from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.submissions.contracts import (
    ACCEPTED_RESULT_PROJECTION_SCHEMA,
    ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
    RESULT_BUNDLE_SCHEMA,
    RESULT_BUNDLE_SCHEMA_VERSION,
    SUBMISSION_ENVELOPE_SCHEMA,
    SUBMISSION_ENVELOPE_SCHEMA_VERSION,
    load_schema,
)
from localbench.submissions.foundation import (
    normalize_result_bundle,
    rescore_bundle,
    validate_accepted_result_projection,
    validate_result_bundle,
    validate_submission_bundle,
    validate_submission_envelope,
)
from localbench.submissions.validate import SubmissionValidationError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PILOT = _REPO_ROOT / "runs" / "campaigns" / "wave0-gemma-12b-q4xl-cal-20260629" / "localbench-run.json"
_SUITE_V1 = _REPO_ROOT / "suite" / "v1"
_REQUIRES_PILOT = pytest.mark.skipif(
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
_SITE_RELEASE_ID = "suite-v1-partial-text-code-4axis-v1"
_SITE_MANIFEST_SHA256 = "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7"


def test_contract_schema_versions_are_split_and_loadable() -> None:
    # Given / When: the foundation schemas are loaded from package data.
    result_schema = load_schema(RESULT_BUNDLE_SCHEMA)
    envelope_schema = load_schema(SUBMISSION_ENVELOPE_SCHEMA)
    projection_schema = load_schema(ACCEPTED_RESULT_PROJECTION_SCHEMA)

    # Then: each contract has its own frozen schema identity.
    assert result_schema["properties"]["schema_version"]["const"] == RESULT_BUNDLE_SCHEMA_VERSION
    assert envelope_schema["properties"]["schema_version"]["const"] == SUBMISSION_ENVELOPE_SCHEMA_VERSION
    assert projection_schema["properties"]["schema_version"]["const"] == ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION


@_REQUIRES_PILOT
def test_result_bundle_normalization_moves_auth_and_trust_out_of_measurement() -> None:
    # Given: the pilot's legacy localbench.run.v1 record.
    legacy = json.loads(_PILOT.read_text(encoding="utf-8"))

    # When: it is normalized to result_bundle_v1.
    bundle = normalize_result_bundle(legacy, suite_dir=_SUITE_V1)
    validation = validate_result_bundle(bundle)

    # Then: submitter/auth fields and verifier-authored trust fields are absent.
    assert bundle["schema_version"] == RESULT_BUNDLE_SCHEMA_VERSION
    for removed in (
        "schema",
        "submission_ticket_id",
        "server_nonce",
        "issued_at",
        "account",
        "trust_tier",
        "serving_verification_level",
        "composite",
        "source",
        "output_path",
    ):
        assert removed not in bundle
    assert bundle["serving_mode"] == "external_openai_compatible_endpoint"
    assert bundle["scores"] == {
        "headline_score": None,
        "partial_composite": 0.7569,
        "partial_composite_scope": "measured_headline_axes",
        "measured_headline_weight": 0.55,
        "missing_headline_weight": 0.45,
        "known_headline_contribution": 0.4163,
        "rank_scope": "partial-text-code-4axis-v1",
        "composite_static": None,
        "composite_full": None,
    }
    assert bundle["manifest"]["integrity"]["publishable"] is False
    assert validation.blocking_reasons == _BLOCKING_REASONS


def test_envelope_and_projection_contracts_validate_board_safe_payloads() -> None:
    # Given: an envelope and a minimal board-safe projection.
    envelope = {
        "schema_version": SUBMISSION_ENVELOPE_SCHEMA_VERSION,
        "ticket_id": "ticket-1",
        "submitter_id": "owner",
        "origin": "project_anchor",
        "allowed_schema": RESULT_BUNDLE_SCHEMA_VERSION,
        "expected_suite_release_id": None,
        "expected_suite_manifest_sha256": None,
        "accepted_suite_terms": True,
        "max_upload_bytes": 25_000_000,
        "expiry": "2026-07-01T00:00:00Z",
        "one_use": True,
        "declared_model_slug": "gemma-4-12b",
        "bundle_sha256": "a" * 64,
    }
    projection = {
        "schema_version": ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
        "model": {"display_name": "Gemma", "declared_name": "Gemma", "file_sha256": "b" * 64, "quant_label": "Q4", "identity_status": "maintainer_verified", "model_system_key": f"artifact:{'b' * 64}"},
        "lineage": {"base_model": []},
        "runtime": {"name": "llama.cpp", "version": "1"},
        "suite_release_id": "suite-v1-partial-text-code-4axis-v1",
        "suite_manifest_sha256": _SITE_MANIFEST_SHA256,
        "scorecard_id": "scorecard",
        "coverage_profile_id": "partial-text-code-4axis-v1",
        "headline_complete": False,
        "scores": {
            "headline_score": None,
            "partial_composite": 0.7473,
            "partial_composite_scope": "measured_headline_axes",
            "measured_headline_weight": 0.5,
            "missing_headline_weight": 0.5,
            "known_headline_contribution": 0.3737,
            "rank_scope": "partial-text-code-4axis-v1",
        },
        "axes": {"knowledge": {"score": 0.7725, "n": 400, "ci": None, "status": "measured"}},
        "conformance": {"status": "headline-comparable"},
        "receipt_references": {"coding_receipt_sha256": None},
        "artifact_hashes": {
            "bundle_sha256": "d" * 64,
            "projection_sha256": "e" * 64,
            "public_artifact_manifest_sha256": "f" * 64,
        },
        "origin": "project_anchor",
        "trust_label": "community_re_scored",
        "verification_level": "bundle_rescored",
        "agentic_provenance": "none",
        "rescore_modes": {},
        "validator": {
            "validator_version": "localbench.submission-validator.v1",
            "commit": None,
            "validated_at": "2026-06-30T00:00:00Z",
        },
    }

    # When / Then: both contracts validate without trusting submitter-authored board fields.
    validate_submission_envelope(envelope)
    validate_accepted_result_projection(projection)


def test_submission_envelope_normalizes_legacy_origin_and_rejects_unknown() -> None:
    envelope = {
        "schema_version": SUBMISSION_ENVELOPE_SCHEMA_VERSION,
        "ticket_id": "ticket-1",
        "submitter_id": "owner",
        "origin": "community_submission",
        "allowed_schema": RESULT_BUNDLE_SCHEMA_VERSION,
        "expected_suite_release_id": None,
        "expected_suite_manifest_sha256": None,
        "accepted_suite_terms": True,
        "max_upload_bytes": 25_000_000,
        "expiry": "2026-07-01T00:00:00Z",
        "one_use": True,
        "bundle_sha256": "a" * 64,
    }

    validate_submission_envelope(envelope)

    assert envelope["origin"] == "community"

    envelope["origin"] = "unexpected"
    with pytest.raises(SubmissionValidationError, match="origin"):
        validate_submission_envelope(envelope)


@_REQUIRES_PILOT
def test_pilot_fixture_validates_not_publishable_with_exact_blockers() -> None:
    # Given / When: the pilot result bundle is validated offline.
    result = validate_submission_bundle(_PILOT, suite_dir=_SUITE_V1)

    # Then: it is accepted as calibration data but not publishable.
    assert result["schema_version"] == "localbench.submission_validation.v1"
    assert result["publishable"] is False
    assert result["blocking_reasons"] == _BLOCKING_REASONS
    assert result["missing_required_fields"] == [
        "model.family",
        "model.quant_label",
        "model.file_name",
        "model.file_size_bytes",
        "model.file_sha256",
        "model.format",
        "model.tokenizer_digest",
        "model.chat_template_digest",
        "runtime.name",
        "runtime.version",
        "runtime.kv_cache_quant",
        "runtime.ctx_len_configured",
        "runtime.parallel_slots",
    ]


def test_synthetic_bundle_validation_clears_sampler_model_and_runtime_blockers(tmp_path: Path) -> None:
    # Given: two site-released synthetic result bundles, one with publishable identity and one empty.
    populated = tmp_path / "populated.json"
    empty = tmp_path / "empty.json"
    populated.write_text(
        json.dumps(_synthetic_result_bundle(identity=True), sort_keys=True),
        encoding="utf-8",
    )
    empty.write_text(
        json.dumps(_synthetic_result_bundle(identity=False), sort_keys=True),
        encoding="utf-8",
    )

    # When: the authoritative validate-submission-bundle path validates both bundles.
    populated_result = validate_submission_bundle(populated)
    empty_result = validate_submission_bundle(empty)

    # Then: the populated bundle clears the sampler/model/runtime blockers.
    assert populated_result["publishable"] is True
    assert populated_result["blocking_reasons"] == []
    assert populated_result["missing_required_fields"] == []

    # And: absent fields still produce the exact blocker codes.
    assert empty_result["publishable"] is False
    assert empty_result["blocking_reasons"] == [
        "sampler.top_k_unpinned",
        "sampler.seed_unpinned",
        "model.identity_missing",
        "runtime.identity_missing",
    ]


def test_result_bundle_normalization_preserves_optional_perf_and_item_timings() -> None:
    timings = {
        "passes": [{"prompt_n": 10, "prompt_ms": 20.0, "predicted_n": 5, "predicted_ms": 10.0}]
    }
    perf = {
        "timings_source": "llama.cpp",
        "timings_coverage": 1.0,
        "prefill_tps": 500.0,
        "decode_tps": 500.0,
        "prompt_ms_median": 20.0,
        "prompt_ms_p95": 20.0,
        "predicted_ms_median": 10.0,
        "predicted_ms_p95": 10.0,
        "ttft_proxy_ms_median": 20.0,
        "per_bench": {
            "mmlu_pro": {
                "prefill_tps": 500.0,
                "decode_tps": 500.0,
                "prompt_ms_median": 20.0,
                "n": 1,
            }
        },
    }
    record = _synthetic_result_bundle(identity=True)
    record["schema"] = "localbench-run-v0"
    record["perf"] = perf
    record["axis_status"] = {"schema_version": "localbench.axis-status.v1", "axes": {}}
    record["items"] = [{"id": "item-1", "bench": "mmlu_pro", "server_timings": timings}]

    bundle = normalize_result_bundle(record)
    validation = validate_result_bundle(bundle)

    assert validation.blocking_reasons == []
    assert bundle["perf"] == perf
    assert bundle["items"] == [{"id": "item-1", "bench": "mmlu_pro", "server_timings": timings}]


def test_normalized_published_record_contains_no_absolute_local_paths() -> None:
    record = _synthetic_result_bundle(identity=True)
    record["serving"] = {
        "launch": {
            "argv": [
                r"C:\Users\Michael\llama.cpp\llama-server.exe",
                "--model",
                r"C:\Users\Michael\models\model.gguf",
            ],
            "cwd": r"C:\Users\Michael\local-bench",
        },
        "artifact": {"executable_sha256": "a" * 64},
    }
    record["agentic_run"] = {
        "wsl_identity": {
            "localbench_distribution_version": "0.3.1",
            "worker_content_sha256": "b" * 64,
            "venv_path": "/home/michael/venv",
            "bwrap_path": "/home/michael/bin/bwrap",
            "appworld_root": "/mnt/c/Users/Michael/appworld",
        },
        "runs": [
            {
                "run_index": 1,
                "results_path": "/mnt/c/Users/Michael/run/agentic/results.json",
            },
        ],
        "agentic_sandbox_identity": {
            "appworld_root": "/HOME/OtherOperator/appworld-data",
        },
    }
    record["items"] = [
        {
            "id": "nested-paths",
            "debug": {
                "windows": r"failed at c:/uSeRs/Alice/private/file.txt",
                "mounted": r"failed at \\MNT\\C\\USERS\\Bob\\private\\file.txt",
                "sandbox": "failed at /tmp/localbench-task/prog.py",
            },
        },
    ]

    bundle = normalize_result_bundle(record)
    serialized = json.dumps(bundle, sort_keys=True).replace("\\\\", "/")

    assert "C:/Users/" not in serialized
    assert "/home/" not in serialized
    assert "/mnt/c/Users/" not in serialized
    assert "Alice" not in serialized
    assert "Bob" not in serialized
    assert "OtherOperator" not in serialized
    assert "/tmp/localbench-task/prog.py" in serialized
    assert bundle["serving"]["launch"]["argv"] == [
        "llama-server.exe",
        "--model",
        "model.gguf",
    ]
    assert len(bundle["serving"]["launch"]["cwd_sha256"]) == 64
    assert bundle["serving"]["artifact"]["executable_sha256"] == "a" * 64
    assert bundle["agentic_run"]["wsl_identity"]["worker_content_sha256"] == "b" * 64
    assert "results_path" not in bundle["agentic_run"]["runs"][0]


def test_missing_manifest_version_normalizes_to_installed_version_not_legacy_default() -> None:
    record = _synthetic_result_bundle(identity=True)

    bundle = normalize_result_bundle(record)

    assert bundle["manifest"]["provenance"]["cli_version"] == "0.3.1"


@_REQUIRES_PILOT
def test_offline_foundation_cli_commands_write_artifacts(tmp_path: Path) -> None:
    from localbench.cli import main

    # Given: the pilot bundle and the authoritative suite directory.
    validation_out = tmp_path / "validation.json"
    projection_out = tmp_path / "projection.json"

    # When: the offline validation and rescore commands run.
    validation_code = main(
        [
            "validate-submission-bundle",
            str(_PILOT),
            "--suite-dir",
            str(_SUITE_V1),
            "--out",
            str(validation_out),
        ],
    )
    rescore_code = main(
        [
            "rescore-bundle",
            str(_PILOT),
            "--suite-dir",
            str(_SUITE_V1),
            "--out",
            str(projection_out),
            "--validated-at",
            "2026-06-30T00:00:00Z",
        ],
    )

    # Then: validation still succeeds, while strict projection v2 rejects the locally
    # rebuilt suite digest because it is not the published allowlisted pair.
    assert validation_code == 0
    assert rescore_code == 2
    assert json.loads(validation_out.read_text(encoding="utf-8")) == validate_submission_bundle(
        _PILOT,
        suite_dir=_SUITE_V1,
    )
    assert not projection_out.exists()


@_REQUIRES_PILOT
def test_pilot_rescore_reproduces_numbers_and_is_byte_identical() -> None:
    # The source-repo pilot predates the published release manifest. Projection v2 must
    # not silently bless a locally rebuilt digest under the published release id.
    with pytest.raises(SubmissionValidationError, match="suite_manifest_sha256"):
        rescore_bundle(_PILOT, suite_dir=_SUITE_V1, validated_at="2026-06-30T00:00:00Z")


def test_validate_submission_bundle_accepts_structured_determinism_policy(
    tmp_path: Path,
) -> None:
    # Given: a publishable bundle whose determinism_policy is the structured object the
    # serve-orchestrator records (not the legacy string form).
    bundle = _synthetic_result_bundle(identity=True)
    manifest = bundle["manifest"]
    assert isinstance(manifest, dict)
    sampling = manifest["sampling"]
    assert isinstance(sampling, dict)
    sampling["determinism_policy"] = {
        "policy_id": "gpu-greedy-single-slot-v1",
        "claim": "best-effort same-stack reproducibility; not bitwise cross-stack determinism",
        "client": {"temperature": 0, "top_k": 1, "seed": 123, "concurrency": 1},
    }
    path = tmp_path / "structured.json"
    path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")

    # When: the authoritative validate-submission-bundle path validates it.
    result = validate_submission_bundle(path)

    # Then: a structured policy counts as present — no crash, no missing-policy blocker.
    assert result["publishable"] is True
    assert result["blocking_reasons"] == []


def _synthetic_result_bundle(*, identity: bool) -> dict[str, object]:
    manifest = {
        "suite": {
            "suite_release_id": _SITE_RELEASE_ID,
            "suite_manifest_sha256": _SITE_MANIFEST_SHA256,
        },
        "sampling": {},
        "model": {},
        "runtime": {},
        "provenance": {},
    }
    if identity:
        manifest["sampling"] = {
            "temperature": 0,
            "top_k": 1,
            "top_p": 1,
            "min_p": 0,
            "seed": 123,
            "determinism_policy": "top_k_1_seeded",
        }
        manifest["model"] = {
            "family": "gemma",
            "quant_label": "Q4_K_M",
            "file_name": "model.gguf",
            "file_size_bytes": 11,
            "file_sha256": "a" * 64,
            "format": "gguf",
            "tokenizer_digest": "b" * 64,
            "chat_template_digest": "c" * 64,
        }
        manifest["runtime"] = {
            "name": "llama.cpp",
            "version": "b1234",
            "kv_cache_quant": "q8_0",
            "ctx_len_configured": 8192,
            "parallel_slots": 1,
            "build_flags": "cuda",
        }
    return {
        "schema_version": RESULT_BUNDLE_SCHEMA_VERSION,
        "run_started_at": "2026-06-30T00:00:00Z",
        "run_finished_at": "2026-06-30T00:00:01Z",
        "producer": "localbench-cli",
        "tier": "standard",
        "serving_mode": "external_openai_compatible_endpoint",
        "model": {},
        "manifest": manifest,
        "axis_status": {},
        "headline_complete": False,
        "scores": {},
        "benches": {},
        "conformance": {},
        "items": [],
        "totals": {},
        "warnings": [],
    }
