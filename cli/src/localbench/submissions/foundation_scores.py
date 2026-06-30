from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Final

from localbench._scoring import BenchAggregate, composite
from localbench._types import JsonObject, JsonValue
from localbench.scoring.axes import AXES, Axis
from localbench.scoring.axis_status import AxisStatusBlock
from localbench.suite_release import coverage_profile_for_benches

_SCORE_PRECISION: Final = 4


def score_summary(
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
    *,
    suite_axes: Mapping[str, JsonValue] | None = None,
) -> JsonObject:
    measured = _measured_headline_weight(axis_status)
    partial = _round_score(composite(benches, axis_status, suite_axes))
    headline_complete = measured >= 1.0
    profile = coverage_profile_for_benches(set(benches))
    return {
        "headline_score": partial if headline_complete else None,
        "partial_composite": partial,
        "partial_composite_scope": "measured_headline_axes",
        "measured_headline_weight": _round_fixed(measured, 2),
        "missing_headline_weight": _round_fixed(max(0.0, 1.0 - measured), 2),
        "known_headline_contribution": _round_score(partial * measured),
        "rank_scope": profile.rank_scope,
    }


def axis_projection(
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
) -> JsonObject:
    projection: JsonObject = {}
    for axis in AXES:
        aggregate = _axis_aggregate(axis, benches)
        status = axis_status["axes"].get(axis.key, {"status": "not_measured"})
        if aggregate is None:
            projection[axis.key] = {
                "score": None,
                "n": 0,
                "ci": None,
                "status": status["status"],
            }
            continue
        projection[axis.key] = {
            "score": _round_score(aggregate["raw_accuracy"]),
            "n": aggregate["n"],
            "ci": None,
            "status": status["status"],
        }
    return projection


def _measured_headline_weight(axis_status: AxisStatusBlock) -> float:
    return sum(
        axis.weight
        for axis in AXES
        if axis.role == "headline"
        and axis_status["axes"].get(axis.key, {}).get("status") == "measured"
    )


def _axis_aggregate(
    axis: Axis,
    benches: Mapping[str, BenchAggregate],
) -> BenchAggregate | None:
    selected = [benches[bench] for bench in axis.benches if bench in benches]
    if not selected:
        return None
    n = sum(item["n"] for item in selected)
    if n <= 0:
        return None
    return {
        "n": n,
        "n_errors": sum(item["n_errors"] for item in selected),
        "n_extraction_failures": sum(item["n_extraction_failures"] for item in selected),
        "raw_accuracy": sum(item["raw_accuracy"] * item["n"] for item in selected) / n,
        "chance_corrected": sum(item["chance_corrected"] * item["n"] for item in selected) / n,
        "termination_rate": sum(item["termination_rate"] * item["n"] for item in selected) / n,
        "conditional_accuracy": sum(item["conditional_accuracy"] * item["n"] for item in selected) / n,
    }


def _round_score(value: float) -> float:
    return _round_fixed(value, _SCORE_PRECISION)


def _round_fixed(value: float, places: int) -> float:
    quant = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))
