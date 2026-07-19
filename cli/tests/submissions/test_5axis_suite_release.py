from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.submissions.contracts import RESULT_BUNDLE_SCHEMA_VERSION
from localbench.submissions import foundation
from localbench.submissions.foundation import validate_submission_bundle

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SITE_5AXIS_MANIFEST = (
    _REPO_ROOT
    / "web"
    / "public"
    / "suites"
    / "suite-v1-text-code-agentic-5axis-v1"
    / "suite_release_manifest.json"
)


def test_validate_submission_bundle_rejects_site_released_5axis_suite_as_incomplete(
    tmp_path: Path,
) -> None:
    # Given: a synthetic bundle that declares the site-served 5-axis release identity.
    manifest = _read_json(_SITE_5AXIS_MANIFEST)
    bundle_path = tmp_path / "five-axis-result-bundle.json"
    bundle_path.write_text(
        json.dumps(_synthetic_5axis_result_bundle(manifest), sort_keys=True),
        encoding="utf-8",
    )

    # When: the authoritative validate-submission-bundle path validates it.
    result = validate_submission_bundle(bundle_path)

    # Then: a previously publishable five-axis release is no longer submittable.
    assert result["publishable"] is False
    assert result["blocking_reasons"] == ["incomplete_run"]
    assert result["missing_required_fields"] == []


def test_validate_submission_bundle_rejects_v2_exec_items_without_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_sha = "f" * 64
    monkeypatch.setitem(
        foundation._SITE_RELEASED_SUITES,
        "suite-v1-full-exec-6axis-v1",
        manifest_sha,
    )
    bundle = _synthetic_5axis_result_bundle(
        {
            "suite_release_id": "suite-v1-full-exec-6axis-v1",
            "suite_manifest_sha256": manifest_sha,
        },
    )
    bundle["benches"] = {
        **bundle["benches"],
        "bigcodebench_hard": {"n": 1, "n_errors": 0, "raw_accuracy": 0.0, "chance_corrected": 0.0},
        "olymmath_hard": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
        "amo": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
    }
    bundle["items"] = [{"id": "bcbh-001", "bench": "bigcodebench_hard"}]
    bundle_path = tmp_path / "full-exec-result-bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")

    result = validate_submission_bundle(bundle_path)

    assert result["publishable"] is False
    assert "missing_code_artifacts" in result["blocking_reasons"]


def _synthetic_5axis_result_bundle(release_manifest: JsonObject) -> JsonObject:
    return {
        "schema_version": RESULT_BUNDLE_SCHEMA_VERSION,
        "run_started_at": "2026-07-03T00:00:00Z",
        "run_finished_at": "2026-07-03T00:00:01Z",
        "producer": "localbench-cli",
        "tier": "standard",
        "serving_mode": "external_openai_compatible_endpoint",
        "model": {},
        "manifest": {
            "suite": {
                "suite_release_id": release_manifest["suite_release_id"],
                "suite_manifest_sha256": release_manifest["suite_manifest_sha256"],
            },
            "sampling": {
                "temperature": 0,
                "top_k": 1,
                "top_p": 1,
                "min_p": 0,
                "seed": 123,
                "determinism_policy": "top_k_1_seeded",
            },
            "model": {
                "family": "gemma",
                "quant_label": "Q4_K_M",
                "file_name": "model.gguf",
                "file_size_bytes": 11,
                "file_sha256": "a" * 64,
                "format": "gguf",
                "tokenizer_digest": "b" * 64,
                "chat_template_digest": "c" * 64,
            },
            "runtime": {
                "name": "llama.cpp",
                "version": "b1234",
                "kv_cache_quant": "q8_0",
                "ctx_len_configured": 8192,
                "parallel_slots": 1,
                "build_flags": "cuda",
            },
            "provenance": {},
        },
        "axis_status": {},
        "headline_complete": True,
        "scores": {},
        "benches": {
            "mmlu_pro": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
            "ifbench": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
            "tc_json_v1": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
            "lcb": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
            "appworld_c": {"n": 1, "n_errors": 0, "raw_accuracy": 1.0, "chance_corrected": 1.0},
        },
        "conformance": {},
        "items": [],
        "totals": {},
        "warnings": [],
    }


def _read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data
