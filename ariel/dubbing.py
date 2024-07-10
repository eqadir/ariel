# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A dubbing module of Ariel package from the Google EMEA gTech Ads Data Science."""

import dataclasses
import functools
import importlib.resources
import json
import os
import readline
import shutil
import tempfile
import time
from typing import Final, Mapping, Sequence
from absl import logging
from ariel import audio_processing
from ariel import speech_to_text
from ariel import text_to_speech
from ariel import translation
from ariel import video_processing
from elevenlabs.client import ElevenLabs
from elevenlabs.core import ApiError
from faster_whisper import WhisperModel
from google.api_core.exceptions import BadRequest, ServiceUnavailable
from google.cloud import texttospeech
import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory
from pyannote.audio import Pipeline
import tensorflow as tf
import torch
from tqdm import tqdm

_ACCEPTED_VIDEO_FORMATS: Final[tuple[str, ...]] = (".mp4",)
_ACCEPTED_AUDIO_FORMATS: Final[tuple[str, ...]] = (".wav", ".mp3", ".flac")
_UTTERNACE_METADATA_FILE_NAME: Final[str] = "utterance_metadata"
_EXPECTED_HUGGING_FACE_ENVIRONMENTAL_VARIABLE_NAME: Final[str] = (
    "HUGGING_FACE_TOKEN"
)
_EXPECTED_GEMINI_ENVIRONMENTAL_VARIABLE_NAME: Final[str] = "GEMINI_TOKEN"
_EXPECTED_ELEVENLABS_ENVIRONMENTAL_VARIABLE_NAME: Final[str] = (
    "ELEVENLABS_TOKEN"
)
_DEFAULT_PYANNOTE_MODEL: Final[str] = "pyannote/speaker-diarization-3.1"
_DEFAULT_ELEVENLABS_MODEL: Final[str] = "eleven_multilingual_v2"
_DEFAULT_TRANSCRIPTION_MODEL: Final[str] = "large-v3"
_DEFAULT_GEMINI_MODEL: Final[str] = "gemini-1.5-flash"
_DEFAULT_GEMINI_TEMPERATURE: Final[float] = 1.0
_DEFAULT_GEMINI_TOP_P: Final[float] = 0.95
_DEFAULT_GEMINI_TOP_K: Final[int] = 64
_DEFAULT_GEMINI_MAX_OUTPUT_TOKENS: Final[int] = 8192
_DEFAULT_GEMINI_RESPONSE_MIME_TYPE: Final[str] = "text/plain"
_DEFAULT_GEMINI_SAFETY_SETTINGS: Final[
    Mapping[HarmCategory, HarmBlockThreshold]
] = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: (
        HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
    ),
    HarmCategory.HARM_CATEGORY_HARASSMENT: (
        HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
    ),
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: (
        HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
    ),
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: (
        HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
    ),
}
_DEFAULT_DIARIZATION_SYSTEM_SETTINGS: Final[str] = "diarization.txt"
_DEFAULT_TRANSLATION_SYSTEM_SETTINGS: Final[str] = "translation.txt"
_NUMBER_OF_STEPS: Final[int] = 7


def is_video(*, input_file: str) -> bool:
  """Checks if a given file is a video (MP4) or audio (WAV, MP3, FLAC).

  Args:
      input_file: The path to the input file.

  Returns:
      True if it's an MP4 video, False otherwise.

  Raises:
      ValueError: If the file format is unsupported.
  """

  _, file_extension = os.path.splitext(input_file)
  file_extension = file_extension.lower()

  if file_extension in _ACCEPTED_VIDEO_FORMATS:
    return True
  elif file_extension in _ACCEPTED_AUDIO_FORMATS:
    return False
  else:
    raise ValueError(f"Unsupported file format: {file_extension}")


def read_system_settings(system_instructions: str) -> str:
  """Reads a .txt file with system instructions from the package.

  - If it's just a string, returns it as is.
  - If it's a .txt file, it assumes you use the defaut package system settings,
  reads them and returns the content.
  - If it has another extension, raises a ValueError.

  Args:
      system_instructions: The string to process.

  Returns:
      The content of the .txt file or the input string.

  Raises:
      ValueError: If the input has an unsupported extension.
      TypeError: If the input file doesn't exist.
      FileNotFoundError: If the .txt file doesn't exist.
  """
  if not isinstance(system_instructions, str):
    raise TypeError("Input must be a string")
  _, extension = os.path.splitext(system_instructions)
  if extension == ".txt":
    try:
      with importlib.resources.path(
          "ariel", "system_settings"
      ) as assets_directory:
        file_path = os.path.join(assets_directory, system_instructions)
        with tf.io.gfile.GFile(file_path, "r") as file:
          result = []
          for line in file:
            if not line.lstrip().startswith("#"):
              result.append(line)
          return "".join(result)
    except Exception:
      raise ValueError(
          "You specified a .txt file that's not part of the Ariel package."
      )
  elif extension:
    raise ValueError(f"Unsupported file type: {extension}")
  else:
    return system_instructions


@dataclasses.dataclass
class PreprocessingArtifacts:
  """Instance with preprocessing outputs.

  Attributes:
      video_file: A path to a video ad with no audio.
      audio_file: A path to an audio track from the ad.
      audio_background_file: A path to and audio track from the ad with removed
        vocals.
  """

  video_file: str
  audio_file: str
  audio_background_file: str


@dataclasses.dataclass
class PostprocessingArtifacts:
  """Instance with postprocessing outputs.

  Attributes:
      audio_file: A path to a dubbed audio file.
      video_file: A path to a dubbed video file. The video is optional.
  """

  audio_file: str
  video_file: str | None


class PyAnnoteAccessError(Exception):
  """Error when establishing access to PyAnnore from Hugging Face."""

  pass


class GeminiAccessError(Exception):
  """Error when establishing access to Gemini."""

  pass


class GoogleTextToSpeechAccessError(Exception):
  """Error when establishing access to Google's Text-To-Speech API."""

  pass


class ElevenLabsAccessError(Exception):
  """Error when establishing access to ElevenLabs API."""

  pass


# BEGIN GOOGLE-INTERNAL
# TODO(krasowiak): Add unit tests for the Dubber class.
# END GOOGLE-INTERNAL
class Dubber:
  """A class to manage the entire ad dubbing process."""

  def __init__(
      self,
      *,
      input_file: str,
      output_directory: str,
      advertiser_name: str,
      original_language: str,
      target_language: str,
      number_of_speakers: int = 1,
      no_dubbing_phrases: Sequence[str] | None = None,
      diarization_instructions: str | None = None,
      translation_instructions: str | None = None,
      merge_utterances: bool = True,
      minimum_merge_threshold: float = 0.001,
      adjust_speed: bool = False,
      preferred_voices: Sequence[str] | None = None,
      clean_up: bool = True,
      pyannote_model: str = _DEFAULT_PYANNOTE_MODEL,
      diarization_system_instructions: str = _DEFAULT_DIARIZATION_SYSTEM_SETTINGS,
      translation_system_instructions: str = _DEFAULT_TRANSLATION_SYSTEM_SETTINGS,
      hugging_face_token: str | None = None,
      gemini_token: str | None = None,
      elevenlabs_token: str | None = None,
      use_elevenlabs: bool = False,
      clone_voices: bool = False,
      elevenlabs_model: str = _DEFAULT_ELEVENLABS_MODEL,
      gemini_model_name: str = _DEFAULT_GEMINI_MODEL,
      temperature: float = _DEFAULT_GEMINI_TEMPERATURE,
      top_p: float = _DEFAULT_GEMINI_TOP_P,
      top_k: int = _DEFAULT_GEMINI_TOP_K,
      max_output_tokens: int = _DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
      response_mime_type: str = _DEFAULT_GEMINI_RESPONSE_MIME_TYPE,
      safety_settings: Mapping[
          HarmCategory, HarmBlockThreshold
      ] = _DEFAULT_GEMINI_SAFETY_SETTINGS,
      number_of_steps: int = _NUMBER_OF_STEPS,
  ) -> None:
    """Initializes the Dubber class with various parameters for dubbing configuration.

    Args:
        input_file: The path to the input video or audio file.
        output_directory: The directory to save the dubbed output and
          intermediate files.
        advertiser_name: The name of the advertiser for context in
          transcription/translation.
        original_language: The language of the original audio. It must be ISO
          3166-1 alpha-2 country code.
        target_language: The language to dub the ad into. It must be ISO 3166-1
          alpha-2 country code.
        number_of_speakers: The exact number of speakers in the ad (including a
          lector if applicable).
        no_dubbing_phrases: A sequence of strings representing the phrases that
          should not be dubbed. It is critical to provide these phrases in a
          format as close as possible to how they might appear in the utterance
          (e.g., include punctuation, capitalization if relevant).
        diarization_instructions: Specific instructions for speaker diarization.
        translation_instructions: Specific instructions for translation.
        merge_utterances: Whether to merge utterances when the the timestamps
          delta between them is below 'minimum_merge_threshold'.
        minimum_merge_threshold: Threshold for merging utterances in seconds.
        adjust_speed: Whether to either speed up or slow down utterances to
          match the duration of the utterances in the source language.
        preferred_voices: Preferred voice names for text-to-speech. Use
          high-level names, e.g. 'Wavenet', 'Standard' etc. Do not use the full
          voice names, e.g. 'pl-PL-Wavenet-A' etc.
        clean_up: Whether to delete intermediate files after dubbing. Only the
          final ouput and the utterance metadata will be kept.
        pyannote_model: Name of the PyAnnote diarization model.
        diarization_system_instructions: System instructions for diarization.
        translation_system_instructions: System instructions for translation.
        hugging_face_token: Hugging Face API token (can be set via
          'HUGGING_FACE_TOKEN' environment variable).
        gemini_token: Gemini API token (can be set via 'GEMINI_TOKEN'
          environment variable).
        elevenlabs_token: ElevenLabs API token (can be set via
          'ELEVENLABS_TOKEN' environment variable).
        use_elevenlabs: Whether to use ElevenLabs API for Text-To-Speech. If not
          Google's Text-To-Speech will be used.
        clone_voices: Whether to clone source voices. It requires using
          ElevenLabs API.
        elevenlabs_model: The ElevenLabs model to use in the Text-To-Speech
          process.
        gemini_model_name: The name of the Gemini model to use.
        temperature: Controls randomness in generation.
        top_p: Nucleus sampling threshold.
        top_k: Top-k sampling parameter.
        max_output_tokens: Maximum number of tokens in the generated response.
        response_mime_type: Gemini output mime type.
        safety_settings: Gemini safety settings.
        utterance_metadata: A sequence with dictionaries containing metadata for
          each detected utterance.
        number_of_steps: The total number of steps in the dubbing process.
    """
    self.input_file = input_file
    self.output_directory = output_directory
    self.advertiser_name = advertiser_name
    self.original_language = original_language
    self.target_language = target_language
    self.number_of_speakers = number_of_speakers
    self.no_dubbing_phrases = no_dubbing_phrases
    self.diarization_instructions = diarization_instructions
    self.translation_instructions = translation_instructions
    self.merge_utterances = merge_utterances
    self.minimum_merge_threshold = minimum_merge_threshold
    self.adjust_speed = adjust_speed
    self.preferred_voices = preferred_voices
    self.clean_up = clean_up
    self.pyannote_model = pyannote_model
    self.hugging_face_token = hugging_face_token
    self.gemini_token = gemini_token
    self.elevenlabs_token = elevenlabs_token
    self.use_elevenlabs = use_elevenlabs
    self._clone_voices = clone_voices
    self.elevenlabs_model = elevenlabs_model
    self.diarization_system_instructions = diarization_system_instructions
    self.translation_system_instructions = translation_system_instructions
    self.gemini_model_name = gemini_model_name
    self.temperature = temperature
    self.top_p = top_p
    self.top_k = top_k
    self.max_output_tokens = max_output_tokens
    self.response_mime_type = response_mime_type
    self.safety_settings = safety_settings
    self.utterance_metadata = None
    self._number_of_steps = number_of_steps
    self._rerun = False

  @functools.cached_property
  def device(self):
    return "cuda" if torch.cuda.is_available() else "cpu"

  @functools.cached_property
  def is_video(self) -> bool:
    """Checks if the input file is a video."""
    return is_video(input_file=self.input_file)

  def get_api_token(
      self, *, environmental_variable: str, provided_token: str | None = None
  ) -> str:
    """Helper to get API token, prioritizing provided argument over environment variable.

    Args:
        environmental_variable: The name of the environment variable storing the
          API token.
        provided_token: The API token provided directly as an argument.

    Returns:
        The API token (either the provided one or from the environment).

    Raises:
        ValueError: If neither the provided token nor the environment variable
        is set.
    """
    token = provided_token or os.getenv(environmental_variable)
    if not token:
      raise ValueError(
          f"You must either provide the '{environmental_variable}' argument or"
          f" set the '{environmental_variable.upper()}' environment variable."
      )
    return token

  @functools.cached_property
  def pyannote_pipeline(self) -> Pipeline:
    """Loads the PyAnnote diarization pipeline."""
    hugging_face_token = self.get_api_token(
        environmental_variable=_EXPECTED_HUGGING_FACE_ENVIRONMENTAL_VARIABLE_NAME,
        provided_token=self.hugging_face_token,
    )
    return Pipeline.from_pretrained(
        self.pyannote_model, use_auth_token=hugging_face_token
    )

  @functools.cached_property
  def speech_to_text_model(self) -> WhisperModel:
    """Initializes the Whisper speech-to-text model."""
    return WhisperModel(
        model_size_or_path=_DEFAULT_TRANSCRIPTION_MODEL,
        device=self.device,
        compute_type="float16" if self.device == "cuda" else "int8",
    )

  def configure_gemini_model(
      self, *, system_instructions: str
  ) -> genai.GenerativeModel:
    """Configures the Gemini generative model.

    Args:
        system_instructions: The system instruction to guide the model's
          behavior.

    Returns:
        The configured Gemini model instance.
    """

    gemini_token = self.get_api_token(
        environmental_variable=_EXPECTED_GEMINI_ENVIRONMENTAL_VARIABLE_NAME,
        provided_token=self.gemini_token,
    )
    genai.configure(api_key=gemini_token)
    gemini_configuration = dict(
        temperature=self.temperature,
        top_p=self.top_p,
        top_k=self.top_k,
        max_output_tokens=self.max_output_tokens,
        response_mime_type=self.response_mime_type,
    )
    return genai.GenerativeModel(
        model_name=self.gemini_model_name,
        generation_config=gemini_configuration,
        system_instruction=system_instructions,
        safety_settings=self.safety_settings,
    )

  @functools.cached_property
  def text_to_speech_client(
      self,
  ) -> texttospeech.TextToSpeechClient | ElevenLabs:
    """Creates a Text-to-Speech client."""
    if not self.use_elevenlabs:
      return texttospeech.TextToSpeechClient()
    logging.warning(
        "You decided to use ElevenLabs API. It will generate extra cost. Check"
        " their pricing on the following website:"
        " https://elevenlabs.io/pricing. Use Google's Text-To-Speech to contain"
        " all the costs within your Google Cloud Platform (GCP) project."
    )
    elevenlabs_token = self.get_api_token(
        environmental_variable=_EXPECTED_ELEVENLABS_ENVIRONMENTAL_VARIABLE_NAME,
        provided_token=self.elevenlabs_token,
    )
    return ElevenLabs(api_key=elevenlabs_token)

  def _verify_api_access(self) -> None:
    """Verifies access to all the required APIs."""
    logging.info("Verifying access to PyAnnote from HuggingFace.")
    if not self.pyannote_pipeline:
      raise PyAnnoteAccessError(
          "No access to HuggingFace. Make sure you passed the correct API token"
          " either as 'hugging_face_token' or through the"
          " '{_EXPECTED_HUGGING_FACE_ENVIRONMENTAL_VARIABLE_NAME}'"
          " environmental variable. Also, please make sure you accepted the"
          " user agreement for the segmentation model"
          " (https://huggingface.co/pyannote/segmentation-3.0) and the speaker"
          " diarization model"
          " (https://huggingface.co/pyannote/speaker-diarization-3.1)."
      )
    logging.info("Access to PyAnnote from HuggingFace verified.")
    logging.info("Verifying access to Gemini.")
    try:
      gemini_token = self.get_api_token(
          environmental_variable=_EXPECTED_GEMINI_ENVIRONMENTAL_VARIABLE_NAME,
          provided_token=self.gemini_token,
      )
      genai.configure(api_key=gemini_token)
      genai.get_model(f"models/{_DEFAULT_GEMINI_MODEL}")
    except BadRequest:
      raise GeminiAccessError(
          "No access to Gemini. Make sure you passed the correct API token"
          " either as 'gemini_token' or through the"
          f" '{_EXPECTED_GEMINI_ENVIRONMENTAL_VARIABLE_NAME}' environmental"
          " variable."
      )
    logging.info("Access to Gemini verified.")
    if not self.use_elevenlabs:
      logging.info("Verifying access to Google's Text-To-Speech.")
      try:
        self.text_to_speech_client.list_voices()
      except ServiceUnavailable:
        raise GoogleTextToSpeechAccessError(
            f"No access to Google's Text-To-Speech. Make sure to autorize"
            f" your access with 'gcloud auth application-default login' and"
            f" then 'gcloud auth login'."
        )
      logging.info("Access to Google's Text-To-Speech verified.")
    logging.info("Verifying access to ElevenLabs.")
    try:
      self.text_to_speech_client.user.get()
    except ApiError:
      raise ElevenLabsAccessError(
          "You spcified to use ElevenLabs API for Text-To-Speech. No access to"
          " ElevenLabs. Make sure you passed the correct API token either as"
          " 'elevenlabs_token' or through the"
          f" '{_EXPECTED_ELEVENLABS_ENVIRONMENTAL_VARIABLE_NAME}' environmental"
          " variable."
      )
    logging.info("Access to ElevenLabs verified.")

  @functools.cached_property
  def processed_diarization_system_instructions(self) -> str:
    """Reads and caches diarization system instructions."""
    return read_system_settings(
        system_instructions=self.diarization_system_instructions
    )

  @functools.cached_property
  def processed_translation_system_instructions(self) -> str:
    """Reads and caches translation system instructions."""
    return read_system_settings(
        system_instructions=self.translation_system_instructions
    )

  @functools.cached_property
  def progress_bar(self) -> tqdm:
    """An instance of the progress bar for the dubbing process."""
    total_number_of_steps = (
        self._number_of_steps if self.clean_up else self._number_of_steps - 1
    )
    return tqdm(total=total_number_of_steps, initial=1)

  @functools.cached_property
  def clone_voices(self) -> bool:
    """An indicator whether to use voice cloning during the dubbing process.

    Raises:
        ValueError: When 'clone_voices' is True and 'use_elevenlabs' is False.
    """
    if self._clone_voices and not self.use_elevenlabs:
      raise ValueError("Voice cloning requires using ElevenLabs API.")
    if self._clone_voices:
      logging.warning(
          "You decided to clone voices with ElevenLabs API. It might require a"
          " more expensive pricing tier. Check their pricing on the following"
          " website: https://elevenlabs.io/pricing. Use Google's Text-To-Speech"
          " to contain all the costs within your Google Cloud Platform (GCP)"
          " project."
      )
    return self._clone_voices

  def run_preprocessing(self) -> None:
    """Splits audio/video, applies DEMUCS, and segments audio into utterances with PyAnnote.

    Returns:
        A named tuple containing paths and metadata of the processed files.
    """
    if self.is_video:
      video_file, audio_file = video_processing.split_audio_video(
          video_file=self.input_file, output_directory=self.output_directory
      )
    else:
      video_file = None
      audio_file = self.input_file

    demucs_command = audio_processing.build_demucs_command(
        audio_file=audio_file,
        output_directory=self.output_directory,
        device=self.device,
    )
    audio_processing.execute_demcus_command(command=demucs_command)
    audio_vocals_file, audio_background_file = (
        audio_processing.assemble_split_audio_file_paths(command=demucs_command)
    )

    utterance_metadata = audio_processing.create_pyannote_timestamps(
        audio_file=audio_file,
        number_of_speakers=self.number_of_speakers,
        pipeline=self.pyannote_pipeline,
        device=self.device,
    )
    if self.merge_utterances:
      utterance_metadata = audio_processing.merge_utterances(
          utterance_metadata=utterance_metadata,
          minimum_merge_threshold=self.minimum_merge_threshold,
      )
    utterance_metadata = audio_processing.cut_and_save_audio(
        utterance_metadata=utterance_metadata,
        audio_file=audio_file,
        output_directory=self.output_directory,
    )
    if self.clone_voices:
      utterance_metadata = audio_processing.cut_and_save_audio(
          utterance_metadata=utterance_metadata,
          audio_file=audio_vocals_file,
          output_directory=self.output_directory,
          clone_voices=self.clone_voices,
      )
    self.utterance_metadata = utterance_metadata
    self.preprocesing_output = PreprocessingArtifacts(
        video_file=video_file,
        audio_file=audio_file,
        audio_background_file=audio_background_file,
    )
    logging.info("Completed preprocessing.")
    self.progress_bar.update()

  def run_speech_to_text(self) -> None:
    """Transcribes audio, applies speaker diarization, and updates metadata with Gemini.

    Returns:
        Updated utterance metadata with speaker information and transcriptions.
    """
    media_file = (
        self.preprocesing_output.video_file
        if self.preprocesing_output.video_file
        else self.preprocesing_output.audio_file
    )
    utterance_metadata = speech_to_text.transcribe_audio_chunks(
        utterance_metadata=self.utterance_metadata,
        advertiser_name=self.advertiser_name,
        original_language=self.original_language,
        model=self.speech_to_text_model,
        no_dubbing_phrases=self.no_dubbing_phrases,
    )
    speaker_diarization_model = self.configure_gemini_model(
        system_instructions=self.processed_diarization_system_instructions
    )
    speaker_info = speech_to_text.diarize_speakers(
        file=media_file,
        utterance_metadata=utterance_metadata,
        number_of_speakers=self.number_of_speakers,
        model=speaker_diarization_model,
        diarization_instructions=self.diarization_instructions,
    )
    self.utterance_metadata = speech_to_text.add_speaker_info(
        utterance_metadata=utterance_metadata, speaker_info=speaker_info
    )
    logging.info("Completed transcription.")
    self.progress_bar.update()

  def run_translation(self) -> None:
    """Translates transcribed text and potentially merges utterances with Gemini.

    Returns:
        Updated utterance metadata with translated text.
    """
    script = translation.generate_script(
        utterance_metadata=self.utterance_metadata
    )
    translation_model = self.configure_gemini_model(
        system_instructions=self.processed_translation_system_instructions
    )
    translated_script = translation.translate_script(
        script=script,
        advertiser_name=self.advertiser_name,
        translation_instructions=self.translation_instructions,
        target_language=self.target_language,
        model=translation_model,
    )
    self.utterance_metadata = translation.add_translations(
        utterance_metadata=self.utterance_metadata,
        translated_script=translated_script,
    )
    logging.info("Completed translation.")
    if not self._rerun:
      self.progress_bar.update()

  def run_configure_text_to_speech(self) -> None:
    """Configures the Text-To-Speech process.

    Returns:
        Updated utterance metadata with assigned voices
        and Text-To-Speech settings.
    """
    if not self.clone_voices:
      if not self.use_elevenlabs:
        assigned_voices = text_to_speech.assign_voices(
            utterance_metadata=self.utterance_metadata,
            target_language=self.target_language,
            client=self.text_to_speech_client,
            preferred_voices=self.preferred_voices,
        )
      else:
        assigned_voices = text_to_speech.elevenlabs_assign_voices(
            utterance_metadata=self.utterance_metadata,
            client=self.text_to_speech_client,
            preferred_voices=self.preferred_voices,
        )
    else:
      assigned_voices = None
    self.utterance_metadata = text_to_speech.update_utterance_metadata(
        utterance_metadata=self.utterance_metadata,
        assigned_voices=assigned_voices,
        use_elevenlabs=self.use_elevenlabs,
        clone_voices=self.clone_voices,
    )

  def _run_verify_utterance_metadata(self) -> None:
    """Displays, allows editing, confirms utterance metadata, and offers translation."""
    utterance_metadata = self.utterance_metadata
    self._rerun = False
    while True:
      self._display_utterance_metadata(utterance_metadata)
      if self._edit_utterance_metadata(utterance_metadata):
        continue
      if self._confirm_utterance_metadata(utterance_metadata):
        translate_choice = self._prompt_for_translation()
        if translate_choice == "yes":
          self.run_translation()
        if not self.clone_voices:
          assign_voices_choice = self._prompt_for_assign_voices()
          if assign_voices_choice == "yes":
            self.run_configure_text_to_speech()
        self._rerun = False
        return

  def _display_utterance_metadata(self, utterance_metadata):
    """Displays the current utterance metadata."""
    print("Current utterance metadata:")
    for i, item in enumerate(utterance_metadata):
      print(f"{i+1}. {json.dumps(item, ensure_ascii=False, indent=2)}")

  def _edit_utterance_metadata(self, utterance_metadata) -> bool:
    """Allows editing of the utterance metadata and returns True if edited."""
    edit_choice = input("\nDo you want to edit? (yes/no): ").lower()
    if edit_choice != "yes":
      return False
    while True:
      try:
        index = int(input("Enter item number to edit: ")) - 1
        if 0 <= index < len(utterance_metadata):
          readline.set_startup_hook(
              lambda: readline.insert_text(
                  json.dumps(utterance_metadata[index], ensure_ascii=False)
              )
          )
          modified_input = input(f"Modify: ")
          utterance_metadata[index] = json.loads(modified_input)
          readline.set_startup_hook()
          return True
        else:
          print("Invalid item number.")
      except (json.JSONDecodeError, ValueError):
        print("Invalid JSON or input. Please try again.")

  def _confirm_utterance_metadata(self, utterance_metadata) -> bool:
    """Confirms the final utterance metadata and returns True if confirmed."""
    while True:
      print("The final utterance metadata is:")
      for i, item in enumerate(utterance_metadata):
        print(f"{i+1}. {json.dumps(item, ensure_ascii=False, indent=2)}")
      confirm_choice = input("\nAre you okay with this? (yes/no): ").lower()
      if confirm_choice == "yes":
        self.utterance_metadata = utterance_metadata
        return True
      elif confirm_choice == "no":
        return False
      else:
        print("Invalid choice.")

  def _prompt_for_translation(self) -> str:
    """Prompts the user if they want to run translation."""
    while True:
      translate_choice = input(
          "\nDo you want to run translation (recommended only after modifying"
          " the source utterance text)? (yes/no): "
      ).lower()
      if translate_choice in ("yes", "no"):
        return translate_choice
      else:
        print("Invalid choice.")

  def _prompt_for_assign_voices(self) -> str:
    """Prompts the user if they want to re-assign voices."""
    while True:
      assign_voices_choice = input(
          "\nDo you want to re-assign voices (recommended only after modifying"
          " speaker IDs)? (yes/no): "
      ).lower()
      if assign_voices_choice in ("yes", "no"):
        return assign_voices_choice
      else:
        print("Invalid choice.")

  def run_text_to_speech(self) -> None:
    """Converts translated text to speech and dubs utterances with Google's Text-To-Speech.

    Returns:
        Updated utterance metadata with generated speech file paths.
    """
    self.utterance_metadata = text_to_speech.dub_utterances(
        client=self.text_to_speech_client,
        utterance_metadata=self.utterance_metadata,
        output_directory=self.output_directory,
        target_language=self.target_language,
        adjust_speed=self.adjust_speed,
        elevenlabs_model=self.elevenlabs_model,
        use_elevenlabs=self.use_elevenlabs,
        clone_voices=self.clone_voices,
    )
    logging.info("Completed converting text to speech.")
    if not self._rerun:
      self.progress_bar.update()

  def run_postprocessing(self) -> None:
    """Merges dubbed audio with the original background audio and video (if applicable).

    Returns:
        Path to the final dubbed output file (audio or video).
    """

    dubbed_audio_vocals_file = audio_processing.insert_audio_at_timestamps(
        utterance_metadata=self.utterance_metadata,
        background_audio_file=self.preprocesing_output.audio_background_file,
        output_directory=self.output_directory,
    )
    dubbed_audio_file = audio_processing.merge_background_and_vocals(
        background_audio_file=self.preprocesing_output.audio_background_file,
        dubbed_vocals_audio_file=dubbed_audio_vocals_file,
        output_directory=self.output_directory,
        target_language=self.target_language,
    )
    if self.is_video:
      if not self.preprocesing_output.video_file:
        raise ValueError(
            "A video file must be provided if the input file is a video."
        )
      dubbed_video_file = video_processing.combine_audio_video(
          video_file=self.preprocesing_output.video_file,
          dubbed_audio_file=dubbed_audio_file,
          output_directory=self.output_directory,
          target_language=self.target_language,
      )
    self.postprocessing_output = PostprocessingArtifacts(
        audio_file=dubbed_audio_file,
        video_file=dubbed_video_file if self.is_video else None,
    )
    logging.info("Completed postprocessing.")
    if not self._rerun:
      self.progress_bar.update()

  def run_save_utterance_metadata(self) -> None:
    """Saves a Python dictionary to a JSON file.

    Returns:
      A path to the saved uttterance metadata.
    """
    target_language_suffix = (
        "_" + self.target_language.replace("-", "_").lower()
    )
    utterance_metadata_file = os.path.join(
        self.output_directory,
        _UTTERNACE_METADATA_FILE_NAME + target_language_suffix + ".json",
    )
    try:
      json_data = json.dumps(
          self.utterance_metadata, ensure_ascii=False, indent=4
      )
      with tempfile.NamedTemporaryFile(
          mode="w", delete=False, encoding="utf-8"
      ) as temporary_file:
        json.dump(json_data, temporary_file, ensure_ascii=False)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
      tf.io.gfile.copy(
          temporary_file.name, utterance_metadata_file, overwrite=True
      )
      os.remove(temporary_file.name)
      logging.info(
          "Utterance metadata saved successfully to"
          f" '{utterance_metadata_file}'"
      )
    except Exception as e:
      logging.warning(f"Error saving utterance metadata: {e}")
    self.save_utterance_metadata_output = utterance_metadata_file

  def run_clean_directory(self) -> None:
    """Removes all files and directories from a directory, except for those listed in keep_files."""
    keep_files = [
        os.path.basename(self.postprocessing_output.audio_file),
        os.path.basename(self.save_utterance_metadata_output),
    ]
    if self.postprocessing_output.video_file:
      keep_files += [os.path.basename(self.postprocessing_output.video_file)]
    for item in tf.io.gfile.listdir(self.output_directory):
      item_path = os.path.join(self.output_directory, item)
      if item in keep_files:
        continue
      try:
        if tf.io.gfile.isdir(item_path):
          shutil.rmtree(item_path)
        else:
          tf.io.gfile.remove(item_path)
      except OSError as e:
        logging.error(f"Error deleting {item_path}: {e}")
    logging.info("Temporary artifacts are now removed.")
    if not self._rerun:
      self.progress_bar.update()

  def dub_ad(self) -> PostprocessingArtifacts:
    """Orchestrates the entire ad dubbing process."""
    self._verify_api_access()
    logging.info("Dubbing process starting...")
    start_time = time.time()
    self.run_preprocessing()
    self.run_speech_to_text()
    self.run_translation()
    self.run_configure_text_to_speech()
    self._run_verify_utterance_metadata()
    self.run_text_to_speech()
    self.run_save_utterance_metadata()
    self.run_postprocessing()
    if self.clean_up:
      self.run_clean_directory()
    self.progress_bar.close()
    logging.info("Dubbing process finished.")
    end_time = time.time()
    logging.info("Total execution time: %.2f seconds.", end_time - start_time)
    logging.info("Output files saved in: %s.", self.output_directory)
    return self.postprocessing_output

  def dub_ad_with_utterance_metadata(
      self,
      utterance_metadata: Sequence[Mapping[str, str | float]] | None = None,
  ) -> PostprocessingArtifacts:
    """Orchestrates the complete ad dubbing process using utterance metadata.

    Takes utterance metadata as input, performs the required dubbing steps, and
    returns the post-processed results.

    Args:
        utterance_metadata: A sequence of mappings detailing each utterance's
          metadata. If not provided, uses `self.utterance_metadata`. Each
          mapping should contain: * 'path': Audio file path (str). * 'start',
          'end': Utterance start/end times in seconds (float). * 'text',
          'translated_text': Original and translated text (str). *
          'for_dubbing': Whether to dub this utterance (bool). * 'speaker_id':
          Speaker identifier (str). * 'ssml_gender': Text-to-speech voice gender
          (str). * 'assigned_voice': Google/ElevenLabs voice name (str). *
          Google TTS-specific: 'pitch', 'speed', 'volume_gain_db' (float). *
          ElevenLabs TTS-specific: 'stability', 'similarity_boost', 'style'
          (float), 'use_speaker_boost' (bool).

    Returns:
        PostprocessingArtifacts: Object containing the post-processed results.
    """

    logging.info("Re-run dubbing process starting...")
    if self.clean_up:
      logging.warning(
          "You are trying to run the dubbing process using utterance metadata."
          " But it looks like you have cleaned up all the process artifacts"
          " during the last run. They might not be available now and the"
          " process might not complete successfully."
      )
    if utterance_metadata:
      self.utterance_metadata = utterance_metadata
    logging.warning(
        "The class utterance metadata was overwritten with the provided input."
    )
    self._rerun = True
    self._run_verify_utterance_metadata()
    self.run_text_to_speech()
    self.run_postprocessing()
    logging.info("Dubbing process finished.")
    logging.info("Output files saved in: %s.", self.output_directory)
    return self.postprocessing_output


  def dub_ad_with_different_language(self, target_language: str) -> PostprocessingArtifacts:
    """Orchestrates the complete ad dubbing process using a new target language.

    Args:
        target_language: The new language to dub the ad into. It must be ISO 3166-1
          alpha-2 country code.

    Returns:
        PostprocessingArtifacts: Object containing the post-processed results.
    """
    logging.info("Re-run dubbing process starting...")
    self.target_language = target_language
    if self.clean_up:
      logging.warning(
          "You are trying to run the dubbing process using utterance metadata."
          " But it looks like you have cleaned up all the process artifacts"
          " during the last run. They might not be available now and the"
          " process might not complete successfully."
      )
    self.target_language = target_language
    logging.warning(
        "The class target language was overwritten with the provided input."
    )
    self._rerun = True
    self.run_translation()
    self.run_configure_text_to_speech()
    self._run_verify_utterance_metadata()
    self.run_text_to_speech()
    self.run_save_utterance_metadata()
    self.run_postprocessing()
    if self.clean_up:
      self.run_clean_directory()
    logging.info("Dubbing process finished.")
    logging.info("Output files saved in: %s.", self.output_directory)
    return self.postprocessing_output
