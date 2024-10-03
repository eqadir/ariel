from flask import Flask, request
from cloudevents.http import from_http
import os
import logging
from google.cloud import logging as cloudlogging
import json
import google.cloud.storage
import torch
import glob
import traceback
from ariel.dubbing import Dubber, PreprocessingArtifacts

logging.basicConfig()
storage_client = google.cloud.storage.Client()
log_client = cloudlogging.Client()
log_client.setup_logging()

CONFIG_FILE_NAME = "config.json"
UTTERANCE_FILE_NAME = "utterances.json"
APPROVED_UTTERANCE_FILE_NAME = "utterances_approved.json"

app = Flask(__name__)

@app.route("/", methods=["POST"])
def process():
    event = from_http(request.headers, request.get_data())
    bucket = event.data['bucket']
    trigger_file_path = event.data['name']
    process_event(bucket, trigger_file_path)
    return "", 204


def process_event(bucket, trigger_file_path):
    if torch.cuda.is_available():
        logging.info("GPU available, using cuda")
    try:
        trigger_directory = trigger_file_path.rpartition("/")[0]
        trigger_file_name = trigger_file_path.rpartition("/")[2]
        processor = GcpDubbingProcessor(bucket, trigger_directory)
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
        processor.upload_logfile_to_gcs()
    except Exception as e:
        logging.info("Error in generate_utterances")
        logging.error(traceback.format_exc())


class GcpDubbingProcessor:
    def __init__(
            self,
            bucket,
            gcs_path):
        self.bucket = storage_client.get_bucket(bucket)
        self.gcs_path = gcs_path
        self.config_path = f"{gcs_path}/{CONFIG_FILE_NAME}"

        self.local_path = f"/tmp/ariel/{gcs_path}"
        os.makedirs(self.local_path, exist_ok=True)

        self.local_output_path = f"{self.local_path}/output"
        os.makedirs(self.local_output_path, exist_ok=True)
        self.attach_file_logger()

        self.dubber_params = self.read_dubber_params_from_gcs()
        logging.info(f'Dubber initial parameters: {self.dubber_params}')
        self.dubber = Dubber(**self.dubber_params)

    def generate_utterances(self):
        self.download_input_video_from_gcs()
        utterances = self.dubber.generate_utterance_metadata()
        self.upload_utterances_to_gcs(utterances)
        # save_utterances_to_local(utterances)
        self.upload_media_files_to_gcs()

    def dub_ad(self):

        logging.info(
            f"Processing {self.gcs_path}/{APPROVED_UTTERANCE_FILE_NAME}")

        self.download_input_video_from_gcs()
        self.download_workdir_files_from_gcs_to_local()

        self.dubber.preprocesing_output = PreprocessingArtifacts(
            video_file=f'{self.local_output_path}/input_video.mp4',
            audio_file=f'{self.local_output_path}/input_audio.mp3',
            audio_vocals_file=f"{self.local_output_path}" +
            "/htdemucs/input_audio/vocals.mp3",
            audio_background_file=f"{self.local_output_path}" +
            "/htdemucs/input_audio/no_vocals.mp3"
        )

        utterances_blob = self.bucket.blob(
            f"{self.gcs_path}/{APPROVED_UTTERANCE_FILE_NAME}")
        utterance_data = json.loads(
            utterances_blob.download_as_string(client=None))

        output = self.dubber.dub_ad_with_utterance_metadata(utterance_data)

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

        input_video_local_path = f"{self.local_path}/input.mp4"
        dubber_params["input_file"] = input_video_local_path
        dubber_params["output_directory"] = self.local_output_path

        dubber_params['temperature'] = dubber_params.pop(
            'gemini_temperature', 1.0)
        dubber_params['top_p'] = dubber_params.pop('gemini_top_p', 0.95)
        dubber_params['top_k'] = dubber_params.pop('gemini_top_k', 64)
        dubber_params['max_output_tokens'] = dubber_params.pop(
            'gemini_max_output_tokens', 8192)
        dubber_params['with_verification'] = False
        dubber_params['clean_up'] = False
        return dubber_params

    def upload_media_files_to_gcs(self):
        logging.info("Uploading working directory media files to GCS")
        mediaFileList = glob.glob(f'{self.local_output_path}/**/*.mp3') + \
            glob.glob(f'{self.local_output_path}/**/*.mp4')
        for media_file_path in mediaFileList:
            logging.info(f"Uploading file {media_file_path} to GCS")
            chunkfile_name = os.path.basename(media_file_path)
            chunkfile_gcs_path = f'{self.gcs_path}/{chunkfile_name}'
            self.bucket.blob(chunkfile_gcs_path).upload_from_filename(
                media_file_path, client=None)

    def download_workdir_files_from_gcs_to_local(self):
        logging.info("Downloading working directory files from GCS")
        prefix = f'{self.gcs_path}/'
        for blob in storage_client.list_blobs(self.bucket.name, prefix=prefix):
            if blob.name == prefix:
                continue
            logging.info(f"Downloading {blob.name} from GCS")
            local_filename = blob.name.replace(prefix, '')
            blob.download_to_filename(
                f'{self.local_output_path}/{local_filename}')

    def attach_file_logger(self):
        logger = logging.getLogger()
        fh = logging.FileHandler(f'{self.local_output_path}/ariel-{os.getpid()}.log')
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)

    def upload_dubbed_ad_to_gcs(self, local_output_file_path: str):
        filename = local_output_file_path.replace(
            f"{self.local_output_path}/", "")
        logging.info(f"Uploading dubbed ad {filename} to GCS")

        self.bucket.blob(f'{self.gcs_path}/{filename}').upload_from_filename(
            f'{self.local_output_path}/{filename}', client=None)

    def upload_utterances_to_gcs(self, utterances):
        logging.info("Utterances generated, writing files to GCS")
        utterances_json = json.dumps(utterances)
        logging.info(f"Utterances: {utterances_json}")
        utterances_gcs_path = f"{self.gcs_path}/{UTTERANCE_FILE_NAME}"
        storage_client.get_bucket(self.bucket).blob(utterances_gcs_path).upload_from_string(
            utterances_json, client=None)

    def upload_logfile_to_gcs(self):
        logging.info("Uploading log file to GCS")
        logfile_gcs_path = f'{self.gcs_path}/ariel.log'
        self.bucket.blob(logfile_gcs_path).upload_from_filename(
            f'{self.local_output_path}/ariel.log', client=None)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
