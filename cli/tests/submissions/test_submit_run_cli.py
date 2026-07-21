from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from localbench.cli import main
from localbench.one_shot.submission import OneShotSubmitContext, maybe_submit
from localbench.one_shot.types import (
    FULL_EXEC_SUITE_IDENTITY,
    OneShotArtifact,
    ResolvedOneShotModel,
)
from localbench.submissions.crypto import load_private_key

from .fixtures import build_submission_fixtures

_RELEASE_ID = "suite-v1-text-code-agentic-5axis-v1"
_MANIFEST_SHA = "1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f"


@pytest.mark.anyio
async def test_submit_run_packs_tickets_uploads_and_prints_publish_summary(
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
        assert request.accepted_result_projection is not None
        assert request.accepted_result_projection["origin"] == "community"
        assert request.accepted_result_projection["trust_label"] == "community_self_submitted"
        assert request.accepted_result_projection["lineage"] == {
            "base_model": ["Qwen/Qwen3.6-27B"],
        }
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
            "--base-model",
            "Qwen/Qwen3.6-27B",
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
    assert "Published immediately; subject to post-hoc moderation." in output
    config = json.loads((tmp_path / "home" / ".localbench" / "submit.json").read_text(encoding="utf-8"))
    assert config == {"display_name": "Alice", "site": "https://local-bench.ai"}


@pytest.mark.anyio
async def test_one_shot_submit_builds_community_projection_from_ticket_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a completed one-shot run and a server ticket assigning community origin.
    import localbench.submissions.submit_run as submit_mod

    _isolate_home(monkeypatch, tmp_path)
    fixtures = await build_submission_fixtures(tmp_path)
    run_path = tmp_path / "localbench-run.json"
    shutil.copyfile(fixtures.run_path, run_path)
    _mark_site_release(run_path)

    def fake_ticket(request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        return _envelope(request.raw_bundle_sha256, request.public_key or "", "sub_one_shot")

    def fake_upload(request: submit_mod.SubmissionUploadRequest) -> dict[str, str]:
        assert request.accepted_result_projection is not None
        assert request.accepted_result_projection["origin"] == "community"
        assert request.accepted_result_projection["trust_label"] == "community_self_submitted"
        return {"submission_id": "sub_one_shot", "status": "published"}

    def fake_status(request: submit_mod.SubmissionStatusRequest) -> dict[str, str]:
        return {"submission_id": request.ticket_id, "status": "published"}

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)
    monkeypatch.setattr(submit_mod, "upload_submission_bundle", fake_upload)
    monkeypatch.setattr(submit_mod, "get_submission_status", fake_status)

    # When: the one-shot submission adapter drives the shared submit path.
    code = maybe_submit(
        OneShotSubmitContext(
            args=argparse.Namespace(
                site="https://local-bench.ai",
                suite_dir=fixtures.suite_dir,
                signing_key=fixtures.key_path,
                display_name=None,
                bypass_token=None,
                bypass_token_file=None,
            ),
            run_root=tmp_path,
            submit_choice=True,
            resolved=ResolvedOneShotModel(
                requested="fixture-model",
                model_id="fixture-model",
                display_name="Fixture Model",
                family=None,
                source_kind="catalog",
                catalog_model_id="fixture-model",
                tokenizer_repo=None,
                tokenizer_revision=None,
                artifact=OneShotArtifact(
                    repo_id="owner/fixture",
                    filename="fixture.gguf",
                    revision="a" * 40,
                    quant_label="Q4_K_M",
                    sha256="b" * 64,
                    size_bytes=1,
                    vram_required_gb_8k=None,
                    vram_required_gb_32k=None,
                ),
                local_only=False,
                publishable=True,
                blocking_reasons=(),
            ),
            submitter=None,
            input_fn=lambda: "",
            record={"headline_complete": True},
            suite_identity=FULL_EXEC_SUITE_IDENTITY,
        ),
    )

    # Then: one-shot uses the ticket's authoritative community origin.
    assert code == 0


@pytest.mark.anyio
async def test_submit_upload_builds_projection_with_the_shared_real_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a real publishable result bundle, suite, and ticket envelope.
    import localbench.cli as cli_mod

    fixtures = await build_submission_fixtures(tmp_path)
    _mark_site_release(fixtures.run_path)
    record = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    record["manifest"]["runtime"] = {"name": "test-runtime", "version": "1", "backend": "test"}
    fixtures.run_path.write_text(json.dumps(record), encoding="utf-8")
    bundle_sha = hashlib.sha256(fixtures.run_path.read_bytes()).hexdigest()
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(
        json.dumps(_envelope(bundle_sha, "ab" * 32, "sub_upload")),
        encoding="utf-8",
    )

    def fake_upload(request: cli_mod.SubmissionUploadRequest) -> dict[str, str]:
        projection = request.accepted_result_projection
        assert projection is not None
        assert projection["origin"] == "community"
        assert projection["trust_label"] == "community_self_submitted"
        assert projection["runtime"] == {"name": "test-runtime", "version": "1", "backend": "test"}
        return {"submission_id": "sub_upload", "status": "published"}

    monkeypatch.setattr(cli_mod, "upload_submission_bundle", fake_upload)

    # When: the advertised low-level upload command is invoked.
    code = main(
        [
            "submit",
            "upload",
            "--site",
            "https://local-bench.ai",
            "--ticket",
            str(ticket_path),
            "--bundle",
            str(fixtures.run_path),
            "--suite-dir",
            str(fixtures.suite_dir),
        ],
    )

    # Then: completion receives the same client-reported projection as submit run.
    assert code == 0


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


def test_submit_run_rejects_invalid_base_model_repo_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a finished bundle and a base-model value outside the repository-id contract.
    _isolate_home(monkeypatch, tmp_path)
    bundle = _write_prepacked_bundle(tmp_path / "bundle-run.json")

    # When: submit run parses the invalid declaration.
    with pytest.raises(SystemExit) as exit_info:
        main([
            "submit",
            "run",
            "--bundle",
            str(bundle),
            "--base-model",
            "not-a-repo-id",
            "--dry-run",
        ])

    # Then: argparse rejects the value before submission preparation.
    assert exit_info.value.code == 2
    assert "Hugging Face repo id" in capsys.readouterr().err


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


def test_submit_run_rejects_incomplete_bundle_before_ticket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import localbench.submissions.submit_run as submit_mod

    _isolate_home(monkeypatch, tmp_path)
    bundle = _write_prepacked_bundle(tmp_path / "partial-run.json")
    record = json.loads(bundle.read_text(encoding="utf-8"))
    record["benches"].pop("appworld_c")
    bundle.write_text(json.dumps(record), encoding="utf-8")
    ticket_requested = False

    def fake_ticket(_request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        nonlocal ticket_requested
        ticket_requested = True
        return {}

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)

    code = main(["submit", "run", "--bundle", str(bundle)])

    assert code == 2
    assert ticket_requested is False
    assert "incomplete_run" in capsys.readouterr().out


def test_submit_run_incomplete_error_prints_coding_verifier_remediation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a prepacked bundle whose agentic bench is missing (headline-incomplete),
    # driven through the same path as the rejection test above.
    import localbench.submissions.submit_run as submit_mod

    _isolate_home(monkeypatch, tmp_path)
    bundle = _write_prepacked_bundle(tmp_path / "partial-run.json")
    record = json.loads(bundle.read_text(encoding="utf-8"))
    record["benches"].pop("appworld_c")
    bundle.write_text(json.dumps(record), encoding="utf-8")

    def fail_ticket(_request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        raise AssertionError("ticket request should not be sent")

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fail_ticket)

    # When: submit refuses the incomplete bundle.
    code = main(["submit", "run", "--bundle", str(bundle)])

    # Then: the error carries an invocation-derived verifier remediation command.
    output = capsys.readouterr().out
    assert code == 2
    assert "incomplete_run" in output
    assert "verify     localbench code --pending-run" in output
    assert str(bundle) in output
    assert "--allow-untrusted-code" in output

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
    _mark_complete(run)
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
    _mark_complete(run)
    path.write_text(json.dumps(run), encoding="utf-8")
    return path


def _mark_complete(run: dict[str, object]) -> None:
    run["benches"] = {
        bench: {"n": 1, "raw_accuracy": 1.0, "chance_corrected": 1.0}
        for bench in (
            "mmlu_pro",
            "ifbench",
            "tc_json_v1",
            "bigcodebench_hard",
            "olymmath_hard",
            "amo",
            "appworld_c",
        )
    }
    run["axis_status"] = {
        "schema_version": "localbench.axis-status.v1",
        "axes": {
            axis: {"axis": axis, "status": "measured", "reason": "ok"}
            for axis in (
                "knowledge",
                "instruction_following",
                "math",
                "agentic",
                "tool_calling",
                "coding",
            )
        },
    }
    run["headline_complete"] = True
    run.setdefault("scores", {})
    run.setdefault("items", [])


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
        "upload_capability": "upload_" + ("1" * 32),
    }
