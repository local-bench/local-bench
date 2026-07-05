from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.cli import main
from localbench.submissions.crypto import load_private_key
from localbench.suite_resolver import SuiteRef

from .fixtures import build_submission_fixtures

_RELEASE_ID = "suite-v1-text-code-agentic-5axis-v1"
_MANIFEST_SHA = "db1e6cd14f946126254cc2ada56ea1af0186303e0899f00f374d30382d96870e"


@pytest.mark.anyio
async def test_submit_run_auto_resolves_suite_from_run_record_when_suite_dir_is_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: an organic run without a release pair, a cached suite release, and stubbed site client calls.
    import localbench.submissions.submit_run as submit_mod
    import localbench.submissions.submit_run_inputs as inputs_mod

    _isolate_home(monkeypatch, tmp_path)
    fixtures = await build_submission_fixtures(tmp_path)
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    suite = run["manifest"]["suite"]
    suite.pop("suite_release_id", None)
    suite.pop("suite_manifest_sha256", None)
    fixtures.run_path.write_text(json.dumps(run), encoding="utf-8")
    (fixtures.suite_dir / "suite_release_manifest.json").write_text(
        json.dumps({"suite_release_id": _RELEASE_ID, "suite_manifest_sha256": _MANIFEST_SHA}),
        encoding="utf-8",
    )
    expected_public_key = load_private_key(fixtures.key_path).public_key.hex()
    uploaded_bundles: list[Path] = []
    resolved_suite_ids: list[str] = []

    def fake_resolve_suite_dir(*, suite_id: str) -> SuiteRef:
        resolved_suite_ids.append(suite_id)
        return SuiteRef(
            suite_id=suite_id,
            path=fixtures.suite_dir,
            suite_hash="fixture-suite-hash",
            source="cache",
            version="fixture-suite-v1",
            license_manifest={},
        )

    def fake_ticket(request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        assert request.expected_suite_release_id == _RELEASE_ID
        assert request.expected_suite_manifest_sha256 == _MANIFEST_SHA
        return _envelope(request.raw_bundle_sha256, request.public_key or "", "sub_auto")

    def fake_upload(request: submit_mod.SubmissionUploadRequest) -> dict[str, str]:
        uploaded_bundles.append(request.bundle_path)
        uploaded = json.loads(request.bundle_path.read_text(encoding="utf-8"))
        assert uploaded["manifest"]["suite"]["suite_release_id"] == _RELEASE_ID
        assert uploaded["manifest"]["suite"]["suite_manifest_sha256"] == _MANIFEST_SHA
        assert uploaded["signature"]["public_key"] == expected_public_key
        return {"submission_id": "sub_auto", "status": "pending_verification"}

    def fake_status(request: submit_mod.SubmissionStatusRequest) -> dict[str, str]:
        assert request.ticket_id == "sub_auto"
        return {"submission_id": "sub_auto", "status": "pending_verification"}

    monkeypatch.setattr(inputs_mod, "resolve_suite_dir", fake_resolve_suite_dir, raising=False)
    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)
    monkeypatch.setattr(submit_mod, "upload_submission_bundle", fake_upload)
    monkeypatch.setattr(submit_mod, "get_submission_status", fake_status)

    # When: the user submits the run JSON without passing --suite-dir.
    code = main(
        [
            "submit",
            "run",
            "--run",
            str(fixtures.run_path),
            "--signing-key",
            str(fixtures.key_path),
        ],
    )

    # Then: the suite id in the run resolves the cached suite and the upload proceeds.
    output = capsys.readouterr().out
    assert code == 0
    assert resolved_suite_ids == ["fixture-suite-v1"]
    assert uploaded_bundles
    assert "submission sub_auto" in output


@pytest.mark.anyio
async def test_submit_run_explains_suite_remediation_when_auto_resolve_is_not_possible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: an organic run without release-pair fields or a suite id.
    _isolate_home(monkeypatch, tmp_path)
    fixtures = await build_submission_fixtures(tmp_path)
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    suite = run["manifest"]["suite"]
    suite.pop("suite_release_id", None)
    suite.pop("suite_manifest_sha256", None)
    suite.pop("suite_id", None)
    fixtures.run_path.write_text(json.dumps(run), encoding="utf-8")

    # When: dry-run submission prepares the upload without an explicit --suite-dir.
    code = main(
        [
            "submit",
            "run",
            "--run",
            str(fixtures.run_path),
            "--signing-key",
            str(fixtures.key_path),
            "--dry-run",
        ],
    )

    # Then: the typed error gives both supported remediation paths.
    output = capsys.readouterr().out
    assert code == 2
    assert "--suite-dir" in output
    assert "localbench fetch-suite --site https://local-bench.ai --accept-suite-terms" in output
    assert "Traceback" not in output


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def _envelope(bundle_sha: str, public_key: str, ticket_id: str) -> dict[str, object]:
    return {
        "accepted_suite_terms": True,
        "allowed_schema": "localbench.result_bundle.v1",
        "bundle_sha256": bundle_sha,
        "expected_suite_manifest_sha256": _MANIFEST_SHA,
        "expected_suite_release_id": _RELEASE_ID,
        "expiry": "2026-07-04T01:00:00Z",
        "max_upload_bytes": 67_108_864,
        "one_use": True,
        "origin": "community",
        "schema_version": "localbench.submission_envelope.v2",
        "submitter_id": "public_key:" + public_key,
        "ticket_id": ticket_id,
    }
