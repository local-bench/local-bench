from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle

from .fixtures import build_submission_fixtures


@pytest.mark.anyio
async def test_pack_is_deterministic_when_clock_nonce_and_key_are_fixed(tmp_path: Path) -> None:
    # Given: a fixed run, suite, signing key, clock, and nonce.
    fixtures = await build_submission_fixtures(tmp_path)
    first = tmp_path / "first.lbsub.zip"
    second = tmp_path / "second.lbsub.zip"

    # When: packing the same run twice.
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=first,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=second,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # Then: bundle bytes and manifest payload hash are stable.
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first, "r") as archive:
        assert archive.namelist() == ["manifest.json", "items.jsonl", "run.original.json"]
        manifest = json.loads(archive.read("manifest.json"))
    payload = json.dumps(manifest["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert manifest["payload_sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.anyio
async def test_pack_records_manifest_counts_and_file_hashes(tmp_path: Path) -> None:
    # Given: a fixed run over one public suite item.
    fixtures = await build_submission_fixtures(tmp_path)
    out = tmp_path / "valid.lbsub.zip"

    # When: packing the run.
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

    # Then: the manifest signs the files that carry authoritative transcript data.
    with zipfile.ZipFile(out, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        files = {entry["path"]: entry for entry in manifest["payload"]["files"]}
    assert manifest["payload"]["counts"]["items_total"] == 1
    assert set(files) == {"items.jsonl", "run.original.json"}
    assert files["items.jsonl"]["sha256"] == hashlib.sha256(
        zipfile.ZipFile(out, "r").read("items.jsonl"),
    ).hexdigest()
