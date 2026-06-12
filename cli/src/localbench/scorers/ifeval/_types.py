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

"""Typed contracts for IFEval scoring."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
InstructionKwargs: TypeAlias = Mapping[str, JsonValue]
Checker: TypeAlias = Callable[[str, InstructionKwargs, str], bool]


class IFEvalScore(TypedDict):
    """Strict IFEval scorer result."""

    follow_all: bool
    per_instruction: list[bool]
    strict: bool
