from __future__ import annotations

from localbench._types import JsonObject
from localbench.check.verdict import (
    aggregate_scores,
    calibration_bounds,
    quant_verdict,
    tune_area_outcome,
)


def _intervals(lower: float = -1.0, upper: float = 1.0) -> dict[str, dict[str, float]]:
    return {
        area: {"lower_pp": lower, "upper_pp": upper}
        for area in ("knowledge", "instruction", "coding", "math", "tools")
    }


def _measures(disagreement: float = 0.02, drop: float = 0.01) -> dict[str, dict[str, float]]:
    return {
        area: {"disagreement_rate": disagreement, "drop_rate": drop}
        for area in ("knowledge", "instruction", "coding", "math", "tools")
    }


def _bounds(value: float = 0.03) -> JsonObject:
    return {
        "status": "calibrated",
        "disagreement": {area: (0.06 if area == "tools" else value) for area in _intervals()},
        "drop": {area: value for area in _intervals()},
    }


def test_quant_boundary_equalities_pass_faithful() -> None:
    intervals = _intervals()
    margins = {"knowledge": 3.0, "instruction": 4.0, "coding": 5.0, "math": 6.0, "tools": 4.0}
    for area, margin in margins.items():
        intervals[area]["lower_pp"] = -margin
    measures = _measures(disagreement=0.03, drop=0.03)
    measures["tools"]["disagreement_rate"] = 0.06

    result = quant_verdict(intervals, measures, _bounds(), validity_gates_pass=True, behavioral_gates_pass=True)

    assert result["verdict"] == "reference-faithful"


def test_verdict_precedence_and_drift_sublabels() -> None:
    degraded = _intervals()
    degraded["knowledge"] = {"lower_pp": -10.0, "upper_pp": -3.0001}
    assert quant_verdict(degraded, _measures(), _bounds(), validity_gates_pass=True, behavioral_gates_pass=True)["verdict"] == "degraded"
    assert quant_verdict(_intervals(), _measures(), _bounds(), validity_gates_pass=False, behavioral_gates_pass=True)["verdict"] == "broken"
    drift = quant_verdict(_intervals(), _measures(disagreement=0.07), _bounds(), validity_gates_pass=True, behavioral_gates_pass=True)
    assert drift["verdict"] == "drift"
    unresolved = _intervals(lower=-8.0, upper=2.0)
    breached = quant_verdict(unresolved, _measures(disagreement=0.07), _bounds(), validity_gates_pass=True, behavioral_gates_pass=True)
    assert breached["verdict"] == "inconclusive"
    assert breached["label"] == "inconclusive — drift bound breached"


def test_uncalibrated_bounds_cap_verdict_at_inconclusive() -> None:
    uncalibrated = calibration_bounds({})

    result = quant_verdict(_intervals(), _measures(), uncalibrated, validity_gates_pass=True, behavioral_gates_pass=True)

    assert uncalibrated["status"] == "uncalibrated"
    assert result["verdict"] == "inconclusive"


def test_tune_four_states_use_strict_outer_edges_and_closed_equivalence_edges() -> None:
    assert tune_area_outcome(2.0001, 4.0) == "resolved gain"
    assert tune_area_outcome(-4.0, -2.0001) == "resolved loss"
    assert tune_area_outcome(-2.0, 2.0) == "practical equivalence"
    assert tune_area_outcome(2.0, 4.0) == "unresolved"
    assert tune_area_outcome(-4.0, -2.0) == "unresolved"


def test_composite_withholds_instead_of_renormalizing_unsupported_area() -> None:
    scores = {"knowledge": 0.8, "coding": 0.7, "instruction": 0.9, "tools-single": 0.8, "tools-stateful": 0.6, "math": 0.5}

    available = aggregate_scores(scores, unsupported=())
    withheld = aggregate_scores(scores, unsupported=("coding",))

    assert available["composite"] == 0.749
    assert available["worst_axis"] == {"area": "math", "score": 0.5}
    assert withheld["composite"] is None
    assert withheld["label"] == "composite unavailable (capability excluded: coding)"
