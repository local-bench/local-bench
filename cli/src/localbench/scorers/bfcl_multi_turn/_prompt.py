from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

from localbench.scorers.bfcl_multi_turn._types import JsonValue

_PROMPT_TEMPLATE: Final = (
    "You are solving a BFCL multi-turn tool-use task in one response.\n"
    "Return only a JSON array. The array must contain one array per user turn. "
    "Each turn array must contain Python-style function-call strings, in execution order.\n"
    "Example: [[\"tool_a(x=1)\", \"tool_b(name='x')\"], [\"tool_c()\"]]\n"
    "Do not include prose, markdown, tool results, or explanations.\n\n"
    "Available functions in JSON format:\n{functions}\n\n"
    "initial_config:\n{initial_config}\n\n"
    "User turns:\n{turns}"
)


def build_bfcl_multi_turn_prompt(prompt_item: Mapping[str, JsonValue]) -> str:
    functions = prompt_item.get("function")
    initial_config = prompt_item.get("initial_config")
    question = prompt_item.get("question")
    if not isinstance(functions, list) or not functions:
        return ""
    turns = _turn_text(question)
    if not turns:
        return ""
    return _PROMPT_TEMPLATE.format(
        functions=json.dumps(functions, ensure_ascii=False, sort_keys=True),
        initial_config=json.dumps(initial_config if isinstance(initial_config, dict) else {}, ensure_ascii=False, sort_keys=True),
        turns=turns,
    )


def _turn_text(question: JsonValue | None) -> str:
    if not isinstance(question, list):
        return ""
    lines: list[str] = []
    for index, turn in enumerate(question, start=1):
        messages = turn if isinstance(turn, list) else [turn]
        parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if isinstance(role, str) and isinstance(content, str):
                parts.append(f"{role}: {content}")
        if parts:
            lines.append(f"Turn {index}: " + " ".join(parts))
    return "\n".join(lines)
