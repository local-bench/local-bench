from __future__ import annotations

import pytest

from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.parser import AssistantActionParser
from localbench.scoring.agentic_exec.types import FailureReason


def test_parser_accepts_exactly_one_tool_call_json_object() -> None:
    # Given the strict plain-text JSON action parser.
    parser = AssistantActionParser(AgenticExecConfig())

    # When a model emits one object and no prose.
    outcome = parser.parse_turn('{"type":"tool_call","tool":"orders.get_order","arguments":{"order_id":"o-100"}}')

    # Then the action is parsed into the protocol object.
    assert outcome.action is not None
    assert outcome.failure is None
    assert outcome.action.type == "tool_call"
    assert outcome.action.tool == "orders.get_order"
    assert outcome.action.arguments == {"order_id": "o-100"}


def test_parser_accepts_final_answer_json_object() -> None:
    # Given the strict parser.
    parser = AssistantActionParser(AgenticExecConfig())

    # When the model emits a final answer action.
    outcome = parser.parse_turn('{"type":"final_answer","answer":{"total":12.5}}')

    # Then the final answer payload is preserved.
    assert outcome.action is not None
    assert outcome.failure is None
    assert outcome.action.type == "final_answer"
    assert outcome.action.answer == {"total": 12.5}


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"type":"tool_call"} trailing',
        '[{"type":"tool_call","tool":"orders.get_order","arguments":{}}]',
    ],
)
def test_parser_allows_one_retry_after_invalid_json(raw: str) -> None:
    # Given a fresh parser.
    parser = AssistantActionParser(AgenticExecConfig())

    # When invalid JSON is seen once.
    first = parser.parse_turn(raw)

    # Then it returns a deterministic retryable parse failure.
    assert first.action is None
    assert first.failure is not None
    assert first.failure.reason is FailureReason.INVALID_JSON
    assert first.failure.hard_fail is False

    # When the next assistant turn is malformed again.
    second = parser.parse_turn(raw)

    # Then the parser hard-fails by the one-retry policy.
    assert second.action is None
    assert second.failure is not None
    assert second.failure.reason is FailureReason.MAX_RETRIES_EXCEEDED
    assert second.failure.hard_fail is True


def test_parser_allows_one_retry_after_schema_error() -> None:
    # Given a fresh parser.
    parser = AssistantActionParser(AgenticExecConfig())

    # When JSON parses but violates the action schema.
    first = parser.parse_turn('{"type":"tool_call","tool":"orders.get_order","arguments":[]}')

    # Then schema errors consume the one deterministic retry.
    assert first.failure is not None
    assert first.failure.reason is FailureReason.SCHEMA_ERROR
    assert first.failure.hard_fail is False

    second = parser.parse_turn('{"type":"tool_call","tool":"orders.get_order","arguments":[]}')
    assert second.failure is not None
    assert second.failure.reason is FailureReason.MAX_RETRIES_EXCEEDED
    assert second.failure.hard_fail is True


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        ("timeout", FailureReason.TIMEOUT),
        ("length", FailureReason.LENGTH),
    ],
)
def test_parser_hard_fails_generation_stop_reasons(
    finish_reason: str,
    expected: FailureReason,
) -> None:
    # Given a parser and a generated JSON payload.
    parser = AssistantActionParser(AgenticExecConfig())

    # When the model stream ended for a hard-fail reason.
    outcome = parser.parse_turn(
        '{"type":"final_answer","answer":"done"}',
        finish_reason=finish_reason,
    )

    # Then parsing is skipped and the failure reason is explicit.
    assert outcome.action is None
    assert outcome.failure is not None
    assert outcome.failure.reason is expected
    assert outcome.failure.hard_fail is True


def test_failure_reason_enum_covers_agentic_failure_policy() -> None:
    # Given the spec failure taxonomy.
    expected = {
        "invalid_json",
        "schema_error",
        "timeout",
        "length",
        "max_retries_exceeded",
        "forbidden_tool",
        "max_turns_exceeded",
        "max_tool_calls_exceeded",
        "loop_guard",
        "tool_error",
        "verifier_failed",
        "collateral_damage",
    }

    # When enumerating parser/runner failure reasons.
    actual = {reason.value for reason in FailureReason}

    # Then every required failure path is named.
    assert expected <= actual
