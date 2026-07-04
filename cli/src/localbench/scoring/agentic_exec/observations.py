"""Canonical tool-observation formatting."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from localbench._types import JsonValue

SIGNIFICANT_FLOAT_DIGITS = 6


@dataclass(frozen=True, slots=True)
class Observation:
    """Canonical observation text returned to the model."""

    text: str
    truncated: bool


def canonical_observation(value: JsonValue, *, char_limit: int) -> Observation:
    """Serialize an observation with sorted keys, stable floats, and a hard cap."""
    normalized = normalize_json(value)
    text = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(text) <= char_limit:
        return Observation(text=text, truncated=False)
    return Observation(text=text[:char_limit], truncated=True)


def normalize_json(value: JsonValue) -> JsonValue:
    """Normalize JSON-compatible values for stable serialization and hashing."""
    match value:  # noqa: MATCH_OK - open JSON boundary, not a closed variant.
        case float() as number:
            return _round_float(number)
        case list() as items:
            return [normalize_json(item) for item in items]
        case dict() as data:
            return {key: normalize_json(data[key]) for key in sorted(data)}
        case _:
            return value


def _round_float(number: float) -> JsonValue:
    if not math.isfinite(number):
        return str(number)
    return float(f"{number:.{SIGNIFICANT_FLOAT_DIGITS}g}")
