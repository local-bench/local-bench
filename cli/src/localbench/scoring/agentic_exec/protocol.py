"""Strict local-bench JSON action protocol."""

from __future__ import annotations

from collections.abc import Mapping

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.types import (
    ActionSchemaError,
    AssistantAction,
    FinalAnswerAction,
    ToolCallAction,
)


def parse_assistant_action(payload: JsonValue) -> AssistantAction:
    """Parse decoded JSON into the assistant action protocol."""
    match payload:  # noqa: MATCH_OK - decoded JSON is open input.
        case dict() as data:
            return _parse_object(data)
        case _:
            raise ActionSchemaError("assistant turn must be one JSON object")


def _parse_object(data: Mapping[str, JsonValue]) -> AssistantAction:
    match data.get("type"):  # noqa: MATCH_OK - protocol boundary rejects unknown tags.
        case "tool_call":
            return _parse_tool_call(data)
        case "final_answer":
            return _parse_final_answer(data)
        case _:
            raise ActionSchemaError("type must be tool_call or final_answer")


def _parse_tool_call(data: Mapping[str, JsonValue]) -> ToolCallAction:
    tool = data.get("tool")
    arguments = data.get("arguments")
    match tool:  # noqa: MATCH_OK - decoded JSON field is open input.
        case str() as tool_name:
            parsed_tool = tool_name
        case _:
            raise ActionSchemaError("tool_call.tool must be a string")
    match arguments:  # noqa: MATCH_OK - decoded JSON field is open input.
        case dict() as argument_map:
            parsed_arguments: JsonObject = dict(argument_map)
        case _:
            raise ActionSchemaError("tool_call.arguments must be an object")
    return ToolCallAction(tool=parsed_tool, arguments=parsed_arguments)


def _parse_final_answer(data: Mapping[str, JsonValue]) -> FinalAnswerAction:
    if "answer" not in data:
        raise ActionSchemaError("final_answer.answer is required")
    return FinalAnswerAction(answer=data["answer"])
