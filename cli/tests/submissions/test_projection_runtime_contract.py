"""Projection runtime must be the frozen-contract view of the bundle's runtime object.

Found 2026-07-15 by the maintainer's local admission probe against the three real pending
ticket bundles: every 2026-07 full-exec bundle carries ``runtime.backend`` (added to the
harness after AcceptedResultProjectionV2 froze with ``additionalProperties: false``), so a
wholesale copy of the manifest runtime makes every admission projection schema-invalid. The
coding-status enum gap masked this on 2026-07-14 (jsonschema reports one error at a time).
"""

from __future__ import annotations

import json
from pathlib import Path

from localbench.submissions.projection import _RUNTIME_PROJECTION_KEYS, _projection_runtime

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "localbench"
    / "submissions"
    / "schemas"
    / "accepted_result_projection_v2.schema.json"
)

# Verbatim shape of the runtime object in the real pending ticket bundle
# (raw_bundle_sha256 d9447a25a773a559f133d34f3da8c4202d5dd26011fb7d02b8307375fe1c44b7,
# gemma-4-12b QAT UD-Q2_K_XL full-exec run) — the "backend" key is the post-freeze addition.
_REAL_BUNDLE_RUNTIME = {
    "backend": "cuda",
    "build_flags": "version: 9852 (fd1a05791)\nbuilt with Clang 20.1.8 for Windows x86_64",
    "ctx_len_configured": 32768,
    "kv_cache_quant": "k=f16,v=f16",
    "name": "llama.cpp",
    "parallel_slots": 1,
    "version": "b9852/fd1a05791",
}


def test_runtime_projection_keys_match_frozen_schema() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    runtime_schema = schema["properties"]["runtime"]
    assert runtime_schema["additionalProperties"] is False
    assert tuple(sorted(runtime_schema["properties"].keys())) == _RUNTIME_PROJECTION_KEYS


def test_projection_runtime_drops_post_freeze_bundle_keys() -> None:
    projected = _projection_runtime({"runtime": dict(_REAL_BUNDLE_RUNTIME)})
    assert "backend" not in projected
    assert projected == {
        key: value for key, value in _REAL_BUNDLE_RUNTIME.items() if key != "backend"
    }


def test_projection_runtime_keeps_only_present_keys() -> None:
    projected = _projection_runtime({"runtime": {"name": "llama.cpp", "version": "b9852"}})
    assert projected == {"name": "llama.cpp", "version": "b9852"}
