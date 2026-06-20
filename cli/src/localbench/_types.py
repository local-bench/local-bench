"""Typed contracts for localbench run records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class ChatMessage(TypedDict):
    role: str
    content: str


class BenchmarkItem(TypedDict):
    id: str
    messages: list[ChatMessage]
    sampling_params: JsonObject
    max_tokens: NotRequired[int]
    think_budget: NotRequired[int]


class Usage(TypedDict):
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    reasoning_tokens: NotRequired[int]


class ItemResult(TypedDict):
    id: str
    response_text: str | None
    reasoning_text: str | None
    finish_reason: str | None
    usage: Usage
    latency_seconds: float
    started_at: str
    finished_at: str
    attempts: int
    error: str | None
    thinking_forced: NotRequired[bool]


class RunParams(TypedDict):
    concurrency: int
    timeout_seconds: float
    max_attempts: int


class RunHeader(TypedDict):
    endpoint: str
    model: str
    params: RunParams
    started_at: str
    finished_at: str


class Totals(TypedDict):
    items: int
    errors: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    active_wall_seconds: float
    completion_tokens_per_second: float


class RunRecord(TypedDict):
    run: RunHeader
    totals: Totals
    results: list[ItemResult]


@dataclass(frozen=True, slots=True)
class ParsedCompletion:
    response_text: str
    reasoning_text: str | None
    finish_reason: str | None
    usage: Usage
    thinking_forced: bool = False
