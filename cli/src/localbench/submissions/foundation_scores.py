from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Final

from localbench._scoring import BenchAggregate, composite
from localbench._types import JsonObject, JsonValue
from localbench.scoring.axes import (
    AXES,
    STATIC_SUITE_V3_INDEX_VERSION as STATIC_SUITE_INDEX_VERSION,
    STATIC_SUITE_V3_WEIGHTS as STATIC_SUITE_WEIGHTS,
    Axis,
    materialize_facet_samples,
    static_suite_v3_domain_weights as static_suite_domain_weights,
)
from localbench.scoring.axis_status import AxisStatusBlock
from localbench.suite_release import coverage_profile_for_benches

_SCORE_PRECISION: Final = 4
_WEIGHT_PRECISION: Final = 3
_FULL_EXEC_PROFILE_ID: Final = "full-exec-6axis-v1"
_FULL_EXEC_REQUIRED_AXES: Final = frozenset(
    {"knowledge", "instruction_following", "math", "agentic", "tool_calling", "coding"},
)
_FULL_EXEC_WEIGHTS: Final[dict[str, float]] = {
    "knowledge": 0.225,
    "instruction_following": 0.225,
    "math": 0.075,
    "agentic": 0.25,
    "coding": 0.225,
}
_FULL_EXEC_BENCHES: Final[dict[str, tuple[str, ...]]] = {
    "knowledge": ("mmlu_pro",),
    "instruction_following": ("ifbench",),
    "math": ("olymmath_hard", "amo"),
    "agentic": ("appworld_c",),
    "coding": ("bigcodebench_hard",),
}


def score_summary(
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
    *,
    suite_axes: Mapping[str, JsonValue] | None = None,
) -> JsonObject:
    profile = coverage_profile_for_benches(set(benches))
    full_exec = profile.profile_id == _FULL_EXEC_PROFILE_ID
    measured = (
        _full_exec_measured_weight(axis_status)
        if full_exec
        else _measured_headline_weight(axis_status)
    )
    raw_partial = (
        _full_exec_composite(benches, axis_status)
        if full_exec
        else composite(benches, axis_status, suite_axes)
    )
    partial = _round_score(min(1.0, max(0.0, raw_partial)))
    headline_complete = (
        _full_exec_complete(axis_status)
        if full_exec
        else measured >= 1.0
    )
    summary: JsonObject = {
        "headline_score": partial if headline_complete else None,
        "partial_composite": partial,
        "partial_composite_scope": "measured_headline_axes",
        "measured_headline_weight": _round_fixed(measured, _WEIGHT_PRECISION),
        "missing_headline_weight": _round_fixed(max(0.0, 1.0 - measured), _WEIGHT_PRECISION),
        "known_headline_contribution": _round_score(partial * measured),
        "rank_scope": profile.rank_scope,
        "composite_static": _strict_composite(
            benches,
            axis_status,
            suite_axes,
            required_axes=frozenset(STATIC_SUITE_WEIGHTS),
            weights=static_suite_domain_weights(),
        ),
        "composite_full": (
            partial
            if full_exec and headline_complete
            else _strict_composite(
                benches,
                axis_status,
                suite_axes,
                required_axes=frozenset(axis.key for axis in AXES if axis.role == "headline"),
                weights=None,
            )
        ),
    }
    if summary["composite_static"] is not None:
        summary["static_index_version"] = STATIC_SUITE_INDEX_VERSION
    return summary


def axis_projection(
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
    *,
    coverage_profile_id: str | None = None,
) -> JsonObject:
    projection: JsonObject = {}
    inferred_profile_id = coverage_profile_for_benches(set(benches)).profile_id
    full_exec = (coverage_profile_id or inferred_profile_id) == _FULL_EXEC_PROFILE_ID
    for axis in AXES:
        aggregate = (
            benches.get("appworld_c")
            if full_exec and axis.key == "tool_use"
            else _axis_aggregate(axis, benches)
        )
        status_key = (
            "agentic"
            if full_exec and axis.key == "tool_use"
            else "tool_calling"
            if full_exec and axis.key == "call_formatting"
            else axis.key
        )
        status = axis_status["axes"].get(status_key, {"status": "not_measured"})
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


def _full_exec_complete(axis_status: AxisStatusBlock) -> bool:
    return all(
        axis_status["axes"].get(axis, {}).get("status") == "measured"
        for axis in _FULL_EXEC_REQUIRED_AXES
    )


def _full_exec_measured_weight(axis_status: AxisStatusBlock) -> float:
    return sum(
        weight
        for axis, weight in _FULL_EXEC_WEIGHTS.items()
        if axis_status["axes"].get(axis, {}).get("status") == "measured"
    )


def _full_exec_composite(
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
) -> float:
    weighted_score = 0.0
    measured_weight = 0.0
    for axis, weight in _FULL_EXEC_WEIGHTS.items():
        if axis_status["axes"].get(axis, {}).get("status") != "measured":
            continue
        score = _pooled_score(benches, _FULL_EXEC_BENCHES[axis])
        if score is None:
            continue
        weighted_score += score * weight
        measured_weight += weight
    if not measured_weight:
        return 0.0
    return min(1.0, max(0.0, weighted_score / measured_weight))


def _pooled_score(
    benches: Mapping[str, BenchAggregate],
    names: tuple[str, ...],
) -> float | None:
    selected = [benches[name] for name in names if name in benches]
    n = sum(aggregate["n"] for aggregate in selected)
    if n <= 0:
        return None
    return sum(aggregate["chance_corrected"] * aggregate["n"] for aggregate in selected) / n


def _strict_composite(
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
    suite_axes: Mapping[str, JsonValue] | None,
    *,
    required_axes: frozenset[str],
    weights: Mapping[str, float] | None,
) -> float | None:
    if not all(axis_status["axes"].get(axis, {}).get("status") == "measured" for axis in required_axes):
        return None
    return _round_score(composite(benches, axis_status, suite_axes, weights=weights))


def _axis_aggregate(
    axis: Axis,
    benches: Mapping[str, BenchAggregate],
) -> BenchAggregate | None:
    facet_material = materialize_facet_samples(axis, benches)
    if axis.facets:
        if facet_material is None:
            return None
        selected = list(facet_material[0].values())
    else:
        selected = [benches[bench] for bench in (*axis.benches, *axis.legacy_benches) if bench in benches]
    if not selected:
        return None
    n = sum(item["n"] for item in selected)
    if n <= 0:
        return None
    aggregate: BenchAggregate = {
        "n": n,
        "n_errors": sum(item["n_errors"] for item in selected),
        "n_extraction_failures": sum(item["n_extraction_failures"] for item in selected),
        "raw_accuracy": sum(item["raw_accuracy"] * item["n"] for item in selected) / n,
        "chance_corrected": sum(item["chance_corrected"] * item["n"] for item in selected) / n,
        "termination_rate": sum(item["termination_rate"] * item["n"] for item in selected) / n,
        "conditional_accuracy": sum(item["conditional_accuracy"] * item["n"] for item in selected) / n,
    }
    if facet_material is not None:
        for key in ("raw_accuracy", "chance_corrected", "termination_rate", "conditional_accuracy"):
            aggregate[key] = sum(
                facet_material[1][bench] * item[key]
                for bench, item in facet_material[0].items()
            )
    return aggregate


def _round_score(value: float) -> float:
    return _round_fixed(value, _SCORE_PRECISION)


def _round_fixed(value: float, places: int) -> float:
    quant = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))
