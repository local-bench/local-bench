from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from localbench.checkset.models import ChecksetBuildError, JsonValue

SELECTION_SEED: Final = 20260802


@dataclass(frozen=True, slots=True)
class SourceItem:
    item_id: str
    content_sha256: str
    informative: bool
    latency_seconds: float | None
    instruction_ids: tuple[str, ...] = ()
    tool_count: int = 0


@dataclass(frozen=True, slots=True)
class MediumMathItem:
    upstream_index: int
    topic: str
    content_sha256: str


def select_cost_aware(
    items: Sequence[SourceItem],
    *,
    quota: int,
    median_pool: Sequence[SourceItem] | None = None,
) -> tuple[SourceItem, ...]:
    pool = items if median_pool is None else median_pool
    latencies = [item.latency_seconds for item in pool if item.latency_seconds is not None]
    if not latencies:
        return tuple(sorted(items, key=lambda item: item.item_id)[:quota])
    median = statistics.median(latencies)
    ranked = sorted(
        items,
        key=lambda item: (
            item.latency_seconds is None or item.latency_seconds >= median,
            item.item_id,
        ),
    )
    return tuple(ranked[:quota])


def select_ifbench(
    items: Sequence[SourceItem],
    quotas: Mapping[str, int],
    *,
    informative_quota: int | None = None,
) -> tuple[SourceItem, ...]:
    primary_strata: dict[str, list[SourceItem]] = defaultdict(list)
    for item in items:
        primary = min(item.instruction_ids)
        primary_strata[primary].append(item)
    family_items: dict[str, list[SourceItem]] = defaultdict(list)
    for primary, primary_items in primary_strata.items():
        family_items[primary.split(":", 1)[0]].extend(primary_items)
    if informative_quota is None:
        selected: list[SourceItem] = []
        for family, quota in quotas.items():
            ranked = sorted(family_items[family], key=lambda item: (not item.informative, item.item_id))
            if len(ranked) < quota:
                raise ChecksetBuildError(f"IFBench stratum {family!r} has {len(ranked)} items for quota {quota}.")
            selected.extend(ranked[:quota])
        return tuple(selected)

    informative_capacity = {
        family: sum(item.informative for item in items_in_family)
        for family, items_in_family in family_items.items()
        if family in quotas
    }
    informative_by_family = _apportion(informative_capacity, informative_quota)
    selected = []
    for family, quota in quotas.items():
        informative_count = informative_by_family[family]
        family_strata = {
            primary: primary_items
            for primary, primary_items in primary_strata.items()
            if primary.split(":", 1)[0] == family
        }
        selected.extend(_select_kind_by_primary(family_strata, informative=True, quota=informative_count))
        selected.extend(_select_kind_by_primary(family_strata, informative=False, quota=quota - informative_count))
    return tuple(selected)


def _apportion(capacities: Mapping[str, int], quota: int) -> dict[str, int]:
    total = sum(capacities.values())
    raw = {name: quota * capacity / total for name, capacity in capacities.items()}
    apportioned = {name: min(int(raw[name]), capacity) for name, capacity in capacities.items()}
    remaining = quota - sum(apportioned.values())
    order = sorted(capacities, key=lambda name: (-(raw[name] - int(raw[name])), name))
    while remaining:
        eligible = [name for name in order if apportioned[name] < capacities[name]]
        if not eligible:
            raise ChecksetBuildError(f"Cannot apportion quota {quota} across capacity {total}.")
        for name in eligible:
            apportioned[name] += 1
            remaining -= 1
            if not remaining:
                break
    return apportioned


def _select_kind_by_primary(
    strata: Mapping[str, Sequence[SourceItem]],
    *,
    informative: bool,
    quota: int,
) -> tuple[SourceItem, ...]:
    candidates = {
        primary: tuple(item for item in items if item.informative is informative)
        for primary, items in strata.items()
    }
    nonempty = {primary: len(items) for primary, items in candidates.items() if items}
    apportioned = _apportion(nonempty, quota)
    selected = [
        item
        for primary in sorted(nonempty)
        for item in sorted(candidates[primary], key=lambda candidate: candidate.item_id)[: apportioned[primary]]
    ]
    return tuple(selected)


def select_math_medium(
    rows: Sequence[Mapping[str, JsonValue]],
    *,
    quota: int,
    seed: int = SELECTION_SEED,
) -> tuple[MediumMathItem, ...]:
    import hashlib
    import json

    strata: dict[str, list[tuple[int, Mapping[str, JsonValue]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        raw_topic = row.get("topic")
        topic = raw_topic if isinstance(raw_topic, str) and raw_topic else f"index-bucket-{index % 10:02d}"
        strata[topic].append((index, row))
    topics = sorted(strata)
    base_quota, remainder = divmod(quota, len(topics))
    selected: list[MediumMathItem] = []
    rng = random.Random(seed)
    topic_priority = topics.copy()
    rng.shuffle(topic_priority)
    bonuses = set(topic_priority[:remainder])
    for topic in topics:
        candidates = strata[topic].copy()
        rng.shuffle(candidates)
        count = base_quota + int(topic in bonuses)
        for index, row in sorted(candidates[:count], key=lambda pair: pair[0]):
            canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            selected.append(MediumMathItem(index, topic, hashlib.sha256(canonical).hexdigest()))
    if len(selected) != quota:
        raise ChecksetBuildError(f"Math medium draw produced {len(selected)} rows, expected {quota}.")
    return tuple(sorted(selected, key=lambda item: item.upstream_index))
