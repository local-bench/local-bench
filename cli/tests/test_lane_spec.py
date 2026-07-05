from __future__ import annotations

import pytest

from localbench.lane_spec import (
    BOUNDED_FINAL_LANE_SPEC_ID,
    BOUNDED_FINAL_V2_LANE_SPEC_ID,
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
    assert lane_spec_digest(BOUNDED_FINAL_LANE_SPEC_ID) == (
        "3a543598bb9c3424a1d2351de2d7d3cc876724be356225b86b627e0ef6b9c398"
    )


def test_bounded_final_v2_lane_spec_uses_per_item_answer_reserve() -> None:
    spec = LANE_SPECS[BOUNDED_FINAL_V2_LANE_SPEC_ID]

    assert spec == {
        "id": "bounded-final-v2",
        "total_cap_source": "suite item max_tokens",
        "answer_reserve_source": "suite item answer_reserve default 1024",
        "think_cap": 8192,
        "think_budget_formula": "min(8192, max(0, T_i - answer_reserve))",
        "answer_budget": "T_i - reasoning_tokens_used",
        "execution_profiles_per_run": 1,
        "scored_text": "final_text_only",
        "sampler_policy": "pinned greedy temp-0 seeded",
    }
    assert lane_spec_digest(BOUNDED_FINAL_V2_LANE_SPEC_ID) == (
        "ab82813dcef91970459b22844ee022e108b436d059b694aacdec916ec19ab5e7"
    )


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


def test_bounded_final_budget_math_supports_per_item_answer_reserve() -> None:
    assert bounded_final_think_budget(16_384, answer_reserve=4_096) == 8_192
    assert bounded_final_think_budget(6_000, answer_reserve=4_096) == 1_904
    assert bounded_final_think_budget(1_024, answer_reserve=4_096) == 0
