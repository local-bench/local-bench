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

from collections.abc import Mapping

from localbench.scorers.ifbench._types import IFBenchScore, InstructionKwargs, JsonValue
from localbench.scorers.ifbench.instructions import INSTRUCTION_DICT


def score_ifbench(prompt_item: Mapping[str, JsonValue], response_text: str) -> IFBenchScore:
    prompt = _string(prompt_item.get("prompt")) or ""
    response = response_text if isinstance(response_text, str) else ""
    instruction_ids = _string_list(prompt_item.get("instruction_id_list"))
    kwargs_list = _kwargs_list(prompt_item.get("kwargs"))
    per_instruction = [
        _score_instruction(
            instruction_id=instruction_id,
            kwargs=kwargs_list[index] if index < len(kwargs_list) else {},
            prompt=prompt,
            response_text=response,
        )
        for index, instruction_id in enumerate(instruction_ids)
    ]
    follow_all = bool(per_instruction) and all(per_instruction)
    return {
        "follow_all": follow_all,
        "per_instruction": per_instruction,
        "strict": follow_all,
    }


def _score_instruction(
    *,
    instruction_id: str,
    kwargs: InstructionKwargs,
    prompt: str,
    response_text: str,
) -> bool:
    checker = INSTRUCTION_DICT.get(instruction_id)
    if checker is None or not response_text.strip():
        return False
    try:
        return bool(checker(response_text, _without_none(kwargs), prompt))
    except Exception:
        return False


def _without_none(kwargs: InstructionKwargs) -> InstructionKwargs:
    return {key: value for key, value in kwargs.items() if value is not None}


def _string(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _string_list(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _kwargs_list(value: JsonValue) -> list[InstructionKwargs]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
