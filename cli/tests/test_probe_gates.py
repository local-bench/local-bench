from __future__ import annotations

import math

import pytest

from localbench.probe.gates import (
    differential_parse_fail_gate,
    is_redundant_with_headline,
    parse_fail_gate,
    pearson_r,
    proportion_upper_bound,
    spread_ci,
    spread_gate,
    wilson_interval,
)


def test_wilson_interval_brackets_the_point_and_handles_degenerate_n() -> None:
    low, high = wilson_interval(50, 100)
    assert low < 0.5 < high
    assert 0.39 < low < 0.41 and 0.59 < high < 0.61
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_zero_observed_failures_in_a_small_sample_still_fails_the_5pct_gate() -> None:
    # The oracle's exact example: 0/58 leaves a ~6% upper bound, so "0% observed" is NOT
    # evidence the parse-fail rate is under 5%.
    upper = proportion_upper_bound(0, 58)
    assert 0.05 < upper < 0.07
    passed, gate_upper = parse_fail_gate(0, 58)
    assert passed is False
    assert gate_upper == upper
    # A large clean sample does pass.
    assert parse_fail_gate(1, 1000)[0] is True
    # Unknown N fails closed.
    assert proportion_upper_bound(0, 0) == 1.0


def test_spread_ci_is_a_difference_of_independent_scores() -> None:
    low, high = spread_ci(0.60, 400, 0.20, 400)
    assert low == pytest.approx(0.338, abs=0.01)
    assert high == pytest.approx(0.462, abs=0.01)
    # Unknown N -> infinitely wide so neither keep nor drop can fire.
    assert spread_ci(0.6, 0, 0.2, 400) == (-math.inf, math.inf)


def test_spread_gate_keeps_only_when_the_lower_bound_clears_keep() -> None:
    result = spread_gate(
        frontier=0.60,
        n_frontier=400,
        floor=0.20,
        n_floor=400,
        n_anchors=0,
        n_locals=3,
        n_items=400,
    )
    assert result.verdict == "keep"
    assert result.ci_low >= 0.15
    assert result.n_locals == 3


def test_spread_gate_fewer_than_three_locals_is_triage_not_promotion() -> None:
    result = spread_gate(
        frontier=0.90,
        n_frontier=400,
        floor=0.10,
        n_floor=400,
        n_anchors=2,
        n_locals=2,
        n_items=400,
    )
    assert result.verdict == "triage"
    assert result.n_locals == 2


def test_spread_gate_drops_only_with_a_low_upper_bound_and_enough_items() -> None:
    dropped = spread_gate(
        frontier=0.30,
        n_frontier=2000,
        floor=0.28,
        n_floor=2000,
        n_anchors=0,
        n_locals=3,
        n_items=2000,
    )
    assert dropped.verdict == "drop"
    assert dropped.ci_high < 0.05
    # Same tight CI but a tiny axis -> we refuse the fine drop decision.
    small = spread_gate(
        frontier=0.30,
        n_frontier=2000,
        floor=0.28,
        n_floor=2000,
        n_anchors=0,
        n_locals=3,
        n_items=100,
    )
    assert small.verdict == "inconclusive:small-n"


def test_spread_gate_wide_ci_is_inconclusive() -> None:
    result = spread_gate(
        frontier=0.40,
        n_frontier=60,
        floor=0.20,
        n_floor=60,
        n_anchors=0,
        n_locals=3,
        n_items=60,
    )
    assert result.verdict == "inconclusive:wide-ci"


def test_differential_parse_fail_gate_flags_a_family_gap() -> None:
    assert differential_parse_fail_gate([0.01, 0.02, 0.03])[0] is True
    passed, gap = differential_parse_fail_gate([0.01, 0.20])
    assert passed is False
    assert gap == pytest.approx(0.19)
    assert differential_parse_fail_gate([0.05])[0] is True  # single family -> nothing to compare


def test_pearson_and_redundancy() -> None:
    assert pearson_r([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson_r([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert pearson_r([1, 1, 1], [1, 2, 3]) is None  # zero variance
    assert is_redundant_with_headline([0.1, 0.5, 0.9], [0.11, 0.49, 0.92]) is True
    assert is_redundant_with_headline([0.1, 0.5, 0.9], [0.9, 0.1, 0.5]) is False
