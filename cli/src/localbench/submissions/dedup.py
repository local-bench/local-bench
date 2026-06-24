from __future__ import annotations

from collections.abc import Sequence

from localbench._types import JsonObject
from localbench.submissions.canon import canonical_json_hash


def dedup_keys(bundle_sha256: str, manifest: JsonObject, items: Sequence[JsonObject]) -> JsonObject:
    payload = manifest.get("payload")
    payload_hash = manifest.get("payload_sha256")
    return {
        "bundle_sha256": bundle_sha256,
        "manifest_payload_sha256": payload_hash if isinstance(payload_hash, str) else "",
        "manifest_sha256": canonical_json_hash(payload if isinstance(payload, dict) else {}),
        "item_hashes": [canonical_json_hash(item) for item in items],
    }
