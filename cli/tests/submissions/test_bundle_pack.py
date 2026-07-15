from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from localbench.submissions.bundle import pack_submission_bundle
from localbench.appliance.runtime_identity import (
    agentic_runtime_identity_object,
    agentic_runtime_identity_sha256,
)
from test_appliance_runtime_identity import _components

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


@pytest.mark.anyio
async def test_pack_carries_agentic_runtime_identity_additively(tmp_path: Path) -> None:
    # Given: a run record carrying C4 identity values sourced by the shared real-artifact fixture.
    fixtures = await build_submission_fixtures(tmp_path)
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    identity = agentic_runtime_identity_object(_components())
    digest = agentic_runtime_identity_sha256(identity)
    run["agentic_run"] = {
        "agentic_runtime_identity": identity,
        "agentic_runtime_identity_sha256": digest,
    }
    fixtures.run_path.write_text(json.dumps(run), encoding="utf-8")
    out = tmp_path / "agentic.lbsub.zip"

    # When: the submission bundle is packed.
    manifest = pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=out,
        offline=True,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # Then: the additive bundle payload and signed run file both carry object plus digest.
    assert manifest["payload"]["agentic_runtime_identity"] == identity
    assert manifest["payload"]["agentic_runtime_identity_sha256"] == digest
    with zipfile.ZipFile(out, "r") as archive:
        carried_run = json.loads(archive.read("run.original.json"))
    assert carried_run["agentic_run"]["agentic_runtime_identity"] == identity
    assert carried_run["agentic_run"]["agentic_runtime_identity_sha256"] == digest


@pytest.mark.anyio
async def test_pack_derives_suite_release_pair_from_suite_dir(tmp_path: Path) -> None:
    # Given: an organic run record (no release pair) over a site-released suite dir.
    fixtures = await build_submission_fixtures(tmp_path)
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    run["manifest"]["suite"].pop("suite_release_id", None)
    run["manifest"]["suite"].pop("suite_manifest_sha256", None)
    fixtures.run_path.write_text(json.dumps(run), encoding="utf-8")
    release = {"suite_release_id": "suite-v1-fixture-release", "suite_manifest_sha256": "a" * 64}
    (fixtures.suite_dir / "suite_release_manifest.json").write_text(json.dumps(release), encoding="utf-8")
    out = tmp_path / "released.lbsub.zip"

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

    # Then: the manifest carries the release pair read from the suite dir.
    with zipfile.ZipFile(out, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    suite = manifest["payload"]["suite"]
    assert suite["suite_release_id"] == "suite-v1-fixture-release"
    assert suite["suite_manifest_sha256"] == "a" * 64


@pytest.mark.anyio
async def test_pack_omits_release_pair_for_local_suites(tmp_path: Path) -> None:
    # Given: an organic run record over a local suite dir with no release manifest.
    fixtures = await build_submission_fixtures(tmp_path)
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    run["manifest"]["suite"].pop("suite_release_id", None)
    run["manifest"]["suite"].pop("suite_manifest_sha256", None)
    fixtures.run_path.write_text(json.dumps(run), encoding="utf-8")
    out = tmp_path / "local.lbsub.zip"

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

    # Then: the keys are absent, never null, in the signed manifest.
    with zipfile.ZipFile(out, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    suite = manifest["payload"]["suite"]
    assert "suite_release_id" not in suite
    assert "suite_manifest_sha256" not in suite
