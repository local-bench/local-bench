# coding=utf-8
# Copyright 2026 The Google Research Authors.
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

"""Keyword and language IFEval checks reimplemented from Google Research."""

from __future__ import annotations

import collections
import re

from localbench.scorers.ifeval import _shared
from localbench.scorers.ifeval._types import InstructionKwargs


def check_keyword_existence(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    return all(
        re.search(keyword, value, flags=re.IGNORECASE)
        for keyword in _shared.string_list_arg(kwargs, "keywords")
    )


def check_keyword_frequency(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    keyword = _shared.string_arg(kwargs, "keyword")
    frequency = _shared.int_arg(kwargs, "frequency")
    relation = _shared.string_arg(kwargs, "relation")
    if keyword is None or frequency is None or relation is None:
        return False
    actual = len(re.findall(keyword, value, flags=re.IGNORECASE))
    return _shared.compare(actual, frequency, relation)


def check_forbidden_words(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    for word in _shared.string_list_arg(kwargs, "forbidden_words"):
        if re.search(r"\b" + word + r"\b", value, flags=re.IGNORECASE):
            return False
    return True


def check_letter_frequency(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    letter = _shared.string_arg(kwargs, "letter")
    frequency = _shared.int_arg(kwargs, "let_frequency")
    relation = _shared.string_arg(kwargs, "let_relation")
    if letter is None or len(letter) != 1 or frequency is None or relation is None:
        return False
    letters = collections.Counter(value.lower())
    return _shared.compare(letters[letter.lower()], frequency, relation)


def check_response_language(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    language = _shared.string_arg(kwargs, "language")
    if language is None:
        return False
    detected = _shared.detect_language(value)
    if detected is None:
        return True
    return detected == language
