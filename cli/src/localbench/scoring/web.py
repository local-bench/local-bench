from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict

from localbench.scoring.signed_score import chance_for_bench


class ScoreInterval(TypedDict):
    hi: float
    hi_raw: float
    lo: float
    lo_raw: float
    point: float
    point_raw: float


class AxisPoint(TypedDict):
    point: float
    point_raw: float


class WorstAxis(TypedDict):
    bench: str
    point: float
    point_raw: float


def score_interval(point: float, lo: float, hi: float) -> ScoreInterval:
    return {
        "hi": hi * 100.0,
        "hi_raw": hi,
        "lo": lo * 100.0,
        "lo_raw": lo,
        "point": point * 100.0,
        "point_raw": point,
    }


def score_interval_from_percent_ci(point: float, ci: float) -> ScoreInterval:
    lo = _clamp_percent(point - ci)
    hi = _clamp_percent(point + ci)
    return {
        "hi": hi,
        "hi_raw": hi / 100.0,
        "lo": lo,
        "lo_raw": lo / 100.0,
        "point": point,
        "point_raw": point / 100.0,
    }


def raw_accuracy_from_signed_percent(bench: str, signed_point: float) -> float:
    chance = chance_for_bench(bench)
    return chance + (signed_point / 100.0) * (1.0 - chance)


def weighted_composite_point(
    axes: Mapping[str, AxisPoint],
    benches: Sequence[str],
    weights: Mapping[str, float],
) -> float:
    weight_total = sum(weights[bench] for bench in benches)
    return sum(axes[bench]["point_raw"] * weights[bench] for bench in benches) / weight_total


def worst_axis(axes: Mapping[str, AxisPoint], benches: Sequence[str]) -> WorstAxis:
    bench = min(benches, key=lambda name: axes[name]["point_raw"])
    axis = axes[bench]
    return {"bench": bench, "point": axis["point"], "point_raw": axis["point_raw"]}


def _clamp_percent(value: float) -> float:
    return min(100.0, max(0.0, value))
