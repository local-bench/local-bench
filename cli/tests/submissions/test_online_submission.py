from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from localbench.submissions.client import (
    AdminBundleDownloadRequest,
    AdminSubmissionListRequest,
    AdminVerificationResultRequest,
    SubmissionStatusRequest,
    SubmissionTicketRequest,
    SubmissionUploadRequest,
    complete_uploaded_bundle,
    download_admin_bundle,
    list_admin_submissions,
    mark_admin_verification_result,
    request_submission_ticket,
    upload_submission_bundle,
)
from localbench.submissions.crypto import load_private_key
from localbench.submissions.keys import write_private_key
from localbench.submissions.bundle import pack_submission_bundle

from .fixtures import build_submission_fixtures


def test_keygen_writes_ed25519_key_that_pack_can_sign(tmp_path: Path) -> None:
    # Given: a fresh output path for a CLI signing key.
    key_path = tmp_path / "localbench-ed25519.pem"

    # When: key generation writes a private key.
    public_key = write_private_key(key_path, seed=bytes(range(32)))

    # Then: the key can be loaded by the existing manifest signer.
    loaded = load_private_key(key_path)
    assert loaded.public_key.hex() == public_key
    assert key_path.read_text(encoding="utf-8").startswith("-----BEGIN PRIVATE KEY-----")


@pytest.mark.anyio
async def test_online_pack_records_server_ticket(tmp_path: Path) -> None:
    # Given: a server-issued online submission ticket.
    fixtures = await build_submission_fixtures(tmp_path)
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(
        json.dumps(
            {
                "account_id": None,
                "server_nonce": "server-nonce",
                "site": "https://local-bench.ai",
                "submission_id": "sub_fixture",
                "suite_hash": "not-authoritative-for-pack",
                "upload_url": "https://example.invalid/upload",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "online.lbsub.zip"

    # When: packing with the ticket.
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=out,
        offline=False,
        ticket_path=ticket_path,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )

    # Then: the signed manifest binds the bundle to the server-issued ticket.
    with zipfile.ZipFile(out, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["payload"]["ticket"] == {
        "account_id": None,
        "mode": "online",
        "server_nonce": "server-nonce",
        "submission_id": "sub_fixture",
    }


def test_submission_client_requests_ticket_uploads_bundle_and_polls_status(tmp_path: Path) -> None:
    # Given: a mocked local-bench API and R2 presigned upload URL.
    bundle = tmp_path / "bundle.lbsub.zip"
    payload_sha = "aa" * 32
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"payload_sha256": payload_sha}))
        archive.writestr("items.jsonl", "{}\n")
    bundle_bytes = bundle.read_bytes()
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
    seen_upload = b""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_upload
        match (request.method, str(request.url)):
            case ("POST", "https://local-bench.ai/api/submissions/tickets"):
                return httpx.Response(
                    201,
                    json={
                        "max_bytes": 104_857_600,
                        "server_nonce": "nonce",
                        "site": "https://local-bench.ai",
                        "status": "issued",
                        "submission_id": "sub_fixture",
                        "suite_hash": "suite-hash",
                        "upload_url": "https://upload.local/sub_fixture",
                    },
                )
            case ("PUT", "https://upload.local/sub_fixture"):
                seen_upload = request.content
                return httpx.Response(200)
            case ("POST", "https://local-bench.ai/api/submissions/sub_fixture/complete"):
                body = json.loads(request.content)
                assert body["bundle_sha256"] == bundle_sha
                assert body["manifest_payload_sha256"] == payload_sha
                assert body["size"] == len(bundle_bytes)
                return httpx.Response(200, json={"status": "uploaded", "submission_id": "sub_fixture"})
            case ("GET", "https://local-bench.ai/api/submissions/sub_fixture"):
                return httpx.Response(200, json={"status": "uploaded", "submission_id": "sub_fixture"})
            case unreachable:
                raise AssertionError(f"unexpected request: {unreachable}")

    transport = httpx.MockTransport(handler)

    # When: the CLI ticket/upload/status helpers run through their public HTTP surfaces.
    ticket = request_submission_ticket(
        SubmissionTicketRequest(
            public_key="ab" * 32,
            site="https://local-bench.ai",
            suite_id="core-text-v1",
        ),
        transport,
    )
    upload_submission_bundle(SubmissionUploadRequest(bundle_path=bundle, ticket=ticket), transport)
    status = complete_uploaded_bundle(
        SubmissionStatusRequest(site="https://local-bench.ai", submission_id="sub_fixture"),
        transport,
    )

    # Then: upload goes directly to R2, while the app API receives metadata only.
    assert ticket["submission_id"] == "sub_fixture"
    assert seen_upload == bundle_bytes
    assert status["status"] == "uploaded"


def test_admin_client_lists_downloads_and_marks_verification(tmp_path: Path) -> None:
    # Given: mocked admin API and signed R2 download surfaces.
    bundle_bytes = b"bundle-bytes"
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
    downloaded = tmp_path / "downloaded.lbsub.zip"

    def handler(request: httpx.Request) -> httpx.Response:
        match (request.method, request.url.path):
            case ("GET", "/api/admin/submissions"):
                assert request.headers["x-localbench-admin-secret"] == "admin-secret"
                assert request.url.params["status"] == "uploaded"
                return httpx.Response(
                    200,
                    json={
                        "submissions": [
                            {
                                "bundle_sha256": bundle_sha,
                                "download_url": "https://download.local/sub_uploaded",
                                "manifest_payload_sha256": "aa" * 32,
                                "r2_key": "submissions/sub_uploaded/bundle.lbsub.zip",
                                "size": len(bundle_bytes),
                                "status": "uploaded",
                                "submission_id": "sub_uploaded",
                            },
                        ],
                    },
                )
            case ("GET", "/sub_uploaded"):
                return httpx.Response(200, content=bundle_bytes)
            case ("POST", "/api/admin/submissions/sub_uploaded/verification"):
                body = json.loads(request.content)
                assert request.headers["x-localbench-admin-secret"] == "admin-secret"
                assert body == {"status": "needs_review"}
                return httpx.Response(200, json={"status": "needs_review", "submission_id": "sub_uploaded"})
            case unreachable:
                raise AssertionError(f"unexpected request: {unreachable}")

    transport = httpx.MockTransport(handler)

    # When: the admin client lists, downloads, and records a verifier result.
    pending = list_admin_submissions(
        AdminSubmissionListRequest(admin_secret="admin-secret", site="https://local-bench.ai"),
        transport,
    )
    download_admin_bundle(
        AdminBundleDownloadRequest(
            download_url=pending[0]["download_url"],
            expected_sha256=pending[0]["bundle_sha256"],
            out_path=downloaded,
        ),
        transport,
    )
    result = mark_admin_verification_result(
        AdminVerificationResultRequest(
            admin_secret="admin-secret",
            site="https://local-bench.ai",
            status="needs_review",
            submission_id="sub_uploaded",
        ),
        transport,
    )

    # Then: the local verifier can trust the listed metadata and direct download bytes.
    assert pending[0]["submission_id"] == "sub_uploaded"
    assert downloaded.read_bytes() == bundle_bytes
    assert result["status"] == "needs_review"


def test_cli_submit_online_keygen_ticket_upload_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    # Given: CLI network helpers patched to behave like the online submission API.
    from localbench.cli import main
    import localbench.cli as cli_mod

    key_path = tmp_path / "submission-key.pem"
    ticket_path = tmp_path / "ticket.json"
    bundle = tmp_path / "bundle.lbsub.zip"
    payload_sha = "bb" * 32
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"payload_sha256": payload_sha}))

    def fake_ticket(request: cli_mod.SubmissionTicketRequest) -> dict[str, object]:
        assert request.site == "https://local-bench.ai"
        assert request.suite_id == "core-text-v1"
        assert len(request.public_key) == 64
        return {
            "account_id": None,
            "max_bytes": 104_857_600,
            "server_nonce": "nonce",
            "site": "https://local-bench.ai",
            "status": "issued",
            "submission_id": "sub_fixture",
            "suite_hash": "suite-hash",
            "upload_url": "https://upload.local/sub_fixture",
        }

    def fake_upload(request: cli_mod.SubmissionUploadRequest) -> dict[str, str]:
        assert request.bundle_path == bundle
        assert request.ticket["submission_id"] == "sub_fixture"
        return {"status": "uploaded", "submission_id": "sub_fixture"}

    def fake_status(request: cli_mod.SubmissionStatusRequest) -> dict[str, str]:
        assert request.site == "https://local-bench.ai"
        assert request.submission_id == "sub_fixture"
        return {"status": "uploaded", "submission_id": "sub_fixture"}

    monkeypatch.setattr(cli_mod, "request_submission_ticket", fake_ticket)
    monkeypatch.setattr(cli_mod, "upload_submission_bundle", fake_upload)
    monkeypatch.setattr(cli_mod, "complete_uploaded_bundle", fake_status)

    # When: a user drives the online submission commands in order.
    keygen_code = main(["submit", "keygen", "--out", str(key_path)])
    ticket_code = main(
        [
            "submit",
            "ticket",
            "--site",
            "https://local-bench.ai",
            "--signing-key",
            str(key_path),
            "--out",
            str(ticket_path),
        ],
    )
    upload_code = main(["submit", "upload", "--ticket", str(ticket_path), "--bundle", str(bundle)])
    status_code = main(
        [
            "submit",
            "status",
            "sub_fixture",
            "--site",
            "https://local-bench.ai",
        ],
    )

    # Then: command output and ticket file expose the expected online state.
    output = capsys.readouterr().out
    ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
    assert keygen_code == 0
    assert ticket_code == 0
    assert upload_code == 0
    assert status_code == 0
    assert ticket["submission_id"] == "sub_fixture"
    assert "public_key " in output
    assert "ticket     " in output
    assert "status     uploaded" in output


@pytest.mark.anyio
async def test_cli_admin_verify_downloads_rescores_and_marks_needs_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    # Given: a real ticket-bound bundle and patched admin transport helpers.
    from localbench.cli import main
    import localbench.cli as cli_mod

    fixtures = await build_submission_fixtures(tmp_path)
    source_bundle = tmp_path / "source.lbsub.zip"
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(
        json.dumps(
            {
                "account_id": None,
                "server_nonce": "server-nonce",
                "site": "https://local-bench.ai",
                "submission_id": "sub_uploaded",
                "suite_hash": "suite-hash",
                "upload_url": "https://upload.local/sub_uploaded",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    pack_submission_bundle(
        run_path=fixtures.run_path,
        suite_dir=fixtures.suite_dir,
        model_name="fixture-model",
        signing_key_path=fixtures.key_path,
        out_path=source_bundle,
        offline=False,
        ticket_path=ticket_path,
        created_at="2026-06-24T00:00:00Z",
        run_nonce="fixed-nonce",
    )
    source_sha = hashlib.sha256(source_bundle.read_bytes()).hexdigest()
    marked: list[tuple[str, str | None]] = []

    def fake_list(request: cli_mod.AdminSubmissionListRequest) -> tuple[dict[str, object], ...]:
        assert request.admin_secret == "admin-secret"
        assert request.site == "https://local-bench.ai"
        return (
            {
                "bundle_sha256": source_sha,
                "download_url": "https://download.local/sub_uploaded",
                "r2_key": "submissions/sub_uploaded/bundle.lbsub.zip",
                "status": "uploaded",
                "submission_id": "sub_uploaded",
            },
        )

    def fake_download(request: cli_mod.AdminBundleDownloadRequest) -> None:
        assert request.download_url == "https://download.local/sub_uploaded"
        assert request.expected_sha256 == source_sha
        request.out_path.write_bytes(source_bundle.read_bytes())

    def fake_mark(request: cli_mod.AdminVerificationResultRequest) -> dict[str, str]:
        marked.append((request.status, request.error))
        return {"status": request.status, "submission_id": request.submission_id}

    monkeypatch.setenv("LOCALBENCH_ADMIN_SECRET", "admin-secret")
    monkeypatch.setattr(cli_mod, "list_admin_submissions", fake_list)
    monkeypatch.setattr(cli_mod, "download_admin_bundle", fake_download)
    monkeypatch.setattr(cli_mod, "mark_admin_verification_result", fake_mark)

    # When: the maintainer verifier command runs.
    code = main(
        [
            "submit",
            "admin-verify",
            "--site",
            "https://local-bench.ai",
            "--suite-dir",
            str(fixtures.suite_dir),
            "--work-dir",
            str(tmp_path / "verify-work"),
        ],
    )

    # Then: the bundle is re-scored locally and marked for human review.
    output = capsys.readouterr().out
    assert code == 0
    assert marked == [("verifying", None), ("needs_review", None)]
    assert "pending    1" in output
    assert (tmp_path / "verify-work" / "sub_uploaded.verification.json").exists()
