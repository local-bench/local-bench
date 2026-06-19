from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from localbench._types import JsonValue
from localbench.probe._point_biserial import axis_point_biserial
from localbench.probe.gates import (
    PARSE_FAIL_CEILING,
    differential_parse_fail_gate,
    is_redundant_with_headline,
    parse_fail_gate,
    spread_gate,
)

LabelKind = Literal["anchor", "local"]
Verdict = Literal[
    "keep",
    "triage",
    "drop",
    "drop:frontier-flat",
    "drop:locals-floor",
    "inconclusive:wide-ci",
    "inconclusive:small-n",
]

FRONTIER_FLAT_THRESHOLD = 0.03
LOCALS_FLOOR_THRESHOLD = 0.05


class RunLabelInput(TypedDict):
    label: str
    model_name: str


class AxisResult(TypedDict):
    axis: str
    benches: list[str]
    anchor_min: float | None
    anchor_max: float | None
    anchor_spread: float | None
    local_min: float | None
    local_max: float | None
    overall_spread: float | None
    mean_point_biserial: float | None
    verdict: Verdict
    suggested_weight: float
    # CI-bound gate fields (oracle #4); None on branches where the CI gate did not run.
    spread_ci_low: float | None
    spread_ci_high: float | None
    n_items: int | None
    n_anchors: int
    n_locals: int
    parse_fail_upper: float | None
    parse_fail_ok: bool
    differential_parse_fail_ok: bool
    redundant_with_headline: bool
    notes: NotRequired[list[str]]


@dataclass(frozen=True, slots=True)
class _ModelRun:
    key: str
    model_name: str
    label: LabelKind
    record: Mapping[str, JsonValue]
    composite: float | None


@dataclass(frozen=True, slots=True)
class _AxisScore:
    model_name: str
    label: LabelKind
    score: float
    n: int
    extraction_failures: int
    composite: float | None


def analyze_discrimination(
    run_records: Mapping[str, Mapping[str, JsonValue]],
    axis_map: Mapping[str, Mapping[str, JsonValue]],
    labels: Mapping[str, RunLabelInput],
) -> list[AxisResult]:
    """Measure per-axis between-model discrimination and normalize kept weights.

    Promotion decisions are CONFIDENCE-BOUND (gates.py): an axis is kept only if the lower
    95% bound on the measured floor->frontier spread clears the keep threshold with at
    least three local models; dropped only if the upper bound is below the drop threshold
    with enough items; flagged (and excluded from weighting) if its parse/extraction-failure
    upper bound breaches the ceiling or it is redundant with the headline.
    """
    global_notes: list[str] = []
    models = _labeled_runs(run_records, labels, global_notes)
    results: list[AxisResult] = []
    for axis, spec in axis_map.items():
        notes = list(global_notes)
        benches = _axis_benches(axis, spec, notes)
        scores = _axis_scores(models, benches, notes)
        result = _axis_result(
            axis=axis,
            benches=benches,
            scores=scores,
            point_biserial=axis_point_biserial(models, benches, notes),
            reference_score=_number(spec.get("reference_score")),
            notes=notes,
        )
        results.append(result)
    _assign_weights(results)
    return results


def _labeled_runs(
    records: Mapping[str, Mapping[str, JsonValue]],
    labels: Mapping[str, RunLabelInput],
    notes: list[str],
) -> list[_ModelRun]:
    models: list[_ModelRun] = []
    for run_key, record in records.items():
        raw_label = labels.get(run_key)
        if raw_label is None:
            notes.append(f"skipped run {run_key}: missing label")
            continue
        label = _label_kind(raw_label.get("label"))
        if label is None:
            notes.append(f"skipped run {run_key}: label must be anchor or local")
            continue
        model_name = raw_label.get("model_name") or run_key
        composite = _number(record.get("composite"))
        if composite is None:
            notes.append(
                f"run {run_key}: missing numeric composite; point-biserial skips it",
            )
        models.append(
            _ModelRun(
                key=run_key,
                model_name=model_name,
                label=label,
                record=record,
                composite=composite,
            ),
        )
    return models


def _axis_benches(
    axis: str,
    spec: Mapping[str, JsonValue],
    notes: list[str],
) -> list[str]:
    raw_benches = spec.get("benches")
    if not isinstance(raw_benches, list):
        notes.append(f"axis {axis}: missing benches list")
        return []
    benches: list[str] = []
    for raw_bench in raw_benches:
        if isinstance(raw_bench, str):
            benches.append(raw_bench)
        else:
            notes.append(f"axis {axis}: skipped non-string bench entry")
    return benches


def _axis_scores(
    models: Sequence[_ModelRun],
    benches: Sequence[str],
    notes: list[str],
) -> list[_AxisScore]:
    scores: list[_AxisScore] = []
    for model in models:
        measured = _axis_score(model, benches, notes)
        if measured is not None:
            score, n, extraction_failures = measured
            scores.append(
                _AxisScore(
                    model_name=model.model_name,
                    label=model.label,
                    score=score,
                    n=n,
                    extraction_failures=extraction_failures,
                    composite=model.composite,
                ),
            )
    return scores


def _axis_score(
    model: _ModelRun,
    benches: Sequence[str],
    notes: list[str],
) -> tuple[float, int, int] | None:
    raw_benches = model.record.get("benches")
    if not isinstance(raw_benches, Mapping):
        notes.append(f"{model.model_name}: missing benches object")
        return None
    weighted_total = 0.0
    item_total = 0.0
    extraction_failures = 0
    for bench in benches:
        raw_aggregate = raw_benches.get(bench)
        if not isinstance(raw_aggregate, Mapping):
            notes.append(f"{model.model_name}: skipped missing bench {bench}")
            continue
        score = _number(raw_aggregate.get("chance_corrected"))
        item_count = _positive_number(raw_aggregate.get("n"))
        if score is None or item_count is None:
            notes.append(f"{model.model_name}: skipped incomplete bench {bench}")
            continue
        weighted_total += score * item_count
        item_total += item_count
        extraction_failures += int(_number(raw_aggregate.get("n_extraction_failures")) or 0.0)
    if item_total <= 0:
        notes.append(f"{model.model_name}: no usable benches for axis")
        return None
    return (weighted_total / item_total, int(item_total), extraction_failures)


def _axis_result(
    *,
    axis: str,
    benches: list[str],
    scores: Sequence[_AxisScore],
    point_biserial: float | None,
    reference_score: float | None = None,
    notes: list[str],
) -> AxisResult:
    anchor_values = [score.score for score in scores if score.label == "anchor"]
    local_values = [score.score for score in scores if score.label == "local"]
    all_values = [score.score for score in scores]
    anchor_spread = _spread(anchor_values)
    overall_spread = _spread(all_values)
    local_max = max(local_values) if local_values else None
    anchor_min = min(anchor_values) if anchor_values else None
    anchor_max = max(anchor_values) if anchor_values else None
    n_anchors = len({score.model_name for score in scores if score.label == "anchor"})
    n_locals = len({score.model_name for score in scores if score.label == "local"})

    # Defaults for the CI-gate fields (only branch 5 populates the CI bounds).
    spread_ci_low: float | None = None
    spread_ci_high: float | None = None
    n_items: int | None = None
    parse_fail_upper, parse_fail_ok = _axis_parse_fail(scores)
    differential_parse_fail_ok, differential_gap = _axis_differential_parse_fail(scores)
    redundant = _axis_redundant(scores)

    if not differential_parse_fail_ok:
        notes.append(
            f"axis {axis}: parse-fail rate differs by {differential_gap:.0%} across families "
            "(possible formatting artifact, not capability)",
        )
    if redundant:
        notes.append(
            f"axis {axis}: near-duplicate of the headline composite (|r| >= 0.98); "
            "verify it adds incremental information on the full panel before weighting",
        )

    if local_values and all(value <= LOCALS_FLOOR_THRESHOLD for value in local_values):
        verdict: Verdict = "drop:locals-floor"
    elif not local_values:
        verdict = "triage"
    elif n_anchors >= 2 and anchor_spread is not None and anchor_spread <= FRONTIER_FLAT_THRESHOLD:
        verdict = "drop:frontier-flat"
    elif (
        n_anchors == 0
        and reference_score is not None
        and reference_score - max(all_values) <= FRONTIER_FLAT_THRESHOLD
    ):
        # No anchors, but the strongest model sits within FRONTIER_FLAT of the published
        # ceiling -> no headroom -> saturated. A NON-saturated published ceiling does NOT
        # block promotion; it falls through to the local-range CI gate below.
        notes.append(
            f"axis {axis}: strongest model within {FRONTIER_FLAT_THRESHOLD:.2f} of published "
            f"ceiling {reference_score:.2f} (REPORTED) -> saturated",
        )
        verdict = "drop:frontier-flat"
    else:
        # CI spread gate on the MEASURED range (anchor-free): promotes on >= 3 local models +
        # a lower-bound spread clearing keep. A published ceiling here is non-saturating, so
        # promotion is decided by the local spread.
        if reference_score is not None:
            notes.append(
                f"axis {axis}: published ceiling {reference_score:.2f} (REPORTED, non-saturating); "
                "promotion judged on the local spread",
            )
        frontier_obj = _extreme(scores, None, highest=True)
        floor_obj = _extreme(scores, None, highest=False)
        n_items = min(frontier_obj.n, floor_obj.n)
        gate = spread_gate(
            frontier=frontier_obj.score,
            n_frontier=frontier_obj.n,
            floor=floor_obj.score,
            n_floor=floor_obj.n,
            n_anchors=n_anchors,
            n_locals=n_locals,
            n_items=n_items,
        )
        verdict = gate.verdict
        spread_ci_low, spread_ci_high = gate.ci_low, gate.ci_high
        notes.extend(f"axis {axis}: {reason}" for reason in gate.reasons)
        if verdict == "keep" and not parse_fail_ok:
            notes.append(
                f"axis {axis}: parse/extraction-failure upper bound {parse_fail_upper:.0%} "
                f">= {PARSE_FAIL_CEILING:.0%} -> not weighted",
            )

    if not local_values:
        notes.append(f"axis {axis}: no usable local scores")

    result: AxisResult = {
        "axis": axis,
        "benches": benches,
        "anchor_min": anchor_min,
        "anchor_max": anchor_max,
        "anchor_spread": anchor_spread,
        "local_min": min(local_values) if local_values else None,
        "local_max": local_max,
        "overall_spread": overall_spread,
        "mean_point_biserial": point_biserial,
        "verdict": verdict,
        "suggested_weight": 0.0,
        "spread_ci_low": spread_ci_low,
        "spread_ci_high": spread_ci_high,
        "n_items": n_items,
        "n_anchors": n_anchors,
        "n_locals": n_locals,
        "parse_fail_upper": parse_fail_upper,
        "parse_fail_ok": parse_fail_ok,
        "differential_parse_fail_ok": differential_parse_fail_ok,
        "redundant_with_headline": redundant,
    }
    if notes:
        result["notes"] = notes
    return result


def _assign_weights(results: Sequence[AxisResult]) -> None:
    # Only PROMOTED axes are weighted: a clean keep that also passes the parse-fail gate
    # (high extraction-failure -> unreliable scores -> not weighted). Redundancy is surfaced
    # as an informational flag, NOT a weight gate: raw correlation with the headline over-
    # flags any axis that tracks general ability; the proper incremental-information test
    # (partial correlation on the panel) is computed at campaign time (see campaign doc).
    kept = [
        result
        for result in results
        if result["verdict"] == "keep"
        and result["overall_spread"] is not None
        and result["parse_fail_ok"]
        and result["differential_parse_fail_ok"]
    ]
    spread_total = sum(result["overall_spread"] for result in kept if result["overall_spread"] is not None)
    if spread_total <= 0:
        return
    for result in kept:
        spread = result["overall_spread"]
        if spread is not None:
            result["suggested_weight"] = spread / spread_total


def _axis_parse_fail(scores: Sequence[_AxisScore]) -> tuple[float | None, bool]:
    """Worst-model parse/extraction-failure upper bound for the axis, and whether it passes."""
    if not scores:
        return (None, True)
    worst_upper = 0.0
    for score in scores:
        _, upper = parse_fail_gate(score.extraction_failures, score.n)
        worst_upper = max(worst_upper, upper)
    return (worst_upper, worst_upper < PARSE_FAIL_CEILING)


def _axis_differential_parse_fail(scores: Sequence[_AxisScore]) -> tuple[bool, float]:
    """Whether parse-fail rates are similar across the anchor vs local families."""
    rates = [
        rate
        for label in ("anchor", "local")
        if (rate := _pooled_failure_rate([s for s in scores if s.label == label])) is not None
    ]
    return differential_parse_fail_gate(rates)


def _axis_redundant(scores: Sequence[_AxisScore]) -> bool:
    # Informational near-duplicate flag (threshold 0.98), NOT the incremental-information
    # gate (which needs partial correlation on the campaign panel).
    paired = [(score.score, score.composite) for score in scores if score.composite is not None]
    if len(paired) < 2:
        return False
    return is_redundant_with_headline(
        [axis for axis, _ in paired], [comp for _, comp in paired], threshold=0.98
    )


def _pooled_failure_rate(scores: Sequence[_AxisScore]) -> float | None:
    n_total = sum(score.n for score in scores)
    if n_total <= 0:
        return None
    return sum(score.extraction_failures for score in scores) / n_total


def _extreme(scores: Sequence[_AxisScore], label: LabelKind | None, *, highest: bool) -> _AxisScore:
    """The highest- or lowest-scoring model of a label. Ties broken by the SMALLEST N (the
    most conservative comparison), so the spread CI attaches to a real model's item count."""
    candidates = [score for score in scores if label is None or score.label == label]
    target = (max if highest else min)(score.score for score in candidates)
    return min((score for score in candidates if score.score == target), key=lambda score: score.n)


def _spread(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return max(values) - min(values)


def _number(value: JsonValue | None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _positive_number(value: JsonValue | None) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return number


def _label_kind(value: str | None) -> LabelKind | None:
    match value:
        case "anchor":
            return "anchor"
        case "local":
            return "local"
        case None:
            return None
        case _:
            return None
