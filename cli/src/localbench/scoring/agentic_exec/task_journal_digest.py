from __future__ import annotations

from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.submissions.canon import canonical_json_hash

_EXCLUDED_DIGEST_KEYS: Final = frozenset(
    {
        "elapsed_ms",
        "latency",
        "latency_ms",
        "latency_seconds",
        "payload_sha256",
        "segment",
        "segment_id",
        "segment_metadata",
        "segments",
        "server_timings",
        "timestamp",
        "timestamps",
        "written_at",
    }
)


def canonical_result_digest(
    accepted_envelopes: list[JsonObject],
    *,
    third_run_decision: JsonObject | None,
) -> str:
    canonical: JsonObject = {
        "accepted_envelopes": [_digest_view(envelope) for envelope in accepted_envelopes],
        "third_run_decision": _digest_view(third_run_decision),
    }
    return canonical_json_hash(canonical)


def _digest_view(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        result: JsonObject = {}
        for key, child in value.items():
            lowered = key.casefold()
            if (
                lowered in _EXCLUDED_DIGEST_KEYS
                or lowered.endswith("_path")
                or lowered.endswith("_timestamp")
                or lowered.endswith("_latency")
                or lowered.endswith("_at")
            ):
                continue
            result[key] = _digest_view(child)
        return result
    if isinstance(value, list):
        return [_digest_view(item) for item in value]
    return value
