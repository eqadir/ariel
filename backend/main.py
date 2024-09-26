import logging
from typing import Any, Dict
import functions_framework
from google.cloud import logging as cloudlogging
import google.cloud.storage

# import tensorflow as tf
import json
from ariel.dubbing import Dubber


@functions_framework.cloud_event
def generate_utterances(cloud_event: Dict[str, Any]):
    """Triggered by a change in a storage bucket.

    Args:
      cloud_event: The Eventarc trigger event.
    """
    # Instantiates a client
    log_client = cloudlogging.Client()
    log_client.setup_logging()

    data = cloud_event.data
    bucket = data["bucket"]
    name = data["name"]

    logging.info(f"Bucket: {bucket}, Name: {name}")
    if str(name).endswith("config.json") == False:
        logging.info(f"Ignoring {name}")
        return

    logging.info(f"Processing {name}")

    storage_client = google.cloud.storage.Client()
    blob = storage_client.get_bucket(bucket).blob(name)
    data = json.loads(blob.download_as_string(client=None))
    logging.info(data)

    input_video_local_path = "/tmp/input.mp4"
    input_video_gcs_path = str(name).replace("config.json", "input.mp4")
    video_blob = storage_client.get_bucket(bucket).blob(input_video_gcs_path)
    video_blob.download_to_filename(input_video_local_path)

    data["input_video"] = input_video_local_path
    data["output_directory"] = "/tmp/output"

    languages = data['target_languages']
    data['target_language'] = languages[0]

    dubber = Dubber(**data)

    utterances = dubber.generate_utterance_metadata()

    utterances_json = json.dumps(utterances)
    logging.info(f"Utterances: {utterances_json}")
    utterances_gcs_path = str(name).replace("config.json", "utterances.json")
    storage_client.get_bucket(bucket).blob(utterances_gcs_path).upload_from_string(
        utterances_json, client=None
    )

    # metageneration = data["metageneration"]
    # timeCreated = data["timeCreated"]
    # updated = data["updated"]

    # request_json = request.get_json(silent=True)

    # diarization_instructions = ""
    # translation_instructions = ""
    # elevenlabs_token = ""
    # elevenlabs_clone_voices = False
    # preferred_voices = ["Journey", "Studio", "Wavenet",
    #                     "Polyglot", "News", "Neural2", "Standard"]

    # merge_utterances = True
    # minimum_merge_threshold = 0.001
    # adjust_speed = True
    # vocals_volume_adjustment = 5.0
    # background_volume_adjustment = 0.0
    # gemini_model_name = "gemini-1.5-flash"
    # gemini_temperature = 1.0
    # gemini_top_p = 0.95
    # gemini_top_k = 64
    # gemini_maximum_output_tokens = 8192
    # clean_up = True
    # with_verification = False

    # # 1. Accessing named parameters from JSON body:
    # if request_json:
    #     # Use .get() to avoid KeyError
    #     input_video = request_json.get('input_video')
    #     output_directory = request_json.get('output_directory')
    #     advertiser_name = request_json.get('advertiser_name')
    #     original_language = request_json.get('original_language')
    #     target_language = request_json.get('target_language')
    #     number_of_speakers = request_json.get('number_of_speakers')
    #     gemini_token = request_json.get('gemini_token')
    #     hugging_face_token = request_json.get('hugging_face_token')
    #     elevenlabs_token = request_json.get(
    #         'elevenlabs_token', elevenlabs_token)
    #     elevenlabs_clone_voices = request_json.get(
    #         'elevenlabs_clone_voices', elevenlabs_clone_voices)
    #     no_dubbing_phrases = request_json.get(
    #         'no_dubbing_phrases', no_dubbing_phrases)
    #     diarization_instructions = request_json.get(
    #         'diarization_instructions', diarization_instructions)
    #     translation_instructions = request_json.get(
    #         'translation_instructions', translation_instructions)
    #     merge_utterances = request_json.get(
    #         'merge_utterances', merge_utterances)
    #     minimum_merge_threshold = request_json.get(
    #         'minimum_merge_threshold', minimum_merge_threshold)
    #     preferred_voices = request_json.get(
    #         'preferred_voices', preferred_voices)
    #     adjust_speed = request_json.get('adjust_speed', adjust_speed)
    #     vocals_volume_adjustment = request_json.get(
    #         'vocals_volume_adjustment', vocals_volume_adjustment)
    #     background_volume_adjustment = request_json.get(
    #         'background_volume_adjustment', background_volume_adjustment)
    #     no_dubbing_phrases = request_json.get(
    #         'no_dubbing_phrases', [])

    #     # ... access other named parameters similarly

    # # # 2. Accessing named parameters from query parameters:
    # # if request_args:
    # #     input_file = request_args.get('input_file')
    # #     # ... access other named parameters similarly

    # use_elevenlabs = False if elevenlabs_token == "" else True

    # if not tf.io.gfile.exists(output_directory):
    #     tf.io.gfile.makedirs(output_directory)
    # dubber = Dubber(
    #     input_file=input_video,
    #     output_directory=output_directory,
    #     advertiser_name=advertiser_name,
    #     original_language=original_language,
    #     target_language=target_language,
    #     number_of_speakers=number_of_speakers,
    #     gemini_token=gemini_token,
    #     hugging_face_token=hugging_face_token,
    #     no_dubbing_phrases=no_dubbing_phrases,
    #     diarization_instructions=diarization_instructions,
    #     translation_instructions=translation_instructions,
    #     merge_utterances=merge_utterances,
    #     minimum_merge_threshold=minimum_merge_threshold,
    #     preferred_voices=preferred_voices,
    #     adjust_speed=adjust_speed,
    #     vocals_volume_adjustment=vocals_volume_adjustment,
    #     background_volume_adjustment=background_volume_adjustment,
    #     clean_up=clean_up,
    #     gemini_model_name=gemini_model_name,
    #     temperature=gemini_temperature,
    #     top_p=gemini_top_p,
    #     top_k=gemini_top_k,
    #     max_output_tokens=gemini_maximum_output_tokens,
    #     use_elevenlabs=use_elevenlabs,
    #     elevenlabs_token=elevenlabs_token,
    #     elevenlabs_clone_voices=elevenlabs_clone_voices,
    #     with_verification=with_verification,
    # )

    # utterance_metadata = dubber.generate_utterance_metadata()

    # return json.dumps(utterance_metadata)


# @functions_framework.http
# def translate_video(request):
#     return "{'dummy':'asd'}"
