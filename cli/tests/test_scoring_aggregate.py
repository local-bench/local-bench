from __future__ import annotations

import pytest

from localbench._scoring import ScoredItem, aggregate, composite
from localbench.scoring.signed_score import signed_score


def test_aggregate_when_below_chance_stores_signed_score_and_lowers_composite() -> None:
    # Given a below-chance multiple-choice bench and a perfect math bench.
    below_chance = aggregate("mmlu_pro", [_scored_item(correct=False)], baseline=0.10)
    perfect = aggregate("genmath", [_scored_item(correct=True)], baseline=0.0)

    # When the run composite is computed from stored per-bench aggregates.
    result = composite({"mmlu_pro": below_chance, "genmath": perfect})

    # Then the stored score stays signed, so the composite is lower than a clamped mean.
    expected_below = signed_score(0.0, chance=0.10)
    assert below_chance["chance_corrected"] == pytest.approx(expected_below)
    assert result == pytest.approx((expected_below + 1.0) / 2.0)
    assert result < 0.5


def _scored_item(*, correct: bool) -> ScoredItem:
    return {
        "id": "item-1",
        "bench": "mmlu_pro",
        "response_text": "A",
        "extracted": "A",
        "correct": correct,
        "finish_reason": "stop",
        "latency_seconds": 0.0,
        "started_at": "2026-06-12T00:00:00+00:00",
        "finished_at": "2026-06-12T00:00:00+00:00",
        "attempts": 1,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "error": None,
    }
