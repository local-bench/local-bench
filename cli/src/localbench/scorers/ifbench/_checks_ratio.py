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

from localbench.scorers.ifbench import _util
from localbench.scorers.ifbench._types import InstructionKwargs


def check_stop_words(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    words = _util.count_words(response)
    if words == 0:
        return False
    return (_util.count_stopwords(response) / words) * 100 <= _float(kwargs.get("percentage"))


def check_sentence_type(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    sentences = _util.sentence_split(response)
    declarative = sum(1 for sentence in sentences if sentence.endswith("."))
    interrogative = sum(1 for sentence in sentences if sentence.endswith("?"))
    return declarative == 2 * interrogative


def check_sentence_balance(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    sentences = _util.sentence_split(response)
    declarative = sum(1 for sentence in sentences if sentence.endswith("."))
    interrogative = sum(1 for sentence in sentences if sentence.endswith("?"))
    exclamatory = sum(1 for sentence in sentences if sentence.endswith("!"))
    return declarative == interrogative == exclamatory


def check_overlap(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    ngrams = _util.char_ngrams(response, 3)
    reference = _str(kwargs.get("reference_text"))
    reference_ngrams = _util.char_ngrams(reference, 3)
    if not ngrams:
        return False
    overlap = len(ngrams.intersection(reference_ngrams)) / len(ngrams)
    percentage = _float(kwargs.get("percentage"))
    return percentage - 2 <= overlap * 100 <= percentage + 2


def check_sentence_words(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    sentences = _util.sentence_split(response)
    if len(sentences) != 3:
        return False
    expected = len(sentences[0].strip())
    return all(len(sentence.strip()) == expected for sentence in sentences)


def _float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError("expected numeric value")


def _str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string value")
