from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

from localbench.scorers.bfcl._types import JsonValue

_OUTPUT_FORMAT: Final = "[func_name1(params_name1=params_value1, params_name2=params_value2...), func_name2(params)]"
_PROMPT_TEMPLATE: Final = (
    "You are an expert in composing functions. You are given a question and a set of possible functions. "
    "Based on the question, you will need to make one or more function/tool calls to achieve the purpose.\n"
    "If none of the functions can be used, point it out. If the given question lacks the parameters required by the function, also point it out.\n"
    "You should only return the function calls in your response.\n\n"
    "If you decide to invoke any of the function(s), you MUST put it in the format of {output_format}\n"
    "You SHOULD NOT include any other text in the response.\n\n"
    "At each turn, you should try your best to complete the tasks requested by the user within the current turn. "
    "Continue to output functions to call until you have fulfilled the user's request to the best of your ability. "
    "Once you have no more functions to call, the system will consider the current turn complete and proceed to the next turn or task.\n\n"
    "Here is a list of functions in JSON format that you can invoke.\n{functions}\n\n{question}"
)


def build_bfcl_prompt(prompt_item: Mapping[str, JsonValue]) -> str:
    functions = prompt_item.get("function")
    question = prompt_item.get("question")
    if not isinstance(functions, list) or not functions:
        return ""
    question_text = _question_text(question)
    if not question_text:
        return ""
    return _PROMPT_TEMPLATE.format(
        output_format=_OUTPUT_FORMAT,
        functions=json.dumps(functions, ensure_ascii=False, sort_keys=True),
        question=question_text,
    )


def _question_text(question: JsonValue) -> str:
    if isinstance(question, str):
        return question
    if not isinstance(question, list):
        return ""
    messages = _message_list(question)
    if not messages:
        return ""
    return "\n".join(f"{role}: {content}" for role, content in messages)


def _message_list(question: list[JsonValue]) -> list[tuple[str, str]]:
    current = question[0] if len(question) == 1 and isinstance(question[0], list) else question
    if not isinstance(current, list):
        return []
    messages: list[tuple[str, str]] = []
    for item in current:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if isinstance(role, str) and isinstance(content, str):
            messages.append((role, content))
    return messages
