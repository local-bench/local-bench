from __future__ import annotations

import json
from pathlib import Path

from localbench.submissions.foundation import validate_submission_bundle

from .test_5axis_suite_release import _synthetic_5axis_result_bundle


def test_validate_submission_bundle_keeps_null_coding_verdicts_publishable_on_other_axes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: a site-released full-exec bundle has BigCodeBench artifacts but no verifier verdict.
    manifest_sha = "f" * 64
    monkeypatch.setitem(
        __import__("localbench.submissions.foundation", fromlist=["_SITE_RELEASED_SUITES"])._SITE_RELEASED_SUITES,
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
    bundle["axis_status"] = {
        "schema_version": "localbench.axis_status.v1",
        "axes": {
            "coding": {
                "status": "generated_unverified",
                "reason": "verdict_pending",
                "detail": "BigCodeBench-Hard artifacts generated; verifier verdict pending",
            },
        },
    }
    bundle["items"] = [
        {
            "id": "bcbh-001",
            "bench": "bigcodebench_hard",
            "code_artifact": {
                "raw_text_sha256": "a" * 64,
                "extracted_code": "def task_func(x):\n    return x",
                "sanitized_code": "def task_func(x):\n    return x",
                "assembly_recipe_id": "bigcodebench-python-unittest-v2",
                "assembled_program_sha256": "b" * 64,
                "item_record_sha": "c" * 64,
                "prompt_content_sha": "d" * 64,
                "test_sha": "e" * 64,
                "ast_gate_rev": "ast-gate-v1",
                "sentinel_scheme_rev": "sentinel-v1",
                "extractor_rev": "extractor-v1",
                "harness_rev": "f" * 64,
                "image_digest": None,
                "verdict": None,
                "verdict_source": None,
            },
        },
    ]
    bundle_path = tmp_path / "community-full-exec-null-coding-verdict.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")

    # When: the submission validator runs the publishability gate.
    result = validate_submission_bundle(bundle_path)

    # Then: missing verifier verdicts do not become a hard reject; ZT-1 handles ranking visibility.
    assert result["publishable"] is True
    assert result["blocking_reasons"] == []
