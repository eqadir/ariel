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

"""A translation module of Ariel package from the Google EMEA gTech Ads Data Science."""

import re
from typing import Final, Mapping, Sequence
import google.generativeai as genai

_TRANSLATION_PROMPT: Final[str] = (
    "You're hired by a company called: {}. The received transcript is: {}."
    " Specific instructions: {}. The target language is: {}."
)


def generate_script(
    utterance_metadata: Sequence[Mapping[str, str | float]],
) -> str:
  """Generates a script string from a list of utterance metadata.

  Args:
    utterance_metadata: The sequence of mappings, where each mapping represents
      utterance metadata with "text", "start", "end", "speaker_id",
      "ssml_gender", "for_dubbing" keys.

  Returns:
    A string representing the script, with "<BREAK>" inserted
    between chunks.
  """
  script = " <BREAK> ".join(str(item["text"]) for item in utterance_metadata)
  script = script.replace("  ", " ")
  return script.rstrip(" <BREAK> ")


def translate_script(
    *,
    script: str,
    advertiser_name: str,
    translation_instructions: str,
    target_language: str,
    model: genai.GenerativeModel,
) -> str:
  """Translates the provided transcript to the target language using a Generative AI model.

  Args:
      script: The transcript to translate.
      advertiser_name: The name of the advertiser.
      translation_instructions: Specific instructions for the translation.
      target_language: The target language for the translation.
      model: The GenerativeModel to use for translation.

  Returns:
      The translated script.
  """
  prompt = _TRANSLATION_PROMPT.format(
      advertiser_name, script, translation_instructions, target_language
  )
  translation_chat_session = model.start_chat()
  response = translation_chat_session.send_message(prompt)
  translation_chat_session.rewind()
  return response.text


def add_translations(
    *,
    utterance_metadata: Sequence[Mapping[str, str | float]],
    translated_script: str,
) -> Sequence[Mapping[str, str | float]]:
  """Updates the "translated_text" field of each utterance metadata with the corresponding text segment.

  Args:
      utterance_metadata: The sequence of mappings, where each mapping
        represents utterance metadata with "text", "start", "end", "speaker_id",
        "ssml_gender", "path", "for_dubbing" keys.
      translated_script: The string containing the translated text segments,
        separated by "<BREAK>".

  Returns:
      A list of updated utterance metadata with the "translated_text" field
      populated.

  Raises:
      ValueError: If the number of utterance metadata and text segments do not
      match.
  """
  text_string = re.sub(r"\s*<BREAK>\s*", "<BREAK>", translated_script).rstrip()
  text_segments = [
      segment for segment in text_string.split("<BREAK>") if segment
  ]
  if len(utterance_metadata) != len(text_segments):
    raise ValueError(
        "The utterance metadata must be of the same length as the text"
        f" segments. Currently they are: {len(utterance_metadata)} and"
        f" {len(text_segments)}."
    )
  updated_utterance_metadata = []
  for metadata, translated_text in zip(utterance_metadata, text_segments):
    if translated_text != "<DO NOT TRANSLATE>":
      updated_utterance_metadata.append(
          {**metadata, "translated_text": translated_text}
      )
    else:
      continue
  return updated_utterance_metadata