from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.submissions.canon import canonical_json_bytes
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
_BLOCKING_REASONS = [
    "sampler.top_k_unpinned",
    "sampler.seed_unpinned",
    "model.identity_missing",
    "runtime.identity_missing",
    "suite.not_site_released",
]
_SITE_RELEASE_ID = "suite-v1-partial-text-code-4axis-v1"
_SITE_MANIFEST_SHA256 = "b3fc40191c366d87b5537b12daa3d5c3680035238492c47996ab1f1b00d32231"


def test_contract_schema_versions_are_split_and_loadable() -> None:
    # Given / When: the foundation schemas are loaded from package data.
    result_schema = load_schema(RESULT_BUNDLE_SCHEMA)
    envelope_schema = load_schema(SUBMISSION_ENVELOPE_SCHEMA)
    projection_schema = load_schema(ACCEPTED_RESULT_PROJECTION_SCHEMA)

    # Then: each contract has its own frozen schema identity.
    assert result_schema["properties"]["schema_version"]["const"] == RESULT_BUNDLE_SCHEMA_VERSION
    assert envelope_schema["properties"]["schema_version"]["const"] == SUBMISSION_ENVELOPE_SCHEMA_VERSION
    assert projection_schema["properties"]["schema_version"]["const"] == ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION


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
        "partial_composite": 0.7473,
        "partial_composite_scope": "measured_headline_axes",
        "measured_headline_weight": 0.5,
        "missing_headline_weight": 0.5,
        "known_headline_contribution": 0.3737,
        "rank_scope": "partial-text-code-4axis-v1",
        "composite_static": 0.7473,
        "static_index_version": "static-suite-v1",
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
        "model": {"display_name": "Gemma", "file_sha256": "b" * 64, "quant_label": "Q4"},
        "runtime": {"name": "llama.cpp", "version": "1"},
        "suite_release_id": "suite-v1-partial-text-code-4axis-v1",
        "suite_manifest_sha256": "c" * 64,
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
        "artifact_hashes": {
            "bundle_sha256": "d" * 64,
            "projection_sha256": "e" * 64,
            "public_artifact_manifest_sha256": "f" * 64,
        },
        "origin": "project_anchor",
        "trust_label": "community_re_scored",
        "verification_level": "bundle_rescored",
        "agentic_provenance": "none",
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

    # Then: both commands succeed and write the same public results as the Python APIs.
    assert validation_code == 0
    assert rescore_code == 0
    assert json.loads(validation_out.read_text(encoding="utf-8")) == validate_submission_bundle(
        _PILOT,
        suite_dir=_SUITE_V1,
    )
    assert json.loads(projection_out.read_text(encoding="utf-8")) == rescore_bundle(
        _PILOT,
        suite_dir=_SUITE_V1,
        validated_at="2026-06-30T00:00:00Z",
    )


def test_pilot_rescore_reproduces_numbers_and_is_byte_identical() -> None:
    # Given / When: the pilot is rescored twice from item-level responses.
    first = rescore_bundle(_PILOT, suite_dir=_SUITE_V1, validated_at="2026-06-30T00:00:00Z")
    second = rescore_bundle(_PILOT, suite_dir=_SUITE_V1, validated_at="2026-06-30T00:00:00Z")

    # Then: the scorer path reproduces the published calibration numbers deterministically.
    assert first["axes"]["knowledge"]["score"] == 0.7725
    assert first["axes"]["instruction_following"]["score"] == 0.6871
    assert first["axes"]["tool_calling"]["score"] == 0.7364
    assert first["axes"]["coding"]["score"] == 0.8527
    assert first["scores"]["partial_composite"] == 0.7473
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


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
