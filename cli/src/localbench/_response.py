"""OpenAI-compatible response parsing helpers."""

from __future__ import annotations

from localbench._types import JsonValue, ParsedCompletion, Usage


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
    if not isinstance(content, str):
        raise ResponseParseError("choice message content is missing")
    finish_reason = choice.get("finish_reason")
    return ParsedCompletion(
        response_text=content,
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        usage=parse_usage(data.get("usage")),
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


def _int_or_none(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
