from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from localbench._types import JsonValue
from localbench.probe._point_biserial import axis_point_biserial

LabelKind = Literal["anchor", "local"]
Verdict = Literal["keep", "drop:frontier-flat", "drop:locals-floor"]

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


def analyze_discrimination(
    run_records: Mapping[str, Mapping[str, JsonValue]],
    axis_map: Mapping[str, Mapping[str, JsonValue]],
    labels: Mapping[str, RunLabelInput],
) -> list[AxisResult]:
    """Measure per-axis between-model discrimination and normalize kept weights."""
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
        score = _axis_score(model, benches, notes)
        if score is not None:
            scores.append(
                _AxisScore(
                    model_name=model.model_name,
                    label=model.label,
                    score=score,
                ),
            )
    return scores


def _axis_score(
    model: _ModelRun,
    benches: Sequence[str],
    notes: list[str],
) -> float | None:
    raw_benches = model.record.get("benches")
    if not isinstance(raw_benches, Mapping):
        notes.append(f"{model.model_name}: missing benches object")
        return None
    weighted_total = 0.0
    item_total = 0.0
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
    if item_total <= 0:
        notes.append(f"{model.model_name}: no usable benches for axis")
        return None
    return weighted_total / item_total


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
    if anchor_spread is None and reference_score is not None:
        # No measured anchors, but a published frontier ceiling exists for this axis
        # (e.g. math: frontier scores are cited from the source, not re-measured here).
        # Judge discrimination by the gap between the published ceiling and the best local.
        gap = reference_score - (local_max if local_max is not None else 0.0)
        notes.append(
            f"axis {axis}: reference-anchored to published ceiling "
            f"{reference_score:.2f} (REPORTED, unmeasured); gap-to-best-local {gap:.2f}",
        )
        verdict: Verdict = "keep" if gap > FRONTIER_FLAT_THRESHOLD else "drop:locals-floor"
        anchor_min = anchor_max = reference_score
        overall_spread = reference_score - (min(local_values) if local_values else 0.0)
    elif anchor_spread is None:
        notes.append(f"axis {axis}: no usable anchor scores")
        verdict = "drop:frontier-flat"
    elif anchor_spread <= FRONTIER_FLAT_THRESHOLD:
        verdict = "drop:frontier-flat"
    elif local_values and all(value <= LOCALS_FLOOR_THRESHOLD for value in local_values):
        verdict = "drop:locals-floor"
    else:
        verdict = "keep"
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
    }
    if notes:
        result["notes"] = notes
    return result


def _assign_weights(results: Sequence[AxisResult]) -> None:
    kept = [
        result
        for result in results
        if result["verdict"] == "keep" and result["overall_spread"] is not None
    ]
    spread_total = sum(result["overall_spread"] for result in kept)
    if spread_total <= 0:
        return
    for result in kept:
        spread = result["overall_spread"]
        if spread is not None:
            result["suggested_weight"] = spread / spread_total


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
