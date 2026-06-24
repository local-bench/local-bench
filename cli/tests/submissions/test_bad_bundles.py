from __future__ import annotations

from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.validate import SubmissionValidationError
from localbench.submissions.verify import verify_bundle_offline

from .fixtures import (
    FIXTURE_NAMES,
    build_submission_fixtures,
    mutate_zip_json,
    write_jsonl_bundle,
    write_oversized_manifest_bundle,
    write_path_traversal_bundle,
)


def test_adversarial_fixture_catalog_lists_required_names() -> None:
    # Given / When / Then: M1's named fixture set is present.
    assert FIXTURE_NAMES == {
        "valid",
        "tampered_aggregate",
        "tampered_item_correct",
        "tampered_output",
        "bad_signature",
        "wrong_scorecard",
        "wrong_suite_hash",
        "duplicate_item",
        "missing_item",
        "unknown_item",
        "path_traversal",
        "oversized_manifest",
    }


@pytest.mark.anyio
async def test_bad_signature_rejects_for_signature_reason(tmp_path: Path) -> None:
    # Given: a signed bundle with a mutated manifest payload.
    fixtures, valid = await _valid_bundle(tmp_path)
    bad = mutate_zip_json(
        valid,
        tmp_path / "bad-signature.lbsub.zip",
        "manifest.json",
        lambda manifest: {**manifest, "payload": {**manifest["payload"], "run_nonce": "wrong"}},
        refresh_payload_sha=True,
    )

    # When / Then: verification fails closed on the signature.
    with pytest.raises(SubmissionValidationError, match="signature"):
        verify_bundle_offline(bad, suite_dir=fixtures.suite_dir)


@pytest.mark.anyio
async def test_wrong_scorecard_rejects(tmp_path: Path) -> None:
    # Given: a bundle signed under a stale scorecard id.
    fixtures, valid = await _valid_bundle(tmp_path)
    bad = mutate_zip_json(
        valid,
        tmp_path / "wrong-scorecard.lbsub.zip",
        "manifest.json",
        lambda manifest: {
            **manifest,
            "payload": {
                **manifest["payload"],
                "scorecard": {**manifest["payload"]["scorecard"], "id": "wrong"},
            },
        },
        refresh_payload_sha=True,
        signing_key_path=fixtures.key_path,
    )

    # When / Then: verification rejects scorecard drift.
    with pytest.raises(SubmissionValidationError, match="scorecard"):
        verify_bundle_offline(bad, suite_dir=fixtures.suite_dir)


@pytest.mark.anyio
async def test_wrong_suite_hash_rejects(tmp_path: Path) -> None:
    # Given: a bundle signed under the wrong suite hash.
    fixtures, valid = await _valid_bundle(tmp_path)
    bad = mutate_zip_json(
        valid,
        tmp_path / "wrong-suite-hash.lbsub.zip",
        "manifest.json",
        lambda manifest: {
            **manifest,
            "payload": {
                **manifest["payload"],
                "suite": {**manifest["payload"]["suite"], "hash": "0" * 64},
            },
        },
        refresh_payload_sha=True,
        signing_key_path=fixtures.key_path,
    )

    # When / Then: verification rejects suite drift.
    with pytest.raises(SubmissionValidationError, match="suite hash"):
        verify_bundle_offline(bad, suite_dir=fixtures.suite_dir)


@pytest.mark.anyio
async def test_duplicate_missing_and_unknown_items_reject(tmp_path: Path) -> None:
    # Given: valid bundle bytes and three item-set adversaries.
    fixtures, valid = await _valid_bundle(tmp_path)
    cases = {
        "duplicate": write_jsonl_bundle(
            valid,
            tmp_path / "duplicate.lbsub.zip",
            lambda rows: [rows[0], rows[0]],
            signing_key_path=fixtures.key_path,
        ),
        "missing": write_jsonl_bundle(
            valid,
            tmp_path / "missing.lbsub.zip",
            lambda rows: [],
            signing_key_path=fixtures.key_path,
        ),
        "unknown": write_jsonl_bundle(
            valid,
            tmp_path / "unknown.lbsub.zip",
            lambda rows: [{**rows[0], "item_id": "unknown-item"}],
            signing_key_path=fixtures.key_path,
        ),
    }

    # When / Then: each item-set violation fails for its intended reason.
    for reason, bundle in cases.items():
        with pytest.raises(SubmissionValidationError, match=reason):
            verify_bundle_offline(bundle, suite_dir=fixtures.suite_dir)


@pytest.mark.anyio
async def test_file_hash_mismatch_rejects(tmp_path: Path) -> None:
    # Given: a bundle whose items file no longer matches manifest file hashes.
    fixtures, valid = await _valid_bundle(tmp_path)
    bad = write_jsonl_bundle(
        valid,
        tmp_path / "file-hash-mismatch.lbsub.zip",
        lambda rows: [{**rows[0], "response": {**rows[0]["response"], "finish_reason": "length"}}],
    )

    # When / Then: verification rejects the modified file before scoring.
    with pytest.raises(SubmissionValidationError, match="file hash"):
        verify_bundle_offline(bad, suite_dir=fixtures.suite_dir)


def test_path_traversal_and_oversized_manifest_reject(tmp_path: Path) -> None:
    # Given: two malformed archives.
    traversal = write_path_traversal_bundle(tmp_path / "path-traversal.lbsub.zip")
    oversized = write_oversized_manifest_bundle(tmp_path / "oversized-manifest.lbsub.zip")

    # When / Then: archive validation rejects both before parsing payloads.
    with pytest.raises(SubmissionValidationError, match="unsafe archive path"):
        verify_bundle_offline(traversal, suite_dir=tmp_path)
    with pytest.raises(SubmissionValidationError, match="manifest too large"):
        verify_bundle_offline(oversized, suite_dir=tmp_path)


async def _valid_bundle(tmp_path: Path):
    fixtures = await build_submission_fixtures(tmp_path)
    valid = tmp_path / "valid.lbsub.zip"
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=valid,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )
    return fixtures, valid
