from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Protocol

from localbench._types import JsonValue


class PointModel(Protocol):
    model_name: str
    record: Mapping[str, JsonValue]
    composite: float | None


def axis_point_biserial(
    models: Sequence[PointModel],
    benches: Sequence[str],
    notes: list[str],
) -> float | None:
    observations: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for model in models:
        if model.composite is None:
            continue
        for item_key, correct in _axis_items(model, benches, notes).items():
            observations.setdefault(item_key, []).append(
                (1.0 if correct else 0.0, model.composite),
            )
    correlations = [_correlation(values) for values in observations.values()]
    defined = [value for value in correlations if value is not None]
    if not defined:
        notes.append("axis point-biserial unavailable: no item has varying correctness")
        return None
    return sum(defined) / len(defined)


def _axis_items(
    model: PointModel,
    benches: Sequence[str],
    notes: list[str],
) -> dict[tuple[str, str], bool]:
    bench_set = set(benches)
    raw_items = model.record.get("items")
    if not isinstance(raw_items, list):
        notes.append(f"{model.model_name}: missing items list")
        return {}
    items: dict[tuple[str, str], bool] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            continue
        bench = raw_item.get("bench")
        item_id = raw_item.get("id")
        correct = raw_item.get("correct")
        if not isinstance(bench, str) or bench not in bench_set:
            continue
        if isinstance(item_id, str) and isinstance(correct, bool):
            items[(bench, item_id)] = correct
        else:
            notes.append(f"{model.model_name}: skipped incomplete item on {bench}")
    return items


def _correlation(values: Sequence[tuple[float, float]]) -> float | None:
    if len(values) < 2:
        return None
    x_mean = sum(value[0] for value in values) / len(values)
    y_mean = sum(value[1] for value in values) / len(values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in values)
    x_ss = sum((x - x_mean) ** 2 for x, _y in values)
    y_ss = sum((y - y_mean) ** 2 for _x, y in values)
    denominator = math.sqrt(x_ss * y_ss)
    if denominator == 0:
        return None
    return numerator / denominator
