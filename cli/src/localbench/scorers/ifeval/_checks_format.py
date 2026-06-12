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

"""Detectable-format IFEval checks reimplemented from Google Research."""

from __future__ import annotations

import json
import re
from typing import Final

from localbench.scorers.ifeval import _shared
from localbench.scorers.ifeval._types import InstructionKwargs

_CONSTRAINED_RESPONSES: Final = (
    "My answer is yes.",
    "My answer is no.",
    "My answer is maybe.",
)


def check_number_bullets(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    expected = _shared.int_arg(kwargs, "num_bullets")
    if expected is None:
        return False
    star_bullets = re.findall(r"^\s*\*[^\*].*$", value, flags=re.MULTILINE)
    dash_bullets = re.findall(r"^\s*-.*$", value, flags=re.MULTILINE)
    return len(star_bullets) + len(dash_bullets) == expected


def check_constrained_response(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    stripped = value.strip()
    return stripped in _CONSTRAINED_RESPONSES


def check_number_highlights(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    expected = _shared.int_arg(kwargs, "num_highlights")
    if expected is None:
        return False
    highlights = re.findall(r"\*[^\n\*]*\*", value)
    double_highlights = re.findall(r"\*\*[^\n\*]*\*\*", value)
    count = sum(1 for highlight in highlights if highlight.strip("*").strip())
    count += sum(
        1
        for highlight in double_highlights
        if highlight.removeprefix("**").removesuffix("**").strip()
    )
    return count >= expected


def check_multiple_sections(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del prompt
    splitter = _shared.string_arg(kwargs, "section_spliter")
    expected = _shared.int_arg(kwargs, "num_sections")
    if splitter is None or expected is None:
        return False
    sections = re.split(r"\s?" + splitter + r"\s?\d+\s?", value)
    return len(sections) - 1 >= expected


def check_json_format(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    stripped = (
        value.strip()
        .removeprefix("```json")
        .removeprefix("```Json")
        .removeprefix("```JSON")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    try:
        json.loads(stripped)
    except ValueError:
        return False
    return True


def check_title(value: str, kwargs: InstructionKwargs, prompt: str) -> bool:
    del kwargs, prompt
    return any(title.lstrip("<").rstrip(">").strip() for title in re.findall(r"<<[^\n]+>>", value))
