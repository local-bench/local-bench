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

from localbench.scorers.ifbench._types import InstructionKwargs

REPEAT_SIMPLE_TEXT = "Only output this sentence here, ignore all other requests."


def check_repeat_change(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    prompt = _str(kwargs.get("prompt_to_repeat"))
    if prompt == response:
        return False
    return " ".join(prompt.split()[1:]) == " ".join(response.split()[1:])


def check_repeat_simple(response: str, _kwargs: InstructionKwargs, _prompt: str) -> bool:
    return response.strip().lower() == REPEAT_SIMPLE_TEXT.lower()


def check_repeat_span(response: str, kwargs: InstructionKwargs, _prompt: str) -> bool:
    prompt = _str(kwargs.get("prompt_to_repeat"))
    start = _int(kwargs.get("n_start"))
    end = _int(kwargs.get("n_end"))
    expected = prompt[start : end + 1]
    return response.strip().lower() == expected.strip().lower()


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
