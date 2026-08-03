from __future__ import annotations

from localbench._types import JsonObject
from localbench.check.grading import grade_response


def test_stop_token_scores_correct_answer_with_protocol_flag() -> None:
    source: JsonObject = {
        "category": "stop-token",
        "gate_kind": "validity",
        "expected": {"forbidden_suffix": "OMEGA", "required": "ALPHA", "stop_marker": "<END>"},
    }

    result = grade_response(
        "sanity-gates",
        source,
        {"text": "ALPHA<END>", "protocol_flag": "think-markers-absent"},
    )

    assert result["correct"] is True


def test_template_canary_scores_correct_echo_with_protocol_flag() -> None:
    source: JsonObject = {
        "category": "template-canary",
        "gate_kind": "validity",
        "expected": {"answer": "CANARY-Q3", "template_role": "assistant"},
    }

    result = grade_response(
        "sanity-gates",
        source,
        {"text": "CANARY-Q3", "protocol_flag": "think-markers-malformed"},
    )

    assert result["correct"] is True


def test_repetition_scores_correct_bounded_sequence_with_protocol_flag() -> None:
    source: JsonObject = {
        "category": "repetition",
        "gate_kind": "behavioral",
        "expected": {
            "answer": "A B A B C STOP",
            "stop_marker": "STOP",
            "loop_detection": {
                "max_occurrences": 2,
                "ngram_size": 2,
                "tokenization": "unicode-word-punctuation-v1",
            },
        },
    }

    result = grade_response(
        "sanity-gates",
        source,
        {"text": "A B A B C STOP", "protocol_flag": "think-markers-absent"},
    )

    assert result["correct"] is True
    detail = result["detail"]
    assert isinstance(detail, dict) and detail["loop_detected"] is False


def test_long_context_scores_correct_needle_with_protocol_flag() -> None:
    source: JsonObject = {
        "category": "long-context-needle",
        "gate_kind": "behavioral",
        "expected": {"answer": "BRISBANE-8192"},
    }

    result = grade_response(
        "sanity-gates",
        source,
        {"text": "BRISBANE-8192", "protocol_flag": "think-markers-absent"},
    )

    assert result["correct"] is True


def test_budget_control_requires_inline_evidence_within_declared_budget() -> None:
    source: JsonObject = {
        "category": "budget-control",
        "gate_kind": "validity",
        "expected": {"answer": "red", "answer_budget": 512, "think_budget": 4096},
    }
    absent = grade_response(
        "sanity-gates",
        source,
        {
            "text": "red",
            "protocol_flag": "think-markers-absent",
            "reasoning_text": "reasoning without inline markers",
            "usage": {"reasoning_tokens": 12},
        },
    )
    exhausted = grade_response(
        "sanity-gates",
        source,
        {
            "text": "red",
            "protocol_flag": "think-budget-exhausted",
            "reasoning_text": "<think>bounded reasoning",
            "usage": {"reasoning_tokens": 4096},
        },
    )
    over_budget = grade_response(
        "sanity-gates",
        source,
        {
            "text": "red",
            "protocol_flag": None,
            "reasoning_text": "<think>unbounded reasoning",
            "usage": {"reasoning_tokens": 4097},
        },
    )

    assert absent["correct"] is False
    assert exhausted["correct"] is True
    assert over_budget["correct"] is False


def test_determinism_compares_frozen_fields_despite_protocol_flag() -> None:
    source: JsonObject = {
        "category": "determinism",
        "gate_kind": "validity",
        "expected": {"answer": "101"},
    }
    first: JsonObject = {
        "finish_reason": "stop",
        "parsed_tool_calls": [],
        "protocol_flag": "think-markers-absent",
        "scorer_result": {"correct": True},
        "server_start_id": "one",
        "text": "101",
        "token_ids": [1, 0, 1],
    }
    second: JsonObject = {**first, "server_start_id": "two"}

    result = grade_response("sanity-gates", source, first, repeated_generation=second)

    assert result["correct"] is True
