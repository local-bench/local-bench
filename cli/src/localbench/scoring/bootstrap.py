from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from typing import NotRequired, TypedDict

from localbench.scoring.signed_score import chance_for_bench, signed_score


class Interval(TypedDict):
    point: float
    lo: float
    hi: float


class BenchSample(TypedDict):
    correct: list[bool]
    strata: NotRequired[list[str]]
    chance: NotRequired[float]


class BootstrapInputError(ValueError):
    pass


def per_bench_ci(
    item_correct: list[bool],
    strata: list[str],
    iters: int = 10_000,
    seed: int = 0,
) -> Interval:
    """Return a seeded stratified percentile bootstrap CI for raw accuracy."""
    values = [1.0 if correct else 0.0 for correct in item_correct]
    return stratified_mean_ci(values, strata, iters=iters, seed=seed)


def stratified_mean_ci(
    values: Sequence[float],
    strata: Sequence[str],
    *,
    iters: int = 10_000,
    seed: int = 0,
) -> Interval:
    """Return a seeded stratified percentile bootstrap CI for a mean."""
    if len(values) != len(strata):
        raise BootstrapInputError("values and strata must have the same length")
    if not values:
        return {"point": 0.0, "lo": 0.0, "hi": 0.0}
    groups = _stratified_groups(values, strata)
    rng = random.Random(seed)
    draws = sorted(_draw_stratified_mean(groups, rng) for _ in range(max(1, iters)))
    point = sum(values) / len(values)
    return {"point": point, "lo": _percentile(draws, 0.025), "hi": _percentile(draws, 0.975)}


def composite_ci(
    bench_to_items: Mapping[str, Sequence[bool] | BenchSample],
    weights: Mapping[str, float],
    seed: int,
    iters: int = 10_000,
) -> Interval:
    """Return a nested item-bootstrap CI for weighted signed composite score."""
    samples = {
        bench: _coerce_sample(bench, sample)
        for bench, sample in bench_to_items.items()
    }
    if not samples:
        return {"point": 0.0, "lo": 0.0, "hi": 0.0}
    normalized = _normalized_weights(samples.keys(), weights)
    point = sum(
        normalized[bench] * signed_score(_mean_bool(correct), chance=chance)
        for bench, (correct, _strata, chance) in samples.items()
    )
    rng = random.Random(seed)
    draws: list[float] = []
    for _index in range(max(1, iters)):
        total = 0.0
        for bench, (correct, strata, chance) in samples.items():
            values = [1.0 if item else 0.0 for item in correct]
            raw = _draw_stratified_mean(_stratified_groups(values, strata), rng)
            total += normalized[bench] * signed_score(raw, chance=chance)
        draws.append(total)
    draws.sort()
    return {"point": point, "lo": _percentile(draws, 0.025), "hi": _percentile(draws, 0.975)}


def _coerce_sample(
    bench: str,
    sample: Sequence[bool] | BenchSample,
) -> tuple[list[bool], list[str], float]:
    if isinstance(sample, dict):
        correct = [bool(value) for value in sample["correct"]]
        raw_strata = sample.get("strata")
        strata = list(raw_strata) if raw_strata is not None else [bench] * len(correct)
        chance = float(sample.get("chance", chance_for_bench(bench)))
        return correct, strata, chance
    correct = [bool(value) for value in sample]
    return correct, [bench] * len(correct), chance_for_bench(bench)


def _stratified_groups(
    values: Sequence[float],
    strata: Sequence[str],
) -> dict[str, list[float]]:
    groups: dict[str, list[float]] = {}
    for value, stratum in zip(values, strata, strict=True):
        groups.setdefault(stratum, []).append(value)
    return groups


def _draw_stratified_mean(
    groups: Mapping[str, Sequence[float]],
    rng: random.Random,
) -> float:
    total = 0.0
    count = 0
    for stratum in sorted(groups):
        values = groups[stratum]
        count += len(values)
        total += sum(values[rng.randrange(len(values))] for _index in range(len(values)))
    return total / count if count else 0.0


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _mean_bool(values: Sequence[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


def _normalized_weights(
    names: Iterable[str],
    weights: Mapping[str, float],
) -> dict[str, float]:
    present = list(names)
    total = sum(max(0.0, weights.get(name, 1.0)) for name in present)
    if total <= 0.0:
        return {name: 1.0 / len(present) for name in present}
    return {name: max(0.0, weights.get(name, 1.0)) / total for name in present}
