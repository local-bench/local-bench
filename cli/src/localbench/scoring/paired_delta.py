from __future__ import annotations

import json
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from localbench._types import JsonValue
from localbench.scoring.bootstrap import (
    Interval,
    _draw_stratified_mean,
    _percentile,
    _stratified_cluster_groups,
    _stratified_groups,
    stratified_mean_ci,
)
from localbench.scoring.metadata import (
    DOMAIN_WEIGHTS,
    cluster_for_item,
    domain_for_bench,
    stratum_for_item,
)
from localbench.scoring.signed_score import chance_for_bench, signed_delta
from localbench.scoring.subgroups import (
    DeltaObservation,
    SubgroupDelta,
    severe_subgroup_regressions,
    subgroup_delta_cis,
)


class PerItemDelta(TypedDict):
    id: str
    bench: str
    domain: str
    stratum: str
    cluster: str
    delta: int
    signed_delta: float


class DomainDelta(TypedDict):
    n: int
    delta: Interval
    repeatability_ci: Interval
    generalization_ci: Interval


class WorstAxis(TypedDict):
    domain: str
    delta: Interval


class CompareResult(TypedDict):
    schema: str
    composite_delta: Interval
    repeatability_ci: Interval
    generalization_ci: Interval
    domains: dict[str, DomainDelta]
    worst_axis: WorstAxis
    subgroups: list[SubgroupDelta]
    severe_subgroup_regressions: list[SubgroupDelta]
    per_item_delta: list[PerItemDelta]


@dataclass(frozen=True, slots=True)
class _RunItem:
    id: str
    bench: str
    correct: bool
    source: Mapping[str, JsonValue]


def compare_run_files(
    run_a: Path,
    run_b: Path,
    *,
    iters: int = 10_000,
    seed: int = 0,
) -> CompareResult:
    """Load two saved run records and return a paired comparison."""
    return compare_runs(_read_run(run_a), _read_run(run_b), iters=iters, seed=seed)


def compare_runs(
    run_a: Mapping[str, JsonValue],
    run_b: Mapping[str, JsonValue],
    *,
    iters: int = 10_000,
    seed: int = 0,
) -> CompareResult:
    """Return paired deltas for two runs over the same item ids."""
    items_a = _item_map(run_a)
    items_b = _item_map(run_b)
    if set(items_a) != set(items_b):
        raise ValueError("paired comparison requires the same item ids in both runs")
    deltas = [_delta_item(items_a[key], items_b[key]) for key in sorted(items_a)]
    observations: list[DeltaObservation] = [
        {
            "domain": item["domain"],
            "stratum": item["stratum"],
            "cluster": item["cluster"],
            "raw_delta": item["delta"],
            "signed_delta": item["signed_delta"],
        }
        for item in deltas
    ]
    domains = _domain_deltas(observations, iters=iters, seed=seed)
    repeatability = _weighted_domain_ci(observations, stratified=False, iters=iters, seed=seed)
    generalization = _weighted_domain_ci(observations, stratified=True, iters=iters, seed=seed)
    subgroups = subgroup_delta_cis(observations, iters=iters, seed=seed + 20_000)
    return {
        "schema": "localbench-compare-v1",
        "composite_delta": generalization,
        "repeatability_ci": repeatability,
        "generalization_ci": generalization,
        "domains": domains,
        "worst_axis": _worst_axis(domains),
        "subgroups": subgroups,
        "severe_subgroup_regressions": severe_subgroup_regressions(subgroups),
        "per_item_delta": deltas,
    }


def format_honest_delta(interval: Mapping[str, float]) -> str:
    """Format a fixed-item delta label without universal percent language."""
    point = interval["point"] * 100.0
    half_width = max(
        abs(interval["point"] - interval["lo"]),
        abs(interval["hi"] - interval["point"]),
    ) * 100.0
    return f"{_signed_decimal(point)} ± {half_width:.1f} on these items"


def _domain_deltas(
    observations: Sequence[DeltaObservation],
    *,
    iters: int,
    seed: int,
) -> dict[str, DomainDelta]:
    grouped = _by_domain(observations)
    domains: dict[str, DomainDelta] = {}
    for index, domain in enumerate(sorted(grouped)):
        values = [item["signed_delta"] for item in grouped[domain]]
        strata = [item["stratum"] for item in grouped[domain]]
        clusters = [item["cluster"] for item in grouped[domain]]
        repeatability = stratified_mean_ci(
            values,
            [domain] * len(values),
            clusters=clusters,
            iters=iters,
            seed=seed + index,
        )
        generalization = stratified_mean_ci(
            values,
            strata,
            clusters=clusters,
            iters=iters,
            seed=seed + 1_000 + index,
        )
        domains[domain] = {
            "n": len(values),
            "delta": generalization,
            "repeatability_ci": repeatability,
            "generalization_ci": generalization,
        }
    return domains


def _weighted_domain_ci(
    observations: Sequence[DeltaObservation],
    *,
    stratified: bool,
    iters: int,
    seed: int,
) -> Interval:
    grouped = _by_domain(observations)
    if not grouped:
        return {"point": 0.0, "lo": 0.0, "hi": 0.0}
    weights = _normalized_domain_weights(grouped.keys())
    point = sum(
        weights[domain] * _mean([item["signed_delta"] for item in grouped[domain]])
        for domain in grouped
    )
    rng = random.Random(seed + (5_000 if stratified else 4_000))
    draws: list[float] = []
    for _index in range(max(1, iters)):
        total = 0.0
        for domain in sorted(grouped):
            values = [item["signed_delta"] for item in grouped[domain]]
            strata = [item["stratum"] if stratified else domain for item in grouped[domain]]
            clusters = [item["cluster"] for item in grouped[domain]]
            total += weights[domain] * _draw_mean(values, strata, rng, clusters=clusters)
        draws.append(total)
    draws.sort()
    return {"point": point, "lo": _percentile(draws, 0.025), "hi": _percentile(draws, 0.975)}


def _item_map(record: Mapping[str, JsonValue]) -> dict[tuple[str, str], _RunItem]:
    raw_items = record.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("run record must contain an items list")
    items: dict[tuple[str, str], _RunItem] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("run item must be a JSON object")
        item_id = raw_item.get("id")
        bench = raw_item.get("bench")
        correct = raw_item.get("correct")
        if not isinstance(item_id, str) or not isinstance(bench, str) or not isinstance(correct, bool):
            raise ValueError("run items must include string id, string bench, and bool correct")
        key = (bench, item_id)
        if key in items:
            raise ValueError(f"duplicate item id in run record: {bench}/{item_id}")
        items[key] = _RunItem(id=item_id, bench=bench, correct=correct, source=raw_item)
    return items


def _delta_item(item_a: _RunItem, item_b: _RunItem) -> PerItemDelta:
    raw_delta = int(item_a.correct) - int(item_b.correct)
    domain = domain_for_bench(item_a.bench)
    stratum = stratum_for_item(item_a.bench, item_a.id, item_a.source)
    cluster = cluster_for_item(item_a.bench, item_a.id, item_a.source)
    return {
        "id": item_a.id,
        "bench": item_a.bench,
        "domain": domain,
        "stratum": stratum,
        "cluster": cluster,
        "delta": raw_delta,
        "signed_delta": signed_delta(raw_delta, chance=chance_for_bench(item_a.bench)),
    }


def _worst_axis(domains: Mapping[str, DomainDelta]) -> WorstAxis:
    if not domains:
        return {"domain": "none", "delta": {"point": 0.0, "lo": 0.0, "hi": 0.0}}
    domain = min(domains, key=lambda name: domains[name]["delta"]["point"])
    return {"domain": domain, "delta": domains[domain]["delta"]}


def _by_domain(
    observations: Sequence[DeltaObservation],
) -> dict[str, list[DeltaObservation]]:
    grouped: dict[str, list[DeltaObservation]] = {}
    for item in observations:
        grouped.setdefault(item["domain"], []).append(item)
    return grouped


def _draw_mean(
    values: Sequence[float],
    strata: Sequence[str],
    rng: random.Random,
    *,
    clusters: Sequence[str] | None = None,
) -> float:
    groups = _stratified_groups(values, strata)
    block_groups = (
        None if clusters is None else _stratified_cluster_groups(values, strata, clusters)
    )
    return _draw_stratified_mean(groups, rng, block_groups)


def _normalized_domain_weights(domains: Iterable[str]) -> dict[str, float]:
    present = list(domains)
    total = sum(DOMAIN_WEIGHTS.get(domain, 1.0) for domain in present)
    return {domain: DOMAIN_WEIGHTS.get(domain, 1.0) / total for domain in present}


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _signed_decimal(value: float) -> str:
    if value < 0:
        return f"−{abs(value):.1f}"
    if value > 0:
        return f"+{value:.1f}"
    return "0.0"


def _read_run(path: Path) -> Mapping[str, JsonValue]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"run record is not a JSON object: {path}")
    return data
