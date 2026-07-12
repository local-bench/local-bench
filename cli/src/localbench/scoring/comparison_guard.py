"""Fail-closed guards for composite comparisons and lineage deltas."""

from __future__ import annotations

from collections.abc import Mapping

from localbench._types import JsonValue
from localbench.scoring.editorial import record_index_version


def assert_same_index_version(
    left: Mapping[str, JsonValue],
    right: Mapping[str, JsonValue],
    *,
    context: str = "composite comparison",
) -> str:
    left_version = record_index_version(left)
    right_version = record_index_version(right)
    if left_version != right_version:
        raise ValueError(
            f"{context} requires matching index_version labels: "
            f"{left_version!r} != {right_version!r}",
        )
    return left_version


def lineage_composite_delta(
    derivative: Mapping[str, JsonValue],
    base: Mapping[str, JsonValue],
    *,
    composite_field: str = "composite",
) -> float:
    """Return a same-season derivative-minus-base point delta."""
    assert_same_index_version(derivative, base, context="lineage composite delta")
    return _point(
        derivative.get(composite_field), f"derivative.{composite_field}"
    ) - _point(
        base.get(composite_field),
        f"base.{composite_field}",
    )


def _point(value: JsonValue | None, context: str) -> float:
    if isinstance(value, dict):
        value = value.get("point_raw", value.get("point"))
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{context} must carry a numeric point")
    return float(value)
