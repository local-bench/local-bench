"""Frozen lane-spec identity payloads."""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Final, Mapping

from localbench._types import JsonObject

DEFAULT_LANE_SPEC_ID: Final = "capped-thinking-v1"

LANE_SPECS: Final[Mapping[str, JsonObject]] = MappingProxyType(
    {
        DEFAULT_LANE_SPEC_ID: {
            "id": DEFAULT_LANE_SPEC_ID,
            "think_budget": 8192,
            "min_answer_budget": 1024,
            "forcing": "two-pass raw-completions force-close",
            "sampler_policy": "pinned greedy temp-0 seeded",
            "total_cap_source": "suite item max_tokens",
        },
    },
)


def lane_spec_digest(lane_id: str) -> str:
    """sha256 of one frozen lane-spec payload."""
    try:
        payload = LANE_SPECS[lane_id]
    except KeyError as exc:
        raise ValueError(f"unknown lane spec: {lane_id}") from exc
    return _digest(payload)


def _digest(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
