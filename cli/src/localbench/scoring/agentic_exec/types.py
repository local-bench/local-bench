"""Shared typed contracts for the agentic execution harness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from localbench._types import JsonObject, JsonValue

ActionKind: TypeAlias = Literal["tool_call", "final_answer"]


class FailureReason(StrEnum):
    """Deterministic failure reasons surfaced by the harness."""

    INVALID_JSON = "invalid_json"
    SCHEMA_ERROR = "schema_error"
    TIMEOUT = "timeout"
    LENGTH = "length"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    FORBIDDEN_TOOL = "forbidden_tool"
    MAX_TURNS_EXCEEDED = "max_turns_exceeded"
    MAX_TOOL_CALLS_EXCEEDED = "max_tool_calls_exceeded"
    LOOP_GUARD = "loop_guard"
    TOOL_ERROR = "tool_error"
    VERIFIER_FAILED = "verifier_failed"
    COLLATERAL_DAMAGE = "collateral_damage"


class ActionSchemaError(Exception):
    """Raised when decoded JSON violates the assistant action schema."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ToolCallAction:
    """A single whitelisted tool invocation requested by the assistant."""

    tool: str
    arguments: JsonObject
    type: Literal["tool_call"] = "tool_call"


@dataclass(frozen=True, slots=True)
class FinalAnswerAction:
    """The assistant's task completion signal."""

    answer: JsonValue
    type: Literal["final_answer"] = "final_answer"


AssistantAction: TypeAlias = ToolCallAction | FinalAnswerAction


@dataclass(frozen=True, slots=True)
class ParseFailure:
    """A parser/protocol failure for one assistant turn."""

    reason: FailureReason
    message: str
    hard_fail: bool


@dataclass(frozen=True, slots=True)
class ParseOutcome:
    """Parsed assistant action or deterministic parse failure."""

    action: AssistantAction | None
    failure: ParseFailure | None
