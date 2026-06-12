from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, assert_never

from localbench._response import ResponseParseError, empty_usage
from localbench._types import ChatMessage, JsonObject, JsonValue, ParsedCompletion, Usage
from localbench.providers._base import (
    Lane,
    ProviderPayloadError,
    ReasoningEffort,
    int_or_none,
)

_ANTHROPIC_VERSION: Final = "2023-06-01"
_PASSTHROUGH_OMIT_KEYS: Final = {
    "max_tokens",
    "thinking_budget",
    "chat_template_kwargs",
}
_THINKING_OMIT_KEYS: Final = _PASSTHROUGH_OMIT_KEYS | {
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "seed",
}
_THINKING_SAMPLING_NOTE: Final = (
    "greedy not enforceable with Anthropic thinking; sampling controls omitted"
)
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
        effort: ReasoningEffort | None = None,
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
        output_effort = _output_effort(decoding, lane, effort)
        omit_keys = _THINKING_OMIT_KEYS if output_effort is not None else _PASSTHROUGH_OMIT_KEYS
        for key, value in decoding.items():
            if key not in omit_keys:
                payload[key] = value
        if output_effort is not None:
            payload["thinking"] = {"type": "adaptive"}
            payload["output_config"] = {"effort": output_effort}
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

    def notes(
        self,
        *,
        effort: ReasoningEffort | None = None,
        decodings: Sequence[JsonObject] = (),
    ) -> list[str]:
        if effort is None:
            return []
        return _effort_notes(effort)


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


def _output_effort(
    decoding: JsonObject,
    lane: Lane,
    effort: ReasoningEffort | None,
) -> str | None:
    if effort is not None:
        return _output_effort_from_reasoning_effort(effort)
    match lane:
        case "capped-thinking":
            thinking_budget = int_or_none(decoding.get("thinking_budget"))
            if thinking_budget is None or thinking_budget <= 0:
                return None
            return "medium"
        case "answer-only" | "api-uncapped":
            return None
        case unreachable:
            assert_never(unreachable)


def _output_effort_from_reasoning_effort(effort: ReasoningEffort) -> str | None:
    match effort:
        case "minimal":
            return None
        case "low":
            return "low"
        case "medium":
            return "medium"
        case "high":
            return "high"
        case "xhigh":
            return "high"
        case unreachable:
            assert_never(unreachable)


def _effort_notes(effort: ReasoningEffort) -> list[str]:
    match effort:
        case "minimal":
            return ["reasoning_effort=minimal mapped to Anthropic thinking off"]
        case "low":
            return [
                _THINKING_SAMPLING_NOTE,
                "reasoning_effort=low mapped to Anthropic output_config.effort=low",
            ]
        case "medium":
            return [
                _THINKING_SAMPLING_NOTE,
                "reasoning_effort=medium mapped to Anthropic output_config.effort=medium",
            ]
        case "high":
            return [
                _THINKING_SAMPLING_NOTE,
                "reasoning_effort=high mapped to Anthropic output_config.effort=high",
            ]
        case "xhigh":
            return [
                _THINKING_SAMPLING_NOTE,
                "reasoning_effort=xhigh mapped to Anthropic output_config.effort=high",
                "reasoning_effort=xhigh clamped to Anthropic high",
            ]
        case unreachable:
            assert_never(unreachable)


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
    usage: Usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    thinking_tokens = _thinking_tokens(value)
    if thinking_tokens is not None:
        usage["reasoning_tokens"] = thinking_tokens
    return usage


def _thinking_tokens(usage: JsonValue) -> int | None:
    if not isinstance(usage, dict):
        return None
    details = usage.get("output_tokens_details")
    if not isinstance(details, dict):
        return None
    return int_or_none(details.get("thinking_tokens"))
