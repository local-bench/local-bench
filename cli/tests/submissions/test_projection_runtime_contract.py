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

import localbench.submissions.projection as projection_mod

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


def test_run_environment_projection_blocks_are_optional_in_schema() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert "runtime" not in schema["required"]
    assert "hardware" not in schema["required"]
    assert "perf" not in schema["required"]


def test_projection_runtime_emits_the_frozen_board_summary() -> None:
    projected = projection_mod._projection_runtime({"runtime": dict(_REAL_BUNDLE_RUNTIME)})
    assert projected == {
        "backend": "cuda",
        "name": "llama.cpp",
        "version": "b9852/fd1a05791",
    }


def test_projection_runtime_uses_nulls_for_missing_sources() -> None:
    projected = projection_mod._projection_runtime({"runtime": {"name": "llama.cpp"}})
    assert projected == {"backend": None, "name": "llama.cpp", "version": None}


def test_projection_lineage_uses_manifest_base_model_declaration() -> None:
    # Given: a run manifest with a declared Hugging Face base model.
    manifest = {"model": {"base_model": "Qwen/Qwen3.6-27B"}}

    # When: the accepted-result lineage block is projected.
    projected = projection_mod._projection_lineage(manifest)

    # Then: the declaration is retained as a one-entry lineage list.
    assert projected == {"base_model": ["Qwen/Qwen3.6-27B"]}


def test_projection_lineage_is_empty_without_a_manifest_declaration() -> None:
    # Given: a run manifest without a base-model declaration.
    manifest = {"model": {"family": "Qwen3.6"}}

    # When: the accepted-result lineage block is projected.
    projected = projection_mod._projection_lineage(manifest)

    # Then: no lineage identity is invented.
    assert projected == {"base_model": []}


def test_projection_hardware_uses_first_gpu_and_rounds_vram_gb() -> None:
    projected = projection_mod._projection_hardware(
        {"hardware": {"gpus": [{"name": "RTX 4090", "vram_mb": 24564}, {"name": "ignored"}]}},
    )
    assert projected == {"gpu_name": "RTX 4090", "vram_gb": 24.0}


def test_projection_perf_uses_perf_totals_and_median_item_completion_tokens() -> None:
    # Given: a run bundle with measured prefill/decode throughput and aggregate totals.
    bundle = {
        "items": [
            {"usage": {"completion_tokens": 9}},
            {"usage": {"completion_tokens": 3}},
            {"usage": {"completion_tokens": None}},
            {"usage": {"completion_tokens": 6}},
        ],
        "perf": {"prefill_tps": 1620.5, "decode_tps": 81.25},
        "totals": {
            "completion_tokens_per_second": 64.5,
            "wall_time_seconds": 12,
        },
    }

    # When: the public submission perf block is projected.
    projected = projection_mod._projection_perf(bundle)

    # Then: both throughput sources and the existing perf fields are retained.
    assert projected == {
        "decode_tps": 81.25,
        "overall_tps": 64.5,
        "prefill_tps": 1620.5,
        "tokens_to_answer_median": 6.0,
        "wall_time_seconds": 12.0,
    }


def test_projection_perf_omits_optional_throughput_when_sources_are_missing() -> None:
    # Given: a run bundle without a perf block or aggregate throughput.
    bundle = {"totals": {"wall_time_seconds": 12}}

    # When: the public submission perf block is projected.
    projected = projection_mod._projection_perf(
        bundle,
    )

    # Then: the additive throughput keys are omitted rather than null-filled.
    assert projected == {
        "decode_tps": None,
        "tokens_to_answer_median": None,
        "wall_time_seconds": 12.0,
    }
    assert "prefill_tps" not in projected
    assert "overall_tps" not in projected
