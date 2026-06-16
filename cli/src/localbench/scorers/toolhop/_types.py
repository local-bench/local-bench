from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
ToolTrace: TypeAlias = list[str]


class FailureKind(StrEnum):
    MALFORMED_CALL = "malformed_call"
    WRONG_TOOL = "wrong_tool"
    WRONG_ARGS = "wrong_args"
    TOOL_EXEC_ERROR = "tool_exec_error"
    WRONG_FINAL_ANSWER = "wrong_final_answer"
    TIMEOUT = "timeout"


class ToolHopScore(TypedDict):
    correct: bool
    extracted: str | None
    failure_kind: str | None


@dataclass(frozen=True, slots=True)
class ParsedCall:
    function_name: str
    args: tuple[JsonValue, ...]
    kwargs: JsonObject
    raw: str


@dataclass(frozen=True, slots=True)
class TraceExecution:
    calls: ToolTrace
    outputs: list[JsonValue]
    failure_kind: FailureKind | None = None
    message: str | None = None
