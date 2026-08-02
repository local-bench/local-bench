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
class AimeMathItem:
    upstream_index: int
    subject: str
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
) -> tuple[SourceItem, ...]:
    primary_strata: dict[str, list[SourceItem]] = defaultdict(list)
    for item in items:
        if not item.instruction_ids:
            raise ChecksetBuildError(f"IFBench item {item.item_id!r} has no instruction ids.")
        primary = min(item.instruction_ids)
        primary_strata[primary].append(item)
    selected: list[SourceItem] = []
    for family, quota in quotas.items():
        candidates: list[tuple[float, bool, str, SourceItem]] = []
        for primary, stratum in primary_strata.items():
            if primary.split(":", 1)[0] != family:
                continue
            ranked = sorted(stratum, key=lambda item: (not item.informative, item.item_id))
            denominator = max(1, len(ranked) - 1)
            candidates.extend(
                (rank / denominator, not item.informative, item.item_id, item)
                for rank, item in enumerate(ranked)
            )
        if len(candidates) < quota:
            raise ChecksetBuildError(f"IFBench stratum {family!r} has {len(candidates)} items for quota {quota}.")
        selected.extend(item for _, _, _, item in sorted(candidates, key=lambda candidate: candidate[:3])[:quota])
    return tuple(selected)


def select_math_aime(
    rows: Sequence[Mapping[str, JsonValue]],
    *,
    quota: int,
    seed: int = SELECTION_SEED,
) -> tuple[AimeMathItem, ...]:
    import hashlib
    import json

    if not rows:
        raise ChecksetBuildError("OlymMATH en-easy input is empty.")
    strata: dict[str, list[tuple[int, Mapping[str, JsonValue]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        raw_topic = row.get("subject")
        topic = raw_topic if isinstance(raw_topic, str) and raw_topic else f"index-bucket-{index % 10:02d}"
        strata[topic].append((index, row))
    topics = sorted(strata)
    base_quota, remainder = divmod(quota, len(topics))
    selected: list[AimeMathItem] = []
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
            selected.append(AimeMathItem(index, topic, hashlib.sha256(canonical).hexdigest()))
    if len(selected) != quota:
        raise ChecksetBuildError(f"Math AIME-band draw produced {len(selected)} rows, expected {quota}.")
    return tuple(sorted(selected, key=lambda item: item.upstream_index))
