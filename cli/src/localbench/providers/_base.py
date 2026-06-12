from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, TypeAlias

from localbench._types import ChatMessage, JsonObject, JsonValue, ParsedCompletion

Lane: TypeAlias = Literal["answer-only", "capped-thinking", "api-uncapped"]
ReasoningEffort: TypeAlias = Literal["minimal", "low", "medium", "high", "xhigh"]
ProviderName: TypeAlias = Literal[
    "local",
    "openai-chat",
    "openai-reasoning",
    "anthropic",
    "gemini",
]


class Provider(Protocol):
    name: str

    def build_payload(
        self,
        model: str,
        messages: list[ChatMessage],
        decoding: JsonObject,
        lane: Lane,
        effort: ReasoningEffort | None = None,
    ) -> JsonObject: ...

    def endpoint_url(self, base: str) -> str: ...

    def headers(self, api_key: str | None) -> dict[str, str]: ...

    def parse_response(self, data: JsonValue) -> ParsedCompletion: ...

    def notes(
        self,
        *,
        effort: ReasoningEffort | None = None,
        decodings: Sequence[JsonObject] = (),
    ) -> list[str]: ...


class ProviderPayloadError(Exception):
    pass


def bearer_headers(api_key: str | None) -> dict[str, str]:
    request_headers = {"content-type": "application/json"}
    if api_key:
        request_headers["authorization"] = f"Bearer {api_key}"
    return request_headers


def chat_completions_url(base: str) -> str:
    return f"{base.rstrip('/')}/chat/completions"


def int_or_none(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
