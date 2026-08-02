from __future__ import annotations

from localbench._types import JsonObject, JsonValue

MARGINS_PP = {"knowledge": 3.0, "instruction": 4.0, "coding": 5.0, "math": 6.0, "tools": 4.0}
WEIGHTS = {"knowledge": 0.25, "coding": 0.25, "instruction": 0.20, "math": 0.10}


def calibration_bounds(good_quant_results: dict[str, list[JsonObject]]) -> JsonObject:
    if not good_quant_results or any(not good_quant_results.get(area) for area in MARGINS_PP):
        return {"disagreement": {}, "drop": {}, "status": "uncalibrated"}
    disagreement: JsonObject = {}
    drop: JsonObject = {}
    for area in MARGINS_PP:
        rows = good_quant_results[area]
        disagreement_values = [_required_rate(row, "disagreement_rate") for row in rows]
        drop_values = [_required_rate(row, "drop_rate") for row in rows]
        disagreement[area] = max(0.06 if area == "tools" else 0.03, 1.5 * max(disagreement_values))
        drop[area] = max(0.03, 1.5 * max(drop_values))
    return {"disagreement": disagreement, "drop": drop, "status": "calibrated"}


def quant_verdict(
    intervals: dict[str, dict[str, float]],
    measures: dict[str, dict[str, float]],
    bounds: JsonObject,
    *,
    validity_gates_pass: bool,
    behavioral_gates_pass: bool,
) -> JsonObject:
    if not validity_gates_pass:
        return {"label": "broken", "verdict": "broken"}
    if bounds.get("status") != "calibrated":
        return {"label": "inconclusive — calibration bounds unavailable", "verdict": "inconclusive"}
    if any(intervals[area]["upper_pp"] < -MARGINS_PP[area] for area in MARGINS_PP):
        return {"label": "degraded", "verdict": "degraded"}
    noninferior = all(intervals[area]["lower_pp"] >= -MARGINS_PP[area] for area in MARGINS_PP)
    bounds_pass = _bounds_pass(measures, bounds)
    if noninferior and bounds_pass and behavioral_gates_pass:
        return {"label": "reference-faithful", "verdict": "reference-faithful"}
    if noninferior and not bounds_pass:
        return {"label": "drift", "verdict": "drift"}
    if not bounds_pass:
        return {"label": "inconclusive — drift bound breached", "verdict": "inconclusive"}
    label = "inconclusive — behavioral gate failure" if not behavioral_gates_pass else "inconclusive"
    return {"label": label, "verdict": "inconclusive"}


def tune_area_outcome(lower_pp: float, upper_pp: float) -> str:
    if lower_pp > 2.0:
        return "resolved gain"
    if upper_pp < -2.0:
        return "resolved loss"
    if lower_pp >= -2.0 and upper_pp <= 2.0:
        return "practical equivalence"
    return "unresolved"


def aggregate_scores(scores: dict[str, float], *, unsupported: tuple[str, ...]) -> JsonObject:
    if unsupported:
        excluded = ", ".join(sorted(unsupported))
        return {
            "composite": None,
            "label": f"composite unavailable (capability excluded: {excluded})",
            "unsupported": list(sorted(unsupported)),
            "version": "check-weights-v1",
            "worst_axis": _worst_axis(scores),
        }
    required = {*WEIGHTS, "tools-single", "tools-stateful"}
    missing = sorted(required - scores.keys())
    if missing:
        raise ValueError(f"composite inputs missing: {', '.join(missing)}")
    composite = sum(scores[area] * weight for area, weight in WEIGHTS.items())
    composite += scores["tools-single"] * 0.12 + scores["tools-stateful"] * 0.08
    return {
        "composite": round(composite, 12),
        "label": "available",
        "unsupported": [],
        "version": "check-weights-v1",
        "worst_axis": _worst_axis(scores),
    }


def reference_policy_exclusions(
    reference_supported: dict[str, bool],
    candidate_supported: dict[str, bool],
) -> tuple[str, ...]:
    exclusions = tuple(sorted(area for area, supported in reference_supported.items() if not supported))
    candidate_only = [
        area
        for area, supported in candidate_supported.items()
        if not supported and reference_supported.get(area, False)
    ]
    if candidate_only:
        raise ValueError(f"candidate-only inability is a scored failure, not unsupported: {', '.join(sorted(candidate_only))}")
    return exclusions


def _bounds_pass(measures: dict[str, dict[str, float]], bounds: JsonObject) -> bool:
    disagreement = bounds.get("disagreement")
    drop = bounds.get("drop")
    if not isinstance(disagreement, dict) or not isinstance(drop, dict):
        return False
    return all(
        measures[area]["disagreement_rate"] <= _number(disagreement.get(area))
        and measures[area]["drop_rate"] <= _number(drop.get(area))
        for area in MARGINS_PP
    )


def _worst_axis(scores: dict[str, float]) -> JsonObject:
    area_scores = {
        area: score
        for area, score in scores.items()
        if area in MARGINS_PP
    }
    if "tools" not in area_scores and {"tools-single", "tools-stateful"} <= scores.keys():
        area_scores["tools"] = scores["tools-single"] * 0.6 + scores["tools-stateful"] * 0.4
    area, score = min(area_scores.items(), key=lambda item: (item[1], item[0]))
    return {"area": area, "score": score}


def _required_rate(row: JsonObject, key: str) -> float:
    return _number(row.get(key))


def _number(value: JsonValue) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("calibration and bound values must be numeric")
    return float(value)
