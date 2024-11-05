from flask import Flask, request
import os
import logging
from google.cloud import logging as cloudlogging
from google.cloud import pubsub_v1
import json
import google.cloud.storage
import torch
import traceback
import base64
import shutil
from pathlib import Path
from ariel.dubbing import Dubber, PreprocessingArtifacts, get_safety_settings
from ariel import translation, text_to_speech
import dataclasses
from typing import Mapping, Sequence

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
		processor = GcpDubbingProcessor(project_id, region, local_path)
		processor.process_file(trigger_file_name)
		logging.info(f"Done processing {bucket}/{trigger_file_path}")
	except Exception as e:
		logging.info("Error in processing event")
		logging.error(traceback.format_exc())

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
			original_metadata = json.load(f)
			self.dubber.utterance_metadata = original_metadata

		preview_json_file_path = f"{self.local_path}/{PREVIEW_UTTERANCES_FILE_NAME}"
		with open(preview_json_file_path) as g:
			updated_utterance_metadata = json.load(g)

		updated_utterance_metadata = self._update_modified_metadata(original_metadata, updated_utterance_metadata)
		self._redub_modified_utterances(original_metadata, updated_utterance_metadata)

		self._save_current_utterances()
		logging.info(f"Removing {preview_json_file_path}")
		os.remove(preview_json_file_path)

	def _update_modified_metadata(self, original_metadata: Sequence[Mapping[str,str|float]], updated_metadata: Sequence[Mapping[str,str|float]]):
		logging.info("Updating modified metadata")
		edited_metadata = []
		for original, updated in zip(
			original_metadata, updated_metadata
			):
			original_start_end = (original["start"], original["end"])
			updated_start_end = (updated["start"], updated["end"])
			original_text:str = original["text"]
			updated_text:str = updated["text"]
			original_voice = {"speaker_id":original["speaker_id"], "assigned_voice": original["assigned_voice"], "ssml_gender": original["ssml_gender"]}
			updated_voice = {"speaker_id":updated["speaker_id"], "assigned_voice": updated["assigned_voice"], "ssml_gender": updated["ssml_gender"]}
			if original != updated:
				combined = updated
				edit_index:int = original_metadata.index(original)
				logging.info(f"Found updated utterance at index {edit_index}")
				if original_start_end != updated_start_end:
					combined = self.dubber._repopulate_metadata(utterance = combined)
				if original_text != updated_text:
					combined = self.dubber._run_translation_on_single_utterance(combined)
				if original_voice != updated_voice:
					combined_voice = self.merge_voice_parameters(original_voice, updated_voice)
					combined["speaker_id"] = combined_voice["speaker_id"]
					combined["assigned_voice"] = combined_voice["assigned_voice"]
					combined["ssml_gender"] = combined_voice["ssml_gender"]

				edited_metadata.append((edit_index, combined))

		for edit_index, edited_utterance in edited_metadata:
			self.dubber.utterance_metadata = self.dubber._update_utterance_metadata(
				updated_utterance=edited_utterance,
				utterance_metadata=original_metadata,
				edit_index=edit_index,
				)

		return self.dubber.utterance_metadata

	def merge_voice_parameters(self, original_voice:Mapping[str,str],updated_voice:Mapping[str,str]):
		combined_voice = {}
		if original_voice["speaker_id"] != updated_voice["speaker_id"]:
			#if you select existing speaker ID from another utterance,
			# copy the gender and voice from it
			#if there's a new speaker ID, use updated voice params
			combined_voice["speaker_id"] = updated_voice["speaker_id"]
			voice_if_assigned = self.dubber.voice_assignments.get(updated_voice["speaker_id"])
			if voice_if_assigned:
				combined_voice["assigned_voice"] = voice_if_assigned
				combined_voice["ssml_gender"] = self.dubber._voice_assigner._unique_speaker_mapping[voice_if_assigned]
			else:
				combined_voice["ssml_gender"] = updated_voice["ssml_gender"]
				combined_voice["assigned_voice"] = None
		elif original_voice["assigned_voice"] != updated_voice["assigned_voice"]:
			# if speaker ID didn't change but we set new assigned voice,
			# we need to have new speaker ID and find what gender it is from
			# voice assigner
			combined_voice["assigned_voice"] = updated_voice["assigned_voice"]
			combined_voice["speaker_id"] = None
			combined_voice["ssml_gender"] = updated_voice["ssml_gender"]
			for assigned_speaker_id, assigned_voice in self.dubber._voice_assigner.assigned_voices:
				if assigned_voice == updated_voice["assigned_voice"]:
					combined_voice["speaker_id"] = assigned_speaker_id
					for gender_speaker_id, ssml_gender in self.dubber._voice_assigner._unique_speaker_mapping.items():
						if gender_speaker_id == assigned_speaker_id:
							combined_voice["ssml_gender"] = ssml_gender
							break
					break
		elif original_voice["ssml_gender"] != updated_voice["ssml_gender"]:
			# if you changed gender only, we generate new speaker id
			# and assign not-yet-assigned voice to it
			combined_voice["ssml_gender"] = updated_voice["ssml_gender"]
			combined_voice["assigned_voice"] = None
			combined_voice["speaker_id"] = None

	def _redub_modified_utterances(self, original_metadata, updated_metadata):
		self._reinit_text_to_speech()
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

	def _reinit_text_to_speech(self):
		self.dubber.text_to_speech = text_to_speech.TextToSpeech(
			client=self.dubber.text_to_speech_client,
			utterance_metadata=self.dubber.utterance_metadata,
			output_directory=self.dubber.output_directory,
			target_language=self.dubber.target_language,
			preprocessing_output=dataclasses.asdict(self.dubber.preprocessing_output),
			adjust_speed=self.dubber.adjust_speed,
			use_elevenlabs=self.dubber.use_elevenlabs,
			elevenlabs_model=self.dubber.elevenlabs_model,
			elevenlabs_clone_voices=self.dubber.elevenlabs_clone_voices,
			keep_voice_assignments=self.dubber.keep_voice_assignments,
			voice_assignments=self.dubber.voice_assignments,
		)
		self.dubber.run_configure_text_to_speech()

	def _render_dubbed_video(self):
		with open(f"{self.local_path}/{APPROVED_UTTERANCE_FILE_NAME}") as f:
			self.dubber.utterance_metadata = json.load(f)
			self.dubber.preprocessing_output = self.preprocessing_artifacts

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
