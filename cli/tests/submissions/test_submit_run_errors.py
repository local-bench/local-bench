from __future__ import annotations

import json
import zipfile
from pathlib import Path

import httpx
import pytest

from localbench.cli import main
from localbench.submissions.keys import write_private_key

_RELEASE_ID = "suite-v1-text-code-agentic-5axis-v1"
_MANIFEST_SHA = "1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f"


def test_submit_run_maps_already_submitted_to_successful_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: the ticket leg reports that this exact bundle already exists.
    import localbench.submissions.submit_run as submit_mod

    bundle = _bundle(tmp_path)
    key = _key(tmp_path)

    def fake_ticket(request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        raise _http_error(409, {"code": "bundle_already_submitted", "submission_id": "sub_existing"})

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)

    # When: submit run is repeated for the same bundle.
    code = main(["submit", "run", "--bundle", str(bundle), "--signing-key", str(key)])

    # Then: it is surfaced as idempotent information, not a failure.
    output = capsys.readouterr().out
    assert code == 0
    assert (
        "this exact bundle is already submitted as sub_existing; "
        "a re-run produces a new bundle you can submit"
    ) in output


def test_submit_run_remints_once_after_ticket_expired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: upload sees one expired ticket and succeeds after automatic ticket rotation.
    import localbench.submissions.submit_run as submit_mod

    bundle = _bundle(tmp_path)
    key = _key(tmp_path)
    ticket_ids: list[str] = []

    def fake_ticket(request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        ticket_id = f"ticket_{len(ticket_ids) + 1}"
        ticket_ids.append(ticket_id)
        return _envelope(request.raw_bundle_sha256, request.public_key or "", ticket_id)

    def fake_upload(request: submit_mod.SubmissionUploadRequest) -> dict[str, str]:
        if request.envelope["ticket_id"] == "ticket_1":
            raise _http_error(410, {"code": "ticket_expired"})
        return {"submission_id": "ticket_2", "status": "pending_verification"}

    def fake_status(request: submit_mod.SubmissionStatusRequest) -> dict[str, str]:
        return {"submission_id": request.ticket_id, "status": "pending_verification"}

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)
    monkeypatch.setattr(submit_mod, "upload_submission_bundle", fake_upload)
    monkeypatch.setattr(submit_mod, "get_submission_status", fake_status)

    # When: submit run uploads the bundle.
    code = main(["submit", "run", "--bundle", str(bundle), "--signing-key", str(key)])

    # Then: the command re-mints exactly once and completes.
    output = capsys.readouterr().out
    assert code == 0
    assert ticket_ids == ["ticket_1", "ticket_2"]
    assert "submission ticket_2" in output


@pytest.mark.parametrize(
    ("payload", "expected", "exit_code"),
    [
        ({"code": "rate_limited", "retry_after_seconds": 17}, "rate_limited retry_after_seconds=17", 3),
        ({"code": "pop_stale"}, "check your system clock (server allows ±10 minutes)", 2),
    ],
)
def test_submit_run_maps_ticket_errors_to_human_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    payload: dict[str, object],
    expected: str,
    exit_code: int,
) -> None:
    # Given: the ticket leg returns an expected typed error.
    import localbench.submissions.submit_run as submit_mod

    bundle = _bundle(tmp_path)
    key = _key(tmp_path)

    def fake_ticket(request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        status = 429 if payload["code"] == "rate_limited" else 400
        raise _http_error(status, payload)

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)

    # When: submit run requests a ticket.
    code = main(["submit", "run", "--bundle", str(bundle), "--signing-key", str(key)])

    # Then: the exact remediation line is printed and the exit code matches the contract.
    output = capsys.readouterr().out
    assert code == exit_code
    assert expected in output
    assert "Traceback" not in output


def test_submit_run_surfaces_unmapped_server_error_code_and_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: the ticket leg returns an unrecognized typed backend error.
    import localbench.submissions.submit_run as submit_mod

    bundle = _bundle(tmp_path)
    key = _key(tmp_path)

    def fake_ticket(request: submit_mod.SubmissionTicketRequest) -> dict[str, object]:
        raise _http_error(
            400,
            {
                "code": "unknown_suite_release",
                "error": "suite release pair is not registered",
            },
        )

    monkeypatch.setattr(submit_mod, "request_submission_ticket", fake_ticket)

    # When: submit run requests a ticket.
    code = main(["submit", "run", "--bundle", str(bundle), "--signing-key", str(key)])

    # Then: both the machine code and server message reach the user.
    output = capsys.readouterr().out
    assert code == 2
    assert "ticket failed: unknown_suite_release: suite release pair is not registered" in output
    assert "Traceback" not in output


def test_submit_run_rejects_zip_archives_with_remediation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a prepacked .lbsub.zip archive (the offline verification format).
    path = tmp_path / "bundle.lbsub.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", "{}")
    key = _key(tmp_path)

    # When: submit run is pointed at the archive.
    code = main(["submit", "run", "--bundle", str(path), "--signing-key", str(key), "--dry-run"])

    # Then: it fails closed with the server-format remediation, before any network call.
    output = capsys.readouterr().out
    assert code == 2
    assert "the submission server accepts the publishable run JSON" in output
    assert "Traceback" not in output


def _bundle(tmp_path: Path) -> Path:
    path = tmp_path / "bundle-run.json"
    run = {
        "manifest": {
            "suite": {
                "suite_release_id": _RELEASE_ID,
                "suite_manifest_sha256": _MANIFEST_SHA,
            },
            "model_claim": {"display_name": "fixture-model"},
        },
        "signature": {"algorithm": "Ed25519", "public_key": "ab" * 32, "signature": "cd" * 64},
    }
    path.write_text(json.dumps(run), encoding="utf-8")
    return path


def _key(tmp_path: Path) -> Path:
    path = tmp_path / "submitter.pem"
    write_private_key(path, seed=bytes(range(32)))
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
        "upload_capability": "upload_" + ("1" * 32),
    }


def _http_error(status_code: int, payload: dict[str, object]) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://local-bench.ai/api/submissions/tickets")
    response = httpx.Response(status_code, json=payload, request=request)
    return httpx.HTTPStatusError("site error", request=request, response=response)
