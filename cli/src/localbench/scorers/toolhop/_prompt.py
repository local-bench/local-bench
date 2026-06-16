from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

from localbench.scorers.toolhop._types import JsonValue

_PROMPT_TEMPLATE: Final = (
    "You are solving a ToolHop multi-hop tool-use task in one response.\n"
    "Return only a JSON array of Python-style function-call strings, in execution order.\n"
    "The evaluator will execute each call and use the last tool output as the final answer.\n"
    "Example: [\"tool_a(x=1)\", \"tool_b(name='Ada')\"]\n"
    "Do not include prose, markdown, tool results, code, or explanations.\n\n"
    "Question:\n{question}\n\n"
    "Available tools:\n{tools}\n\n"
    "Subtask count: {hop_count}"
)


def build_toolhop_prompt(prompt_item: Mapping[str, JsonValue]) -> str:
    tools = prompt_item.get("tools")
    question = prompt_item.get("question")
    if not isinstance(tools, dict) or not tools:
        return ""
    if not isinstance(question, str) or not question.strip():
        return ""
    return _PROMPT_TEMPLATE.format(
        question=question,
        tools=json.dumps(_tool_docs(tools), ensure_ascii=False, sort_keys=True),
        hop_count=_hop_count(prompt_item),
    )


def _tool_docs(tools: JsonValue) -> list[JsonValue]:
    if not isinstance(tools, dict):
        return []
    docs: list[JsonValue] = []
    for tool in tools.values():
        if isinstance(tool, dict):
            docs.append(tool)
    return docs


def _hop_count(item: Mapping[str, JsonValue]) -> int:
    hop_count = item.get("hop_count")
    if isinstance(hop_count, int) and not isinstance(hop_count, bool):
        return hop_count
    sub_task = item.get("sub_task")
    return len(sub_task) if isinstance(sub_task, dict) else 0
