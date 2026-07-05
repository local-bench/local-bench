"""Frozen lane-spec identity payloads."""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Final, Mapping

from localbench._types import JsonObject

DEFAULT_LANE_SPEC_ID: Final = "capped-thinking-v1"
BOUNDED_FINAL_LANE_SPEC_ID: Final = "bounded-final-v1"
BOUNDED_FINAL_MIN_FINAL: Final = 1024
BOUNDED_FINAL_THINK_CAP: Final = 8192

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
        BOUNDED_FINAL_LANE_SPEC_ID: {
            "id": BOUNDED_FINAL_LANE_SPEC_ID,
            "total_cap_source": "suite item max_tokens",
            "min_final": BOUNDED_FINAL_MIN_FINAL,
            "think_cap": BOUNDED_FINAL_THINK_CAP,
            "think_budget_formula": "min(8192, max(0, T_i - 1024))",
            "answer_budget": "T_i - reasoning_tokens_used",
            "execution_profiles_per_run": 1,
            "scored_text": "final_text_only",
            "sampler_policy": "pinned greedy temp-0 seeded",
        },
    },
)


def bounded_final_think_budget(total_cap: int) -> int:
    return min(BOUNDED_FINAL_THINK_CAP, max(0, total_cap - BOUNDED_FINAL_MIN_FINAL))


def lane_spec_id_for_lane(lane: str) -> str:
    if lane == BOUNDED_FINAL_LANE_SPEC_ID:
        return BOUNDED_FINAL_LANE_SPEC_ID
    return DEFAULT_LANE_SPEC_ID


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
