from flask import Flask, request
from cloudevents.http import from_http
import os
import logging
from google.cloud import logging as cloudlogging
from google.cloud import pubsub_v1
import json
import google.cloud.storage
import torch
import glob
import traceback
import base64
import shutil
from pathlib import Path
from ariel.dubbing import Dubber, PreprocessingArtifacts, get_safety_settings
from ariel import translation

if __name__ == "__main__":
	logging.basicConfig()

log_client = cloudlogging.Client()
log_client.setup_logging()

storage_client = google.cloud.storage.Client()
if torch.cuda.is_available():
	logging.info("GPU available, using cuda")

CONFIG_FILE_NAME = "config.json"
INPUT_FILE_NAME = "input.mp4"
INITIAL_UTTERANCES_FILE_NAME = "utterances.json"
PREVIEW_UTTERANCES_FILE_NAME = "utterances_preview.json"
APPROVED_UTTERANCE_FILE_NAME = "utterances_approved.json"
DUBBED_VIDEO_FILE_NAME = "dubbed_video.mp4"

TRIGGER_FILES = [
	CONFIG_FILE_NAME, PREVIEW_UTTERANCES_FILE_NAME, APPROVED_UTTERANCE_FILE_NAME
]

WORKDIR_NAME = "output"

app = Flask(__name__)

@app.route("/", methods=["POST"])
def process():
	envelope = request.get_json()
	message_str = base64.b64decode(envelope["message"]["data"]).decode("utf-8").strip()
	message = json.loads(message_str)
	bucket = message["bucket"]
	path = message["name"]
	if should_process_file(path):
		logging.info(f"Processing file {bucket}/{path}")
		project_id = os.environ.get("PROJECT_ID")
		region = os.environ.get("REGION")
		process_event(project_id, region, bucket, path)
		return "Processed", 204
	else:
		logging.info(f"Ignoring file {bucket}/{path}")
		return "Ignored file", 204

def should_process_file(path: str):
	return any(path.endswith(file_name) for file_name in TRIGGER_FILES)

def process_event(project_id, region, bucket, trigger_file_path):
	try:
		trigger_directory = trigger_file_path.rpartition("/")[0]
		trigger_file_name = trigger_file_path.rpartition("/")[2]
		local_path = f"/tmp/ariel/{trigger_directory}"
		synchronizer = WorkdirSynchronizer(bucket, trigger_directory, local_path)
		synchronizer.download_workdir()
		processor = GcpDubbingProcessor(project_id, region, local_path)
		processor.process_file(trigger_file_name)
		synchronizer.upload_workdir()
		logging.info(f"Done processing {bucket}/{trigger_file_path}")
	except Exception as e:
		logging.info("Error in processing event")
		logging.error(traceback.format_exc())

class WorkdirSynchronizer:

	def __init__(
		self,
		bucket_name: str,
		gcs_path: str,
		local_path: str):
		self.bucket = storage_client.get_bucket(bucket_name)
		self.gcs_path = gcs_path
		self.local_path = local_path
		self.local_output_path = f"{self.local_path}/{WORKDIR_NAME}"
		self._ensure_local_dirs_exist()

	def _ensure_local_dirs_exist(self):
		os.makedirs(self.local_path, exist_ok=True)
		os.makedirs(self.local_output_path, exist_ok=True)

	def download_workdir(self):
		logging.info("Downloading working directory files from GCS")
		command = f"gcloud storage rsync -r --delete-unmatched-destination-objects gs://{self.bucket.name}/{self.gcs_path} {self.local_path}"
		os.system(command)

	def upload_workdir(self):
		logging.info("Uploading all working directory files to GCS")
		command = f"gcloud storage rsync -r --delete-unmatched-destination-objects {self.local_path} gs://{self.bucket.name}/{self.gcs_path}"
		os.system(command)

class DummyProgressBar:
	def update(param=None):
		return
	def close():
		return

class GcpDubbingProcessor:
	def __init__(
		self,
		project_id: str,
		region: str,
		local_path: str):
		self.local_path = local_path
		self.project_id = project_id
		self.region = region

		self.dubber_params = self.read_dubber_params_from_config()
		self.enrich_dubber_params()
		logging.info(f'Dubber initial parameters: {self.dubber_params}')
		local_output_path = f"{self.local_path}/{WORKDIR_NAME}"
		self.preprocessing_artifacts = PreprocessingArtifacts(
			video_file=f'{local_output_path}/video_processing/input_video.mp4',
			audio_file=f'{local_output_path}/video_processing/input_audio.mp3',
			audio_vocals_file=f"{local_output_path}" +
			"/audio_processing/vocals.mp3",
			audio_background_file=f"{local_output_path}" +
			"/audio_processing/no_vocals.mp3"
		)

		self.dubber = Dubber(**self.dubber_params)
		self.dubber.progress_bar = DummyProgressBar()

	def process_file(self, file_name: str):
		if file_name == CONFIG_FILE_NAME:
			self._generate_utterances()
		elif file_name == PREVIEW_UTTERANCES_FILE_NAME:
			self._render_preview()
		elif file_name == APPROVED_UTTERANCE_FILE_NAME:
			self._render_dubbed_video()
		else:
			logging.info(f"Unrecognized file to process {file_name}")

	def _generate_utterances(self):
		self.dubber.run_preprocessing()
		self.dubber.run_speech_to_text()
		self.dubber.run_translation()
		self.dubber.run_configure_text_to_speech()
		self.dubber.run_text_to_speech()
		self._save_current_utterances()

	def _render_preview(self):
		self.dubber.preprocessing_output = self.preprocessing_artifacts

		original_utterances_file_path = f"{self.local_path}/{INITIAL_UTTERANCES_FILE_NAME}"
		with open(original_utterances_file_path) as f:
			original_metadata = json.load(original_utterances_file_path)
			self.dubber.utterance_metadata = original_metadata

		preview_json_file_path = f"{self.local_path}/{PREVIEW_UTTERANCES_FILE_NAME}"
		with open(preview_json_file_path) as g:
			updated_utterance_metadata = json.load(g)

		updated_utterance_metadata = self._update_modified_metadata(original_metadata, updated_utterance_metadata)
		self._redub_modified_utterances(original_metadata, updated_utterance_metadata)

		self._save_current_utterances()
		os.remove(preview_json_file_path)

	def _update_modified_metadata(self, original_metadata, updated_metadata):
		for original, updated in zip(
			original_metadata, updated_metadata
			):
			combined = updated
			original_start_end = (original["start"], original["end"])
			updated_start_end = (updated["start"], updated["end"])
			original_text = original.text
			updated_text = updated.text
			edit_index = -1
			if original_start_end != updated_start_end:
				combined = self.dubber._repopulate_metadata(utterance = combined)
				edit_index = original_metadata.index(original)
			if original_text != updated_text:
				combined = self.dubber._run_translation_on_single_utterance(combined)
				edit_index = original_metadata.index(original)
			if edit_index != -1:
				self.dubber.utterance_metadata = self.dubber._update_utterance_metadata(
              updated_utterance=combined,
              utterance_metadata=original,
              edit_index=edit_index,
          )

		return self.dubber.utterance_metadata

	def _redub_modified_utterances(self, original_metadata, updated_metadata):
		#non-interactive copy of Dubber._verify_and_redub_utterances
		edited_utterances = self.dubber.text_to_speech.dub_edited_utterances(
			original_utterance_metadata=original_metadata,
			updated_utterance_metadata=updated_metadata,
			)

		for edited_utterance in edited_utterances:
			for i, original_utterance in enumerate(updated_metadata):
				if (
					original_utterance["path"] == edited_utterance["path"]
					and original_utterance["dubbed_path"]
					!= edited_utterance["dubbed_path"]
				):
					updated_metadata[i] = edited_utterance
		self.dubber.utterance_metadata = updated_metadata

	def _render_dubbed_video(self):
		with open(f"{self.local_path}/{APPROVED_UTTERANCE_FILE_NAME}") as f:
			self.dubber.utterance_metadata = json.load(f)
			self.dubber.preprocessing_output = self.preprocessing_artifacts

			self.dubber.run_text_to_speech()
			self.dubber.run_postprocessing()
			self.dubber.run_save_utterance_metadata()
			self.dubber.postprocessing_output.utterance_metadata = (
				self.dubber.save_utterance_metadata_output
				)
			subtitles_path = translation.save_srt_subtitles(
				utterance_metadata=self.dubber.utterance_metadata,
				output_directory=os.path.join(self.dubber.output_directory, WORKDIR_NAME),
				target_language=self.dubber.target_language
				)
			self.dubber.postprocessing_output.subtitles = subtitles_path
			if self.dubber.elevenlabs_clone_voices and self.dubber.elevenlabs_remove_cloned_voices:
				self.dubber.text_to_speech.remove_cloned_elevenlabs_voices()
			output_video_file = self.dubber.postprocessing_output.video_file

			shutil.copyfile(output_video_file, f"{self.local_path}/{DUBBED_VIDEO_FILE_NAME}")

	def _save_current_utterances(self):
		with open(f"{self.local_path}/{INITIAL_UTTERANCES_FILE_NAME}", "w") as fp:
			json.dump(self.dubber.utterance_metadata, fp)

	def read_dubber_params_from_config(self):
		with open(f"{self.local_path}/{CONFIG_FILE_NAME}") as f:
			dubber_params = json.load(f)
			logging.info(f"Input Parameters: {dubber_params}")
			return dubber_params

	def enrich_dubber_params(self):
		self.inject_required_dubber_params()
		if "safety_settings" in self.dubber_params:
			safety_level = self.dubber_params["safety_settings"]
			self.dubber_params["safety_settings"] = get_safety_settings(safety_level)

	def inject_required_dubber_params(self):
		input_video_local_path = f"{self.local_path}/{INPUT_FILE_NAME}"
		self.dubber_params["input_file"] = input_video_local_path
		self.dubber_params["output_directory"] = f"{self.local_path}/{WORKDIR_NAME}"
		self.dubber_params["gcp_project_id"] = self.project_id
		self.dubber_params["gcp_region"] = self.region
		self.dubber_params['with_verification'] = False
		self.dubber_params['clean_up'] = False

if __name__ == "__main__":
	process_event(os.environ.get("PROJECT_ID"), os.environ.get("REGION"), "cse-kubarozek-sandbox-ariel-us", "test-shell/config.json")
	# process_event(os.environ.get("PROJECT_ID"), os.environ.get("REGION"), "cse-kubarozek-sandbox-ariel-us", "test-shell/utterances_preview.json")
	# process_event(os.environ.get("PROJECT_ID"), os.environ.get("REGION"), "cse-kubarozek-sandbox-ariel-us", "test-shell/utterances_approved.json")
