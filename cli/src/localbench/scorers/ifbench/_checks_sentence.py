# Copyright 2025 Allen Institute for AI.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import re
import string

from localbench.scorers.ifbench import _util
from localbench.scorers.ifbench._types import InstructionKwargs


def check_alliteration_increment(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    previous = -1
    for sentence in _util.sentence_split(response):
        words = [_util.strip_word(word).lower() for word in sentence.split()]
        words = [word for word in words if word]
        alliteration = 0
        previous_alliterative = False
        for index in range(len(words) - 1):
            if words[index][0] == words[index + 1][0]:
                alliteration += 1 if previous_alliterative else 2
                previous_alliterative = True
            else:
                previous_alliterative = False
        if alliteration <= previous:
            return False
        previous = alliteration
    return True


def check_keyword(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    word = _str(kwargs.get("word"))
    nth = _int(kwargs.get("N"))
    sentences = _util.sentence_split(response)
    if len(sentences) < nth:
        return False
    return bool(re.search(rf"\b{re.escape(word)}\b", sentences[nth - 1], re.IGNORECASE))


def check_increment(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    increment = _int(kwargs.get("small_n"))
    sentences = _util.sentence_split(response)
    if not sentences:
        return False
    previous = len(_util.remove_punctuation(sentences[0]).strip().split())
    for sentence in sentences[1:]:
        count = len(_util.remove_punctuation(sentence).strip().split())
        if count != previous + increment:
            return False
        previous = count
    return True


def check_sentence_alphabet(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    sentences = _util.sentence_split(response)
    if len(sentences) != 26:
        return False
    for index, sentence in enumerate(sentences):
        words = sentence.lstrip().split()
        if not words or not words[0] or words[0].lower()[0] != chr(97 + index):
            return False
    return True


def check_last_first(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    sentences = _util.sentence_split(response)
    for index in range(len(sentences) - 1):
        last_words = sentences[index].rstrip(string.punctuation + " ").split()
        first_words = sentences[index + 1].lstrip(string.punctuation + " ").split()
        if not last_words or not first_words:
            return False
        if last_words[-1].lower() != first_words[0].lower():
            return False
    return True


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError("expected integer-compatible value")


def _str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string value")
