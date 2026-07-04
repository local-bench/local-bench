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

"""Length and content IFEval checks reimplemented from Google Research."""

from __future__ import annotations

import re

from localbench.scorers.ifeval import _shared, _util
from localbench.scorers.ifeval._types import InstructionKwargs


def check_number_sentences(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    threshold = _shared.int_arg(kwargs, "num_sentences")
    relation = _shared.string_arg(kwargs, "relation")
    if threshold is None or relation is None:
        return False
    return _shared.compare(_util.count_sentences(value), threshold, relation)


def check_number_paragraphs(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    expected = _shared.int_arg(kwargs, "num_paragraphs")
    if expected is None:
        return False
    paragraphs = re.split(r"\s?\*\*\*\s?", value)
    count = len(paragraphs)
    for index, paragraph in enumerate(paragraphs):
        if not paragraph.strip():
            if index == 0 or index == len(paragraphs) - 1:
                count -= 1
            else:
                return False
    return count == expected


def check_number_words(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    threshold = _shared.int_arg(kwargs, "num_words")
    relation = _shared.string_arg(kwargs, "relation")
    if threshold is None or relation is None:
        return False
    return _shared.compare(_util.count_words(value), threshold, relation)


def check_nth_paragraph_first_word(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    expected_count = _shared.int_arg(kwargs, "num_paragraphs")
    nth = _shared.int_arg(kwargs, "nth_paragraph")
    first_word = _shared.string_arg(kwargs, "first_word")
    if expected_count is None or nth is None or first_word is None:
        return False
    paragraphs = re.split(r"\n\n", value)
    non_empty_count = len([paragraph for paragraph in paragraphs if paragraph.strip()])
    if nth > non_empty_count:
        return False
    paragraph = paragraphs[nth - 1].strip()
    if not paragraph:
        return False
    word = paragraph.split()[0].strip().lstrip("'").lstrip('"')
    observed = ""
    for letter in word:
        if letter in {".", ",", "?", "!", "'", '"'}:
            break
        observed += letter.lower()
    return non_empty_count == expected_count and observed == first_word.lower()


def check_number_placeholders(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    expected = _shared.int_arg(kwargs, "num_placeholders")
    return expected is not None and len(re.findall(r"\[.*?\]", value)) >= expected


def check_postscript(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    marker = _shared.string_arg(kwargs, "postscript_marker")
    if marker is None:
        return False
    lowered = value.lower()
    match marker:
        case "P.P.S":
            pattern = r"\s*p\.\s?p\.\s?s.*$"
        case "P.S.":
            pattern = r"\s*p\.\s?s\..*$"
        case _:
            pattern = r"\s*" + marker.lower() + r".*$"
    return bool(re.findall(pattern, lowered, flags=re.MULTILINE))
