from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.cli import main
from localbench.submissions.canon import canonical_json_bytes, sha256_file
from localbench.submissions.projection import projection_object_sha256, rescore_admission_bundle

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PILOT = _REPO_ROOT / "runs" / "campaigns" / "wave0-gemma-12b-q4xl-cal-20260629" / "localbench-run.json"
_SUITE_V1 = _REPO_ROOT / "suite" / "v1"
pytestmark = pytest.mark.skipif(
    not _PILOT.exists(),
    reason="golden pilot run not present (source-repo artifact, excluded from the public snapshot)",
)
_BLOCKING_REASONS = [
    "sampler.top_k_unpinned",
    "sampler.seed_unpinned",
    "model.identity_missing",
    "runtime.identity_missing",
    "suite.not_site_released",
]
_VALIDATED_AT = "2026-06-30T00:00:00Z"


def test_verify_submission_rejects_pilot_with_exact_blockers(tmp_path: Path) -> None:
    # Given: the committed pilot bundle and output paths for verifier artifacts.
    projection_out = tmp_path / "pilot.projection.json"
    status_out = tmp_path / "pilot.status.json"

    # When: the authoritative offline verifier runs through the CLI.
    code = main(
        [
            "verify-submission",
            str(_PILOT),
            "--suite-dir",
            str(_SUITE_V1),
            "--projection-out",
            str(projection_out),
            "--out",
            str(status_out),
            "--validated-at",
            _VALIDATED_AT,
            "--validator-commit",
            "440f540",
        ],
    )

    # Then: it emits a rejected status update with the exact validation blockers.
    status = read_json(status_out)
    projection = read_json(projection_out)
    assert code == 0
    assert status == {
        "schema_version": "localbench.submission_status_update.v1",
        "accepted": False,
        "status": "rejected",
        "reason": ";".join(_BLOCKING_REASONS),
        "blocking_reasons": _BLOCKING_REASONS,
        "projection_sha256": projection["artifact_hashes"]["projection_sha256"],
        "projection_object_sha256": projection_object_sha256(projection),
        "projection": projection,
        "projection_path": str(projection_out),
        "raw_bundle_sha256": sha256_file(_PILOT),
        "validator_version": "localbench.submission-validator.v1",
        "validator_commit": "440f540",
        "validated_at": _VALIDATED_AT,
    }


def test_verify_submission_accepts_publishable_fixture_with_byte_identical_projection(
    tmp_path: Path,
) -> None:
    # Given: a synthetic publishable local result bundle derived from the pilot responses.
    bundle = write_publishable_fixture(tmp_path / "publishable-run.json")
    projection_out = tmp_path / "publishable.projection.json"
    status_out = tmp_path / "publishable.status.json"

    # When: the offline verifier writes the accepted projection.
    code = main(
        [
            "verify-submission",
            str(bundle),
            "--suite-dir",
            str(_SUITE_V1),
            "--projection-out",
            str(projection_out),
            "--out",
            str(status_out),
            "--validated-at",
            _VALIDATED_AT,
            "--validator-commit",
            "test-validator-commit",
        ],
    )

    # Then: the projection bytes match the authoritative rescorer exactly.
    expected_projection = rescore_admission_bundle(
        bundle,
        suite_dir=_SUITE_V1,
        validated_at=_VALIDATED_AT,
        origin="project_anchor",
        coding_verification=None,
    )
    status = read_json(status_out)
    assert code == 0
    assert projection_out.read_bytes() == canonical_json_bytes(expected_projection) + b"\n"
    assert status["accepted"] is True
    assert status["status"] == "accepted"
    assert status["reason"] == "publishable"
    assert status["blocking_reasons"] == []
    assert status["projection_sha256"] == expected_projection["artifact_hashes"]["projection_sha256"]


def write_publishable_fixture(path: Path) -> Path:
    record = json.loads(_PILOT.read_text(encoding="utf-8"))
    manifest = record["manifest"]
    manifest["sampling"] = {
        **manifest.get("sampling", {}),
        "top_k": 1,
        "seed": 12345,
        "determinism_policy": "top_k_1_seeded",
    }
    manifest["model"] = {
        "family": "gemma-4",
        "quant_label": "Q4_K_M",
        "file_name": "gemma-4-12b-it-Q4_K_M.gguf",
        "file_size_bytes": 1_234_567,
        "file_sha256": "a" * 64,
        "format": "gguf",
        "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64,
    }
    manifest["runtime"] = {
        "name": "llama.cpp",
        "version": "b1234",
        "kv_cache_quant": "f16",
        "ctx_len_configured": 32768,
        "parallel_slots": 1,
    }
    # Declare the site-released suite identity, as a runner that PULLED the site release would.
    # The publishable gate keys on this declared (release_id, suite_manifest_sha256) pair.
    manifest["suite"] = {
        **manifest.get("suite", {}),
        "suite_release_id": "suite-v1-partial-text-code-4axis-v1",
        "suite_manifest_sha256": "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7",
    }
    manifest["integrity"] = {}
    path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    return path


def read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data
