from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from localbench._response import ResponseParseError, empty_usage
from localbench._types import ChatMessage, JsonObject, JsonValue, ParsedCompletion, Usage
from localbench.providers._base import Lane, ProviderPayloadError, int_or_none

_ANTHROPIC_VERSION: Final = "2023-06-01"
_PASSTHROUGH_OMIT_KEYS: Final = {
    "max_tokens",
    "thinking_budget",
    "chat_template_kwargs",
}
_STOP_REASON_MAP: Final = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


@dataclass(frozen=True, slots=True)
class AnthropicProvider:
    name: str = "anthropic"

    def build_payload(
        self,
        model: str,
        messages: list[ChatMessage],
        decoding: JsonObject,
        lane: Lane,
    ) -> JsonObject:
        max_tokens = _required_max_tokens(decoding)
        system_text, api_messages = _split_system_messages(messages)
        payload: JsonObject = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if system_text:
            payload["system"] = system_text
        for key, value in decoding.items():
            if key not in _PASSTHROUGH_OMIT_KEYS:
                payload[key] = value
        thinking = _thinking_config(decoding, lane)
        if thinking is not None:
            payload["thinking"] = thinking
        return payload

    def endpoint_url(self, base: str) -> str:
        endpoint = base.rstrip("/")
        if endpoint.endswith("/v1"):
            return f"{endpoint}/messages"
        return f"{endpoint}/v1/messages"

    def headers(self, api_key: str | None) -> dict[str, str]:
        request_headers = {
            "content-type": "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        if api_key:
            request_headers["x-api-key"] = api_key
        return request_headers

    def parse_response(self, data: JsonValue) -> ParsedCompletion:
        if not isinstance(data, dict):
            raise ResponseParseError("Anthropic response JSON is not an object")
        content = data.get("content")
        if not isinstance(content, list):
            raise ResponseParseError("Anthropic response content is missing")
        response_text, reasoning_text = _parse_blocks(content)
        finish_reason = _map_stop_reason(data.get("stop_reason"))
        if not response_text:
            if reasoning_text is not None:
                response_text = reasoning_text
            elif finish_reason is None:
                raise ResponseParseError("Anthropic response text is missing")
        return ParsedCompletion(
            response_text=response_text,
            reasoning_text=reasoning_text,
            finish_reason=finish_reason,
            usage=_parse_usage(data.get("usage")),
        )

    def notes(self) -> list[str]:
        return []


def _required_max_tokens(decoding: JsonObject) -> int:
    max_tokens = int_or_none(decoding.get("max_tokens"))
    if max_tokens is None:
        raise ProviderPayloadError("Anthropic provider requires max_tokens")
    return max_tokens


def _split_system_messages(messages: list[ChatMessage]) -> tuple[str | None, list[JsonObject]]:
    system_parts: list[str] = []
    api_messages: list[JsonObject] = []
    for message in messages:
        role = message["role"]
        content = message["content"]
        if role == "system":
            system_parts.append(content)
        else:
            api_messages.append({"role": role, "content": content})
    system_text = "\n\n".join(system_parts)
    return (system_text if system_text else None), api_messages


def _thinking_config(decoding: JsonObject, lane: Lane) -> JsonObject | None:
    if lane != "capped-thinking":
        return None
    budget = int_or_none(decoding.get("thinking_budget"))
    if budget is None or budget <= 0:
        return None
    return {"type": "enabled", "budget_tokens": budget}


def _parse_blocks(blocks: list[JsonValue]) -> tuple[str, str | None]:
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
        elif block_type == "thinking":
            thinking = block.get("thinking")
            if isinstance(thinking, str) and thinking:
                thinking_parts.append(thinking)
    response_text = "\n".join(text_parts)
    reasoning_text = "\n".join(thinking_parts)
    return response_text, reasoning_text if reasoning_text else None


def _map_stop_reason(value: JsonValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    return _STOP_REASON_MAP.get(value, value)


def _parse_usage(value: JsonValue | None) -> Usage:
    if not isinstance(value, dict):
        return empty_usage()
    prompt_tokens = int_or_none(value.get("input_tokens"))
    completion_tokens = int_or_none(value.get("output_tokens"))
    total_tokens = (
        prompt_tokens + completion_tokens
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
