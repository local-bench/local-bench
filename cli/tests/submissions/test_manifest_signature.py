from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.crypto import verify_manifest_signature

from .fixtures import build_submission_fixtures, mutate_zip_json


@pytest.mark.anyio
async def test_manifest_signature_verifies_for_valid_payload(tmp_path: Path) -> None:
    # Given: a valid packed submission.
    fixtures = await build_submission_fixtures(tmp_path)
    out = tmp_path / "valid.lbsub.zip"
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=out,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # When: verifying the signature block against the manifest payload.
    with zipfile.ZipFile(out, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))

    # Then: the signature is valid.
    assert verify_manifest_signature(manifest) is True


@pytest.mark.anyio
async def test_manifest_signature_fails_after_one_payload_byte_mutation(tmp_path: Path) -> None:
    # Given: a valid packed submission.
    fixtures = await build_submission_fixtures(tmp_path)
    out = tmp_path / "valid.lbsub.zip"
    tampered = tmp_path / "bad-signature.lbsub.zip"
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=out,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # When: mutating one signed payload field without resigning.
    mutate_zip_json(
        out,
        tampered,
        "manifest.json",
        lambda manifest: {
            **manifest,
            "payload": {**manifest["payload"], "run_nonce": "mutated-nonce"},
        },
    )
    with zipfile.ZipFile(tampered, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))

    # Then: signature verification fails.
    assert verify_manifest_signature(manifest) is False
