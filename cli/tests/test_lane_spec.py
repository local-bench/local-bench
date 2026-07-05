from __future__ import annotations

import pytest

from localbench.lane_spec import (
    BOUNDED_FINAL_LANE_SPEC_ID,
    LANE_SPECS,
    bounded_final_think_budget,
    lane_spec_digest,
)


def test_bounded_final_lane_spec_is_frozen_contract() -> None:
    spec = LANE_SPECS[BOUNDED_FINAL_LANE_SPEC_ID]

    assert spec == {
        "id": "bounded-final-v1",
        "total_cap_source": "suite item max_tokens",
        "min_final": 1024,
        "think_cap": 8192,
        "think_budget_formula": "min(8192, max(0, T_i - 1024))",
        "answer_budget": "T_i - reasoning_tokens_used",
        "execution_profiles_per_run": 1,
        "scored_text": "final_text_only",
        "sampler_policy": "pinned greedy temp-0 seeded",
    }
    assert len(lane_spec_digest(BOUNDED_FINAL_LANE_SPEC_ID)) == 64


@pytest.mark.parametrize(
    ("total_cap", "expected"),
    [
        (0, 0),
        (512, 0),
        (1024, 0),
        (1025, 1),
        (2000, 976),
        (20_000, 8192),
    ],
)
def test_bounded_final_budget_math_uses_suite_item_total_cap(
    total_cap: int,
    expected: int,
) -> None:
    assert bounded_final_think_budget(total_cap) == expected
