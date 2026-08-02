from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from statistics import NormalDist
from typing import Final

from localbench._types import JsonObject, JsonValue

AREA_NAMES: Final = ("knowledge", "instruction", "coding", "math", "tools")
BOOTSTRAP_RESAMPLES: Final = 100_000
BOOTSTRAP_SEED: Final = 20260802
_CONFIDENCE: Final = 0.95


@dataclass(frozen=True, slots=True)
class PairedOutcome:
    item_id: str
    reference_correct: bool
    candidate_correct: bool
    stratum: str
    cluster: str
    chance: float = 0.0

    @property
    def raw_delta(self) -> int:
        return int(self.candidate_correct) - int(self.reference_correct)

    @property
    def signed_delta(self) -> float:
        if self.chance >= 1.0:
            raise ValueError("chance baseline must be less than one")
        return self.raw_delta / (1.0 - self.chance)


def paired_measures(outcomes: list[PairedOutcome]) -> JsonObject:
    if not outcomes:
        raise ValueError("paired measures require at least one outcome")
    drops = sum(outcome.reference_correct and not outcome.candidate_correct for outcome in outcomes)
    leaps = sum(not outcome.reference_correct and outcome.candidate_correct for outcome in outcomes)
    n = len(outcomes)
    return {
        "delta_pp": 100.0 * (leaps - drops) / n,
        "disagreement_count": drops + leaps,
        "disagreement_rate": (drops + leaps) / n,
        "drop_count": drops,
        "drop_rate": drops / n,
        "leapfrog_count": leaps,
        "leapfrog_rate": leaps / n,
        "n": n,
    }


def bootstrap_area_deltas(
    outcomes: list[PairedOutcome],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[float]:
    if resamples < 2:
        raise ValueError("bootstrap requires at least two resamples")
    blocks = _cluster_blocks(outcomes)
    rng = random.Random(seed)
    return [_draw_area_delta(blocks, rng) for _ in range(resamples)]


def simultaneous_intervals(
    areas: dict[str, list[PairedOutcome]],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = _CONFIDENCE,
) -> JsonObject:
    _validate_areas(areas)
    measures = {area: paired_measures(areas[area]) for area in AREA_NAMES}
    zero_discordance = [area for area in AREA_NAMES if measures[area]["disagreement_count"] == 0]
    if zero_discordance:
        return _fallback_intervals(areas, confidence=confidence, reasons=zero_discordance)
    if resamples < 2:
        raise ValueError("bootstrap requires at least two resamples")

    grouped = {area: _cluster_blocks(areas[area]) for area in AREA_NAMES}
    distributions: dict[str, list[float]] = {area: [] for area in AREA_NAMES}
    rng = random.Random(seed)
    for _ in range(resamples):
        for area in AREA_NAMES:
            distributions[area].append(_draw_area_delta(grouped[area], rng))
    standard_errors: dict[str, float] = {
        area: statistics.stdev(distributions[area]) for area in AREA_NAMES
    }
    zero_variance = [area for area, value in standard_errors.items() if value == 0.0]
    if zero_variance:
        return _fallback_intervals(areas, confidence=confidence, reasons=zero_variance)

    points = {area: _point_delta(areas[area]) for area in AREA_NAMES}
    max_statistics: list[float] = [
        max(
            abs((distributions[area][index] - points[area]) / standard_errors[area])
            for area in AREA_NAMES
        )
        for index in range(resamples)
    ]
    critical = _quantile(max_statistics, confidence)
    interval_rows: JsonObject = {}
    for area in AREA_NAMES:
        half_width = critical * standard_errors[area]
        interval_rows[area] = {
            "delta_pp": points[area],
            "lower_pp": max(-100.0 * _score_scale(areas[area]), points[area] - half_width),
            "method": "centered-studentized-two-sided-simultaneous-max-statistic",
            "se_pp": standard_errors[area],
            "upper_pp": min(100.0 * _score_scale(areas[area]), points[area] + half_width),
        }
    return {
        "areas": interval_rows,
        "confidence": confidence,
        "critical_value": critical,
        "method": "centered-studentized-two-sided-simultaneous-max-statistic",
        "resamples": resamples,
        "seed": seed,
        "studentization": "bootstrap-standard-deviation-of-area-paired-delta",
    }


def tango_paired_interval(
    outcomes: list[PairedOutcome],
    *,
    confidence: float,
) -> tuple[float, float]:
    measures = paired_measures(outcomes)
    n_value = measures["n"]
    drops_value = measures["drop_count"]
    leaps_value = measures["leapfrog_count"]
    if not isinstance(n_value, int) or not isinstance(drops_value, int) or not isinstance(leaps_value, int):
        raise TypeError("paired count fields must be integers")
    estimate = (leaps_value - drops_value) / n_value
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)

    def score(delta: float) -> float:
        nuisance = _constrained_discordance_mle(
            delta,
            drops=drops_value,
            leaps=leaps_value,
            n=n_value,
        )
        variance = max((nuisance - delta * delta) / n_value, 1e-18)
        return (estimate - delta) / math.sqrt(variance)

    lower = _score_root(-1.0, estimate, target=z, score=score)
    upper = _score_root(estimate, 1.0, target=-z, score=score)
    scale = _score_scale(outcomes)
    return 100.0 * lower * scale, 100.0 * upper * scale


def _fallback_intervals(
    areas: dict[str, list[PairedOutcome]],
    *,
    confidence: float,
    reasons: list[str],
) -> JsonObject:
    bonferroni_confidence = 1.0 - (1.0 - confidence) / len(AREA_NAMES)
    interval_rows: JsonObject = {}
    for area in AREA_NAMES:
        lower, upper = tango_paired_interval(areas[area], confidence=bonferroni_confidence)
        interval_rows[area] = {
            "delta_pp": _point_delta(areas[area]),
            "lower_pp": lower,
            "method": "bonferroni-tango-paired-score",
            "upper_pp": upper,
        }
    reason_values: list[JsonValue] = [reason for reason in reasons]
    result: JsonObject = {
        "areas": interval_rows,
        "bonferroni_confidence": bonferroni_confidence,
        "confidence": confidence,
        "fallback_reasons": reason_values,
        "method": "bonferroni-tango-paired-score",
        "trigger": "any-area-zero-bootstrap-variance-or-zero-discordance",
    }
    return result


def _cluster_blocks(outcomes: list[PairedOutcome]) -> dict[str, list[tuple[float, int]]]:
    if not outcomes:
        raise ValueError("bootstrap requires at least one paired outcome")
    clusters: dict[tuple[str, str], list[PairedOutcome]] = defaultdict(list)
    for outcome in outcomes:
        clusters[(outcome.stratum, outcome.cluster)].append(outcome)
    strata: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for (stratum, _cluster), members in sorted(clusters.items()):
        strata[stratum].append((sum(member.signed_delta for member in members), len(members)))
    return dict(strata)


def _draw_area_delta(blocks: dict[str, list[tuple[float, int]]], rng: random.Random) -> float:
    total = 0.0
    n = 0
    for stratum in sorted(blocks):
        choices = blocks[stratum]
        for _ in choices:
            block_delta, block_n = choices[rng.randrange(len(choices))]
            total += block_delta
            n += block_n
    return 100.0 * total / n


def _point_delta(outcomes: list[PairedOutcome]) -> float:
    return 100.0 * sum(outcome.signed_delta for outcome in outcomes) / len(outcomes)


def _score_scale(outcomes: list[PairedOutcome]) -> float:
    scales = {1.0 / (1.0 - outcome.chance) for outcome in outcomes}
    if len(scales) != 1:
        raise ValueError("one area cannot mix chance-correction baselines")
    return scales.pop()


def _quantile(values: list[float], probability: float) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError("quantile probability must be between zero and one")
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def _validate_areas(areas: dict[str, list[PairedOutcome]]) -> None:
    if set(areas) != set(AREA_NAMES):
        raise ValueError(f"comparison must contain exactly the five locked areas: {AREA_NAMES}")
    if any(not areas[area] for area in AREA_NAMES):
        raise ValueError("every supported comparison area must contain paired outcomes")


def _constrained_discordance_mle(delta: float, *, drops: int, leaps: int, n: int) -> float:
    epsilon = 1e-12
    lower = min(1.0 - epsilon, abs(delta) + epsilon)
    upper = 1.0 - epsilon

    def derivative(discordance: float) -> float:
        positive = discordance + delta
        negative = discordance - delta
        value = 0.0
        if leaps:
            value += leaps / positive
        if drops:
            value += drops / negative
        concordant = n - leaps - drops
        if concordant:
            value -= concordant / (1.0 - discordance)
        return value

    if derivative(lower) <= 0.0:
        return lower
    if derivative(upper) >= 0.0:
        return upper
    for _ in range(80):
        middle = (lower + upper) / 2.0
        if derivative(middle) > 0.0:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2.0


def _score_root(
    lower: float,
    upper: float,
    *,
    target: float,
    score: Callable[[float], float],
) -> float:
    lower_value = score(lower + 1e-10) - target
    upper_value = score(upper - 1e-10) - target
    if lower_value * upper_value > 0.0:
        return lower if abs(lower_value) < abs(upper_value) else upper
    for _ in range(80):
        middle = (lower + upper) / 2.0
        middle_value = score(middle) - target
        if lower_value * middle_value <= 0.0:
            upper = middle
            upper_value = middle_value
        else:
            lower = middle
            lower_value = middle_value
    return (lower + upper) / 2.0
