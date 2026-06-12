from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from localbench._response import parse_chat_completion
from localbench._types import ChatMessage, JsonObject, JsonValue, ParsedCompletion, Usage
from localbench.providers._base import (
    Lane,
    ReasoningEffort,
    bearer_headers,
    chat_completions_url,
    int_or_none,
)

_REASONING_OMIT_KEYS: Final = {
    "max_tokens",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "seed",
    "chat_template_kwargs",
    "thinking_budget",
}
_REASONING_NOTE: Final = "greedy not enforceable; provider-default sampling"


@dataclass(frozen=True, slots=True)
class OpenAIChatProvider:
    name: str = "openai-chat"

    def build_payload(
        self,
        model: str,
        messages: list[ChatMessage],
        decoding: JsonObject,
        lane: Lane,
        effort: ReasoningEffort | None = None,
    ) -> JsonObject:
        return {"model": model, "messages": messages, **decoding}

    def endpoint_url(self, base: str) -> str:
        return chat_completions_url(base)

    def headers(self, api_key: str | None) -> dict[str, str]:
        return bearer_headers(api_key)

    def parse_response(self, data: JsonValue) -> ParsedCompletion:
        return parse_chat_completion(data)

    def notes(
        self,
        *,
        effort: ReasoningEffort | None = None,
        decodings: Sequence[JsonObject] = (),
    ) -> list[str]:
        return []


@dataclass(frozen=True, slots=True)
class GeminiProvider:
    name: str = "gemini"

    def build_payload(
        self,
        model: str,
        messages: list[ChatMessage],
        decoding: JsonObject,
        lane: Lane,
        effort: ReasoningEffort | None = None,
    ) -> JsonObject:
        payload: JsonObject = {"model": model, "messages": messages, **decoding}
        if effort is not None:
            payload["reasoning_effort"] = effort
        return payload

    def endpoint_url(self, base: str) -> str:
        return chat_completions_url(base)

    def headers(self, api_key: str | None) -> dict[str, str]:
        return bearer_headers(api_key)

    def parse_response(self, data: JsonValue) -> ParsedCompletion:
        return parse_chat_completion(data)

    def notes(
        self,
        *,
        effort: ReasoningEffort | None = None,
        decodings: Sequence[JsonObject] = (),
    ) -> list[str]:
        if effort is None:
            return []
        return [f"reasoning_effort={effort} passed through Gemini OpenAI-compatible body"]


@dataclass(frozen=True, slots=True)
class OpenAIReasoningProvider:
    name: str = "openai-reasoning"

    def build_payload(
        self,
        model: str,
        messages: list[ChatMessage],
        decoding: JsonObject,
        lane: Lane,
        effort: ReasoningEffort | None = None,
    ) -> JsonObject:
        payload: JsonObject = {"model": model, "messages": messages}
        max_tokens = int_or_none(decoding.get("max_tokens"))
        if max_tokens is not None:
            payload["max_completion_tokens"] = max_tokens
        for key, value in decoding.items():
            if key not in _REASONING_OMIT_KEYS:
                payload[key] = value
        if effort is not None:
            payload["reasoning_effort"] = effort
        return payload

    def endpoint_url(self, base: str) -> str:
        return chat_completions_url(base)

    def headers(self, api_key: str | None) -> dict[str, str]:
        return bearer_headers(api_key)

    def parse_response(self, data: JsonValue) -> ParsedCompletion:
        parsed = parse_chat_completion(data)
        usage: Usage = {
            "prompt_tokens": parsed.usage["prompt_tokens"],
            "completion_tokens": parsed.usage["completion_tokens"],
            "total_tokens": parsed.usage["total_tokens"],
        }
        reasoning_tokens = _reasoning_tokens(data)
        if reasoning_tokens is not None:
            usage["reasoning_tokens"] = reasoning_tokens
        return ParsedCompletion(
            response_text=parsed.response_text,
            reasoning_text=parsed.reasoning_text,
            finish_reason=parsed.finish_reason,
            usage=usage,
        )

    def notes(
        self,
        *,
        effort: ReasoningEffort | None = None,
        decodings: Sequence[JsonObject] = (),
    ) -> list[str]:
        notes = [_REASONING_NOTE]
        if effort is not None:
            notes.append(f"reasoning_effort={effort} sent as OpenAI reasoning_effort")
        return notes


def _reasoning_tokens(data: JsonValue) -> int | None:
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    details = usage.get("completion_tokens_details")
    if not isinstance(details, dict):
        return None
    return int_or_none(details.get("reasoning_tokens"))
