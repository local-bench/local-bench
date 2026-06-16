from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
ActionTrace: TypeAlias = list[list[str]]


class FailureKind(StrEnum):
    MALFORMED_CALL = "malformed_call"
    WRONG_TOOL = "wrong_tool"
    WRONG_ARGS = "wrong_args"
    WRONG_STATE = "wrong_state"
    WRONG_FINAL_RESPONSE = "wrong_final_response"
    TIMEOUT = "timeout"


class BFCLMultiTurnScore(TypedDict):
    correct: bool
    extracted: str | None
    failure_kind: str | None


@dataclass(frozen=True, slots=True)
class ParsedCall:
    function_name: str
    class_name: str | None
    args: tuple[JsonValue, ...]
    kwargs: JsonObject
    raw: str


@dataclass(frozen=True, slots=True)
class TurnExecution:
    responses: list[str]
    failure_kind: FailureKind | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class TraceExecution:
    responses_by_turn: list[list[str]]
    final_state: JsonObject
    failure_kind: FailureKind | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class StateComparison:
    valid: bool
    differences: JsonObject
