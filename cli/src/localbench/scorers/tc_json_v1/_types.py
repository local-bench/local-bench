from __future__ import annotations

from typing import Literal, NotRequired, TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

FailureReason: TypeAlias = Literal[
    "invalid_json",
    "extra_text_or_multiple_json_objects",
    "response_schema_invalid",
    "wrong_schema_version",
    "wrong_call_count",
    "wrong_tool",
    "arg_schema_invalid",
    "call_or_arg_mismatch",
]

NormalizerId: TypeAlias = Literal["iso_date", "iso_datetime", "hhmm_24h", "enum-casefold"]


class ToolSpec(TypedDict):
    name: str
    description: str
    parameters: JsonObject


class ToolCall(TypedDict):
    name: str
    arguments: JsonObject


class GoldSpec(TypedDict):
    order_matters: bool
    calls: list[ToolCall]


class MatchPolicy(TypedDict):
    default: str
    normalizers: dict[str, NormalizerId]
    allow_default_omission: bool
    unordered_arrays: list[str]


class TCJsonItem(TypedDict):
    id: str
    source: str
    stratum: str
    prompt: str
    tools: list[ToolSpec]
    gold: GoldSpec
    match_policy: MatchPolicy


class FailureDiagnostics(TypedDict):
    extra_call: list[ToolCall]
    missing_call: list[ToolCall]
    arg_mismatch: list[JsonObject]


class TCJsonScore(TypedDict):
    correct: bool
    extracted: str | None
    failure_reason: FailureReason | None
    diagnostics: FailureDiagnostics
    response_schema_valid: bool
    schema_version: str | None


class ParseResult(TypedDict):
    value: JsonObject | None
    extracted: str | None
    failure_reason: FailureReason | None


class ValidationResult(TypedDict):
    valid: bool
    message: NotRequired[str]
