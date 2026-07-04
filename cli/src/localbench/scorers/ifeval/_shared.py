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

"""Shared helpers for reimplemented IFEval checks."""

from __future__ import annotations

import warnings
from typing import Final

from localbench.scorers.ifeval._types import InstructionKwargs, JsonValue

try:
    import langdetect as _langdetect
    from langdetect.lang_detect_exception import LangDetectException as _LangDetectException
except ModuleNotFoundError:
    _langdetect = None
    _LangDetectException = RuntimeError

LESS_THAN: Final = "less than"
AT_LEAST: Final = "at least"
LANGDETECT_UNAVAILABLE_WARNING: Final = (
    "langdetect is unavailable; IFEval language check is indeterminate"
)


def compare(actual: int, threshold: int, relation: str) -> bool:
    match relation:
        case "less than":
            return actual < threshold
        case "at least":
            return actual >= threshold
        case _:
            return False


def string_arg(kwargs: InstructionKwargs, key: str) -> str | None:
    value = kwargs.get(key)
    if isinstance(value, str):
        return value.strip()
    return None


def int_arg(kwargs: InstructionKwargs, key: str) -> int | None:
    value = kwargs.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def string_list_arg(kwargs: InstructionKwargs, key: str) -> list[str]:
    return string_list(kwargs.get(key))


def string_list(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def detect_language(value: str) -> str | None:
    if _langdetect is None:
        warnings.warn(LANGDETECT_UNAVAILABLE_WARNING, RuntimeWarning, stacklevel=2)
        return None
    try:
        return _langdetect.detect(value)
    except _LangDetectException:
        return None
