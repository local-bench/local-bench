from __future__ import annotations

from collections.abc import Sequence

import pytest

from localbench._scoring import BenchAggregate, composite
from localbench._types import JsonObject
from localbench.scoring import board_scoring
from localbench.scoring.axis_status import axis_status_for_benches
from localbench.scoring.axes import web_composite_weights
from localbench.submissions.foundation_scores import axis_projection, score_summary


def test_normal_run_composite_honors_facets_under_skewed_item_counts() -> None:
    benches = _skewed_tool_use_benches()

    assert composite(benches) == pytest.approx(10 / 17)


def test_submission_projection_honors_facets_under_skewed_item_counts() -> None:
    benches = _skewed_tool_use_benches()
    status = axis_status_for_benches(benches)

    projection = axis_projection(benches, status)

    assert projection["tool_use"]["score"] == pytest.approx(10 / 17, abs=1e-4)
    assert projection["tool_use"]["n"] == 146


def test_board_point_ci_and_source_allocation_honor_facets() -> None:
    benches = _json_benches(_skewed_tool_use_benches())
    items = [
        *_items("appworld_c", [True] * 96),
        *_items("bfcl_multi_turn_base", [False] * 50),
        *_items("tc_json_v1", [False] * 330),
    ]

    axes, samples = board_scoring._axes_and_samples(benches, items, {}, 10)
    source_weights = board_scoring._source_weights_for_composite(
        samples,
        axes,
        web_composite_weights(),
    )

    assert axes["tool_use"]["point_raw"] == pytest.approx(10 / 17)
    assert axes["tool_use"]["raw_accuracy"] == pytest.approx(10 / 17)
    assert source_weights["appworld_c"] == pytest.approx(2 / 17)
    assert source_weights["bfcl_multi_turn_base"] == pytest.approx(7 / 85)
    assert "tc_json_v1" not in source_weights


def test_missing_tool_use_facet_fails_closed_in_all_cli_paths() -> None:
    benches = _skewed_tool_use_benches()
    del benches["bfcl_multi_turn_base"]
    status = axis_status_for_benches(benches)
    board_axes, samples = board_scoring._axes_and_samples(
        _json_benches(benches),
        [
            *_items("appworld_c", [True] * 96),
            *_items("tc_json_v1", [False] * 330),
        ],
        {},
        5,
    )

    assert status["axes"]["tool_use"]["status"] == "not_measured"
    assert axis_projection(benches, status)["tool_use"]["score"] is None
    assert score_summary(benches, status)["composite_full"] is None
    assert "tool_use" not in board_axes
    assert board_scoring._strict_composite(
        samples,
        board_axes,
        5,
        required_axes=frozenset({"tool_use"}),
        weights=web_composite_weights(),
    ) is None


def test_experimental_benches_never_enter_composite() -> None:
    weighted = _skewed_tool_use_benches()
    with_diagnostics = {
        **weighted,
        "bfcl": _aggregate(300, 1.0),
        "bfcl_multi_turn_long_context": _aggregate(50, 1.0),
    }

    assert composite(with_diagnostics) == pytest.approx(composite(weighted))
    assert composite(
        {
            "bfcl": _aggregate(300, 1.0),
            "bfcl_multi_turn_long_context": _aggregate(50, 1.0),
            "tc_json_v1": _aggregate(330, 1.0),
        },
    ) == 0.0


def _skewed_tool_use_benches() -> dict[str, BenchAggregate]:
    return {
        "appworld_c": _aggregate(96, 1.0),
        "bfcl_multi_turn_base": _aggregate(50, 0.0),
        "tc_json_v1": _aggregate(330, 0.0),
    }


def _aggregate(n: int, score: float) -> BenchAggregate:
    return {
        "n": n,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": score,
        "chance_corrected": score,
        "termination_rate": 1.0,
        "conditional_accuracy": score,
    }


def _json_benches(benches: dict[str, BenchAggregate]) -> JsonObject:
    return {bench: dict(aggregate) for bench, aggregate in benches.items()}


def _items(bench: str, correct: Sequence[bool]) -> list[JsonObject]:
    return [
        {"id": f"{bench}-{index}", "bench": bench, "correct": value, "error": None}
        for index, value in enumerate(correct)
    ]
