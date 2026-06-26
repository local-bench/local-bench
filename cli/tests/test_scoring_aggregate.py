from __future__ import annotations

import pytest

from localbench._scoring import ScoredItem, aggregate, composite
from localbench.scoring.signed_score import signed_delta, signed_score


def test_aggregate_when_below_chance_stores_signed_score_and_lowers_composite() -> None:
    # Given a below-chance knowledge bench and a perfect instruction bench (both
    # HEADLINE axes, so both enter the composite under METHODOLOGY-v1.2 §3).
    below_chance = aggregate("mmlu_pro", [_scored_item(correct=False)], baseline=0.10)
    perfect = aggregate("ifbench", [_scored_item(correct=True)], baseline=0.0)

    # When the run composite is computed from stored per-bench aggregates.
    result = composite({"mmlu_pro": below_chance, "ifbench": perfect})

    # Then the stored score stays signed, so the composite is lower than a clamped mean.
    expected_below = signed_score(0.0, chance=0.10)
    assert below_chance["chance_corrected"] == pytest.approx(expected_below)
    assert result == pytest.approx(((0.15 * expected_below) + (0.25 * 1.0)) / 0.40)
    assert result < 0.625


def test_signed_delta_when_chance_corrected_matches_aggregate_score_difference() -> None:
    # Given paired item correctness on a chance-corrected multiple-choice bench.
    chance = 0.10
    run_a = [True, True, False, True, False]
    run_b = [True, False, False, False, False]

    # When averaging per-item signed deltas and differencing aggregate signed scores.
    mean_delta = sum(
        signed_delta(int(correct_a) - int(correct_b), chance=chance)
        for correct_a, correct_b in zip(run_a, run_b, strict=True)
    ) / len(run_a)
    aggregate_delta = signed_score(_mean_bool(run_a), chance=chance) - signed_score(
        _mean_bool(run_b),
        chance=chance,
    )

    # Then linear chance correction makes the two paths exactly equivalent.
    assert mean_delta == pytest.approx(aggregate_delta)


def test_aggregate_reports_termination_and_conditional_accuracy() -> None:
    # Given post-gate scored items with successes, a non-terminating failure, and an error.
    items = [
        _scored_item(id="correct-1", correct=True, finish_reason="stop"),
        _scored_item(id="correct-2", correct=True, finish_reason="stop"),
        _scored_item(id="wrong-terminated", correct=False, finish_reason="stop"),
        _scored_item(id="wrong-length", correct=False, finish_reason="length"),
        _scored_item(id="errored", correct=False, finish_reason=None, error="timeout"),
    ]

    # When aggregating the bench.
    result = aggregate("mmlu_pro", items, baseline=0.10)

    # Then termination and conditional accuracy decompose raw accuracy.
    assert result["raw_accuracy"] == pytest.approx(2 / 5)
    assert result["termination_rate"] == pytest.approx(3 / 5)
    assert result["conditional_accuracy"] == pytest.approx(2 / 3)
    assert all(item["finish_reason"] != "length" for item in items if item["correct"])
    assert result["raw_accuracy"] == pytest.approx(
        result["termination_rate"] * result["conditional_accuracy"],
    )


def _scored_item(
    *,
    correct: bool,
    id: str = "item-1",
    finish_reason: str | None = "stop",
    error: str | None = None,
) -> ScoredItem:
    return {
        "id": id,
        "bench": "mmlu_pro",
        "response_text": None if error is not None else "A",
        "extracted": None if error is not None else "A",
        "correct": correct,
        "finish_reason": finish_reason,
        "latency_seconds": 0.0,
        "started_at": "2026-06-12T00:00:00+00:00",
        "finished_at": "2026-06-12T00:00:00+00:00",
        "attempts": 1,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "error": error,
    }


def _mean_bool(values: list[bool]) -> float:
    return sum(1 for value in values if value) / len(values)
