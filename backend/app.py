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
from pathlib import Path
from ariel.dubbing import Dubber, PreprocessingArtifacts

if __name__ == "__main__":
	logging.basicConfig()

log_client = cloudlogging.Client()
log_client.setup_logging()

storage_client = google.cloud.storage.Client()
if torch.cuda.is_available():
	logging.info("GPU available, using cuda")

CONFIG_FILE_NAME = "config.json"
UTTERANCE_FILE_NAME = "utterances.json"
APPROVED_UTTERANCE_FILE_NAME = "utterances_approved.json"
GCS_WORKDIR_NAME = "output"

app = Flask(__name__)

@app.route("/", methods=["POST"])
def process():
	envelope = request.get_json()
	message_str = base64.b64decode(envelope["message"]["data"]).decode("utf-8").strip()
	message = json.loads(message_str)
	bucket = message["bucket"]
	path = message["name"]
	if should_process_file(path):
		logging.info(f"Processing message about file {bucket}/{path}")
		project_id = os.environ.get("PROJECT_ID")
		region = os.environ.get("REGION")
		process_event(project_id, region, bucket, path)
		return "Processed", 204
	else:
		logging.info(f"Ignoring file {bucket}/{path}")
		return "Ignored file", 204

def should_process_file(path: str):
	return path.endswith(CONFIG_FILE_NAME) or path.endswith(APPROVED_UTTERANCE_FILE_NAME)

def process_event(project_id, region, bucket, trigger_file_path):
	try:
		trigger_directory = trigger_file_path.rpartition("/")[0]
		trigger_file_name = trigger_file_path.rpartition("/")[2]
		processor = GcpDubbingProcessor(project_id, region, bucket, trigger_directory)
		logging.info(f"Bucket: {bucket}, Name: {trigger_file_path}")
		if trigger_file_name == CONFIG_FILE_NAME:
			logging.info(f"Processing {trigger_file_path}")
			processor.generate_utterances()
		elif trigger_file_name == APPROVED_UTTERANCE_FILE_NAME:
			logging.info(f"Processing {trigger_file_path}")
			processor.dub_ad()
		else:
			logging.info(f"Ignoring {trigger_file_path}")
			return
		logging.info("Done")
	except Exception as e:
		logging.info("Error in generate_utterances")
		logging.error(traceback.format_exc())


class GcpDubbingProcessor:
	def __init__(
		self,
		project_id: str,
		region: str,
		bucket: str,
		gcs_path: str):
		self.bucket = storage_client.get_bucket(bucket)
		self.gcs_path = gcs_path
		self.config_path = f"{gcs_path}/{CONFIG_FILE_NAME}"

		self.local_path = f"/tmp/ariel/{gcs_path}"
		os.makedirs(self.local_path, exist_ok=True)

		self.local_output_path = f"{self.local_path}/output"
		os.makedirs(self.local_output_path, exist_ok=True)

		self.project_id = project_id
		self.region = region

		self.dubber_params = self.read_dubber_params_from_gcs()
		self.inject_required_dubber_params()
		logging.info(f'Dubber initial parameters: {self.dubber_params}')
		self.dubber = Dubber(**self.dubber_params)

	def generate_utterances(self):
		self.download_input_video_from_gcs()
		utterances = self.dubber.generate_utterance_metadata()
		self.upload_utterances_to_gcs(utterances)
		self.upload_workdir_files_to_gcs()

	def dub_ad(self):
		logging.info(
			f"Processing {self.gcs_path}/{APPROVED_UTTERANCE_FILE_NAME}")

		self.download_input_video_from_gcs()
		self.download_workdir_files_from_gcs_to_local()

		preprocessing_artifacts = PreprocessingArtifacts(
			video_file=f'{self.local_output_path}/video_processing/input_video.mp4',
			audio_file=f'{self.local_output_path}/video_processing/input_audio.mp3',
			audio_vocals_file=f"{self.local_output_path}" +
			"/audio_processing/htdemucs/input_audio/vocals.mp3",
			audio_background_file=f"{self.local_output_path}" +
			"/audio_processing/htdemucs/input_audio/no_vocals.mp3"
		)

		utterances_blob = self.bucket.blob(
			f"{self.gcs_path}/{APPROVED_UTTERANCE_FILE_NAME}")
		utterance_data = json.loads(
			utterances_blob.download_as_string(client=None))

		output = self.dubber.dub_ad_with_utterance_metadata(utterance_metadata=utterance_data, preprocessing_artifacts=preprocessing_artifacts,overwrite_utterance_metadata=True)

		self.upload_dubbed_ad_to_gcs(output.video_file)

	def download_input_video_from_gcs(self):
		input_video_local_path = f"{self.local_path}/input.mp4"
		input_video_gcs_path = f'{self.gcs_path}/input.mp4'
		logging.info("Downloading input.mp4 file from " +
			f"{input_video_gcs_path} to {input_video_local_path}")

		video_blob = self.bucket.blob(input_video_gcs_path)
		video_blob.download_to_filename(input_video_local_path)

	def read_dubber_params_from_gcs(self):
		"""Sets target_language to first language in the list for error-proofing"""

		config_blob = self.bucket.blob(self.config_path)
		dubber_params = json.loads(config_blob.download_as_string(client=None))
		logging.info(f"Input Parameters: {dubber_params}")

		return dubber_params

	def inject_required_dubber_params(self):
		input_video_local_path = f"{self.local_path}/input.mp4"
		self.dubber_params["input_file"] = input_video_local_path
		self.dubber_params["output_directory"] = self.local_output_path
		self.dubber_params["gcp_project_id"] = self.project_id
		self.dubber_params["gcp_region"] = self.region
		self.dubber_params['with_verification'] = False
		self.dubber_params['clean_up'] = False

	def upload_workdir_files_to_gcs(self):
		logging.info("Uploading all working directory files to GCS")
		mediaFileList = glob.glob(f'{self.local_output_path}/**', recursive=True)
		for media_file_path in mediaFileList:
			if os.path.isfile(media_file_path):
				file_path_under_local_dir = media_file_path.replace(self.local_output_path, GCS_WORKDIR_NAME)
				gcs_file_path = f'{self.gcs_path}/{file_path_under_local_dir}'
				logging.info(f"Uploading file {file_path_under_local_dir} to GCS as {gcs_file_path}")
				self.bucket.blob(gcs_file_path).upload_from_filename(
					media_file_path, client=None)


	def download_workdir_files_from_gcs_to_local(self):
		logging.info("Downloading working directory files from GCS")
		prefix = f'{self.gcs_path}/{GCS_WORKDIR_NAME}/'
		for blob in storage_client.list_blobs(self.bucket.name, prefix=prefix):
			# if blob.name == prefix:
			if blob.name.endswith("/"):
				continue
			gcs_path_under_workdir = blob.name.replace(prefix,'')
			local_path = f'{self.local_output_path}/{gcs_path_under_workdir}'
			local_directory = "/".join(local_path.split("/")[0:-1])
			Path(local_directory).mkdir(parents=True, exist_ok=True)
			logging.info(f"Downloading {blob.name} to {local_path}")
			blob.download_to_filename(local_path)

	def upload_dubbed_ad_to_gcs(self, local_output_file_path: str):
		filename = local_output_file_path.replace(
			f"{self.local_output_path}/", "")
		logging.info(f"Uploading dubbed ad {filename} to GCS")

		output_video_gcs_file_name = "dubbed_video.mp4"
		self.bucket.blob(f'{self.gcs_path}/{output_video_gcs_file_name}').upload_from_filename(
			f'{self.local_output_path}/{filename}', client=None)

	def upload_utterances_to_gcs(self, utterances):
		logging.info("Utterances generated, writing files to GCS")
		utterances_json = json.dumps(utterances)
		logging.info(f"Utterances: {utterances_json}")
		utterances_gcs_path = f"{self.gcs_path}/{UTTERANCE_FILE_NAME}"
		storage_client.get_bucket(self.bucket).blob(utterances_gcs_path).upload_from_string(
			utterances_json, client=None)

if __name__ == "__main__":
	# process_event(os.environ.get("PROJECT_ID"), os.environ.get("REGION"), "cse-kubarozek-sandbox-ariel-us", "test-shell/config.json")
	process_event(os.environ.get("PROJECT_ID"), os.environ.get("REGION"), "cse-kubarozek-sandbox-ariel-us", "test-shell/utterances_approved.json")

