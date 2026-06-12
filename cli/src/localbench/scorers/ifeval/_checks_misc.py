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

"""Combination, casing, punctuation, and boundary IFEval checks."""

from __future__ import annotations

import re

from localbench.scorers.ifeval import _shared, _util
from localbench.scorers.ifeval._types import InstructionKwargs


def check_two_responses(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    valid = []
    responses = value.split("******")
    for index, response in enumerate(responses):
        if not response.strip():
            if index != 0 and index != len(responses) - 1:
                return False
        else:
            valid.append(response)
    return len(valid) == 2 and valid[0].strip() != valid[1].strip()


def check_repeat_prompt(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    repeat = _shared.string_arg(kwargs, "prompt_to_repeat") or prompt
    return value.strip().lower().startswith(repeat.strip().lower())


def check_end(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    phrase = _shared.string_arg(kwargs, "end_phrase")
    if phrase is None:
        return False
    return value.strip().strip('"').lower().endswith(phrase.strip().lower())


def check_capital_word_frequency(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    frequency = _shared.int_arg(kwargs, "capital_frequency")
    relation = _shared.string_arg(kwargs, "capital_relation")
    if frequency is None or relation is None:
        return False
    count = len([word for word in _util.word_tokenize(value) if word.isupper()])
    return _shared.compare(count, frequency, relation)


def check_english_capital(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    detected = _shared.detect_language(value)
    if detected is None:
        return True
    return value.isupper() and detected == "en"


def check_english_lowercase(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    detected = _shared.detect_language(value)
    if detected is None:
        return True
    return value.islower() and detected == "en"


def check_no_comma(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    return not re.search(r"\,", value)


def check_quotation(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    stripped = value.strip()
    return len(stripped) > 1 and stripped[0] == '"' and stripped[-1] == '"'
