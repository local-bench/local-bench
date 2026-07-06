from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from localbench.cli import main
from localbench.submissions.crypto import load_private_key

from .fixtures import build_submission_fixtures

_RELEASE_ID = "suite-v1-text-code-agentic-5axis-v1"
_MANIFEST_SHA = "1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f"


@pytest.mark.anyio
async def test_submit_run_packs_tickets_uploads_and_prints_review_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a finished run, a signing key, isolated submit config, and stubbed site client calls.
    import localbench.submissions.submit_run as submit_mod

    _isolate_home(monkeypatch, tmp_path)
    fixtures = await build_submission_fixtures(tmp_path)
    _mark_site_release(fixtures.run_path)
    expected_public_key = load_private_key(fixtures.key_path).public_key.hex()
    captured_tickets: list[submit_mod.SubmissionTicketRequest] = []
    uploaded_bundles: list[Path] = []

    def fake_ticket(request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        captured_tickets.append(request)
        assert request.expected_suite_release_id == _RELEASE_ID
        assert request.expected_suite_manifest_sha256 == _MANIFEST_SHA
        assert request.submitter_display_name == "Alice"
        assert request.declared_model_slug == "fixture-model"
        assert request.pop is not None
        expected = "\n".join(
            (
                "localbench.ticket_pop.v1",
                request.raw_bundle_sha256,
                _RELEASE_ID,
                _MANIFEST_SHA,
                request.pop.timestamp,
            ),
        )
        assert request.pop.message == expected
        timestamp = datetime.strptime(request.pop.timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        assert abs((datetime.now(UTC) - timestamp).total_seconds()) < 60
        return _envelope(request.raw_bundle_sha256, request.public_key or "", "sub_123")

    def fake_upload(request: submit_mod.SubmissionUploadRequest) -> dict[str, str]:
        uploaded_bundles.append(request.bundle_path)
        assert request.envelope["ticket_id"] == "sub_123"
        assert request.bundle_path.exists()
        uploaded = json.loads(request.bundle_path.read_text(encoding="utf-8"))
        assert uploaded["manifest"]["suite"]["suite_release_id"] == _RELEASE_ID
        assert uploaded["manifest"]["suite"]["suite_manifest_sha256"] == _MANIFEST_SHA
        assert uploaded["signature"]["public_key"] == expected_public_key
        return {"submission_id": "sub_123", "status": "pending_verification"}

    def fake_status(request: submit_mod.SubmissionStatusRequest) -> dict[str, str]:
        assert request.ticket_id == "sub_123"
        return {"submission_id": "sub_123", "status": "pending_verification"}

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)
    monkeypatch.setattr(submit_mod, "upload_submission_bundle", fake_upload)
    monkeypatch.setattr(submit_mod, "get_submission_status", fake_status)

    # When: the one-command submit path is driven from the CLI.
    code = main(
        [
            "submit",
            "run",
            "--run",
            str(fixtures.run_path),
            "--suite-dir",
            str(fixtures.suite_dir),
            "--signing-key",
            str(fixtures.key_path),
            "--display-name",
            "Alice",
        ],
    )

    # Then: the bundle-derived ticket request, upload, status check, output, and config are correct.
    output = capsys.readouterr().out
    assert code == 0
    assert captured_tickets[0].credentials.site == "https://local-bench.ai"
    assert uploaded_bundles
    assert "submission sub_123" in output
    assert "status_url https://local-bench.ai/submission?id=sub_123" in output
    assert "status     pending_verification" in output
    assert "community submissions are labeled self-reported on the agentic axis" in output
    assert "the maintainer reviews every submission before anything publishes." in output
    config = json.loads((tmp_path / "home" / ".localbench" / "submit.json").read_text(encoding="utf-8"))
    assert config == {"display_name": "Alice", "site": "https://local-bench.ai"}


def test_submit_run_default_key_autogen_reuses_key_and_explicit_missing_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a prepacked bundle and an isolated home without a submitter key.
    _isolate_home(monkeypatch, tmp_path)
    bundle = _write_prepacked_bundle(tmp_path / "bundle-run.json")
    default_key = tmp_path / "home" / ".localbench" / "submitter_ed25519.pem"

    # When: dry-run submit uses the default key twice.
    first = main(["submit", "run", "--bundle", str(bundle), "--dry-run"])
    first_output = capsys.readouterr().out
    public_key = load_private_key(default_key).public_key.hex()
    second = main(["submit", "run", "--bundle", str(bundle), "--dry-run"])
    second_output = capsys.readouterr().out
    missing = main(
        [
            "submit",
            "run",
            "--bundle",
            str(bundle),
            "--signing-key",
            str(tmp_path / "missing.pem"),
            "--dry-run",
        ],
    )
    missing_output = capsys.readouterr().out

    # Then: the default key is created once, reused, and explicit missing keys fail cleanly.
    assert first == 0
    assert second == 0
    assert missing == 2
    assert default_key.exists()
    assert f"public_key {public_key}" in first_output
    assert "this key is your leaderboard identity — back it up." in first_output
    assert "this key is your leaderboard identity" not in second_output
    assert "signing key does not exist" in missing_output


def test_submit_run_rejects_unregistered_suite_pair_before_ticket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a signed bundle that declares a synthesized custom suite release pair.
    import localbench.submissions.submit_run as submit_mod

    _isolate_home(monkeypatch, tmp_path)
    bundle = _write_prepacked_bundle(
        tmp_path / "bundle-run.json",
        release_id="suite-custom-local-v0",
        manifest_sha="b" * 64,
    )

    def fail_ticket(_request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        raise AssertionError("ticket request should not be sent")

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fail_ticket)

    # When: the user submits without dry-run.
    code = main(["submit", "run", "--bundle", str(bundle)])

    # Then: the CLI fails locally with the current registered releases before any ticket request.
    output = capsys.readouterr().out
    assert code == 2
    assert "suite release pair is not registered for submission" in output
    assert "suite-custom-local-v0" in output
    assert "suite-v1-full-exec-6axis-v1" in output
    assert "suite-v1-static-exec-5axis-v1" in output
    assert "suite-v1-static-core-diag-v1" in output
    assert "Traceback" not in output


def test_submit_run_reads_config_and_rejects_malformed_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a malformed submit config.
    _isolate_home(monkeypatch, tmp_path)
    bundle = _write_prepacked_bundle(tmp_path / "bundle-run.json")
    config_path = tmp_path / "home" / ".localbench" / "submit.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{not json", encoding="utf-8")

    # When: submit run tries to load it.
    code = main(["submit", "run", "--bundle", str(bundle), "--dry-run"])

    # Then: the user sees a typed config error naming the file.
    output = capsys.readouterr().out
    assert code == 2
    assert "malformed submit config" in output
    assert str(config_path) in output
    assert "Traceback" not in output


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def _mark_site_release(run_path: Path) -> None:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    suite = run["manifest"]["suite"]
    suite["suite_release_id"] = _RELEASE_ID
    suite["suite_manifest_sha256"] = _MANIFEST_SHA
    run_path.write_text(json.dumps(run, indent=2), encoding="utf-8")


def _write_prepacked_bundle(path: Path, *, release_id: str = _RELEASE_ID, manifest_sha: str = _MANIFEST_SHA) -> Path:
    run = {
        "manifest": {
            "suite": {
                "suite_release_id": release_id,
                "suite_manifest_sha256": manifest_sha,
            },
            "model_claim": {"display_name": "fixture-model"},
        },
        "signature": {"algorithm": "Ed25519", "public_key": "ab" * 32, "signature": "cd" * 64},
    }
    path.write_text(json.dumps(run), encoding="utf-8")
    return path


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
