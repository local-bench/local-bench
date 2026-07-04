"""Parser behavior for reasoning models (vLLM reasoning_content split)."""

from __future__ import annotations

import pytest

from localbench._response import ResponseParseError, parse_chat_completion


def _resp(message: dict, finish_reason: str | None = "stop") -> dict:
    return {"choices": [{"message": message, "finish_reason": finish_reason}]}


def test_plain_content_is_used_as_response_text() -> None:
    parsed = parse_chat_completion(_resp({"content": "Answer: C"}))
    assert parsed.response_text == "Answer: C"
    assert parsed.reasoning_text is None


def test_reasoning_split_keeps_content_as_answer_and_captures_reasoning() -> None:
    parsed = parse_chat_completion(
        _resp({"content": "Answer: B", "reasoning_content": "long chain of thought"}),
    )
    assert parsed.response_text == "Answer: B"
    assert parsed.reasoning_text == "long chain of thought"


def test_truncated_mid_think_does_not_raise_and_falls_back_to_reasoning() -> None:
    # Thinking model cut off at the token wall: empty content, only reasoning, finish=length.
    parsed = parse_chat_completion(
        _resp({"content": "", "reasoning_content": "still thinking..."}, finish_reason="length"),
    )
    assert parsed.finish_reason == "length"
    assert parsed.reasoning_text == "still thinking..."
    # No final answer → response_text falls back to reasoning so the transcript is preserved;
    # MCQ/math extraction will fail on it and score the item wrong (correct behavior).
    assert parsed.response_text == "still thinking..."


def test_empty_message_with_length_finish_is_recorded_not_raised() -> None:
    parsed = parse_chat_completion(_resp({"content": None}, finish_reason="length"))
    assert parsed.response_text == ""
    assert parsed.reasoning_text is None


def test_empty_message_without_finish_reason_still_raises() -> None:
    with pytest.raises(ResponseParseError):
        parse_chat_completion(_resp({"content": None}, finish_reason=None))
