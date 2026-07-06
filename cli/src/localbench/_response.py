"""OpenAI-compatible response parsing helpers."""

from __future__ import annotations

from localbench._types import JsonObject, JsonValue, ParsedCompletion, Usage


class ResponseParseError(Exception):
    """Raised when a chat completion response is not OpenAI-compatible."""


def parse_chat_completion(data: JsonValue) -> ParsedCompletion:
    """Parse the subset of chat completion JSON used by the runner."""
    if not isinstance(data, dict):
        raise ResponseParseError("response JSON is not an object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ResponseParseError("response choices are missing")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ResponseParseError("first choice is not an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ResponseParseError("choice message is missing")
    content = message.get("content")
    # vLLM reasoning parsers (e.g. --reasoning-parser qwen3) split a thinking model's output:
    # the chain-of-thought lands in reasoning_content and only the FINAL answer in content.
    # A response truncated mid-think has empty/null content — that is a real "no answer"
    # (extraction fails → scored wrong), NOT a malformed response. Fall back to reasoning_content
    # so we never lose the transcript, and only raise when the message is genuinely empty AND
    # the model was not cut off.
    content_str = content if isinstance(content, str) and content else None
    reasoning = message.get("reasoning_content")
    reasoning_str = reasoning if isinstance(reasoning, str) and reasoning else None
    finish_reason = choice.get("finish_reason")
    finish_reason = finish_reason if isinstance(finish_reason, str) else None
    if content_str is None and reasoning_str is None:
        if finish_reason is None:
            raise ResponseParseError("choice message content is missing")
        response_text = ""
    else:
        response_text = content_str if content_str is not None else (reasoning_str or "")
    return ParsedCompletion(
        response_text=response_text,
        reasoning_text=reasoning_str,
        finish_reason=finish_reason,
        usage=parse_usage(data.get("usage")),
        server_timings=parse_server_timings(data.get("timings")),
    )


def parse_usage(value: JsonValue | None) -> Usage:
    """Parse usage values, leaving missing fields as unknown."""
    if not isinstance(value, dict):
        return empty_usage()
    return {
        "prompt_tokens": _int_or_none(value.get("prompt_tokens")),
        "completion_tokens": _int_or_none(value.get("completion_tokens")),
        "total_tokens": _int_or_none(value.get("total_tokens")),
    }


def empty_usage() -> Usage:
    """Return an empty usage object with stable keys."""
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


def parse_server_timings(value: JsonValue | None) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    return {"passes": [dict(value)]}


def _int_or_none(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
