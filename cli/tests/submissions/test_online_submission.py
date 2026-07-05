from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from localbench.submissions.client import (
    AdminDecisionRequest,
    AdminVerificationRequest,
    SiteCredentials,
    SubmissionStatusRequest,
    SubmissionTicketRequest,
    SubmissionUploadRequest,
    get_submission_status,
    post_admin_decision,
    post_admin_verification,
    read_submission_envelope,
    request_submission_ticket,
    upload_submission_bundle,
)
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.crypto import load_private_key
from localbench.submissions.keys import write_private_key
from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.validate import SubmissionValidationError, validate_suite_and_scorecard

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


def test_submission_envelope_normalizes_legacy_community_origin(tmp_path: Path) -> None:
    envelope_path = tmp_path / "ticket.json"
    envelope = {
        "accepted_suite_terms": True,
        "allowed_schema": "localbench.result_bundle.v1",
        "bundle_sha256": "a" * 64,
        "expected_suite_manifest_sha256": None,
        "expected_suite_release_id": None,
        "expiry": "2026-07-04T01:00:00Z",
        "max_upload_bytes": 104_857_600,
        "one_use": True,
        "origin": "community_submission",
        "schema_version": "localbench.submission_envelope.v1",
        "submitter_id": "submitter",
        "ticket_id": "ticket_fixture",
    }
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

    parsed = read_submission_envelope(envelope_path)

    assert parsed["origin"] == "community"


def test_submission_envelope_rejects_unknown_origin(tmp_path: Path) -> None:
    envelope_path = tmp_path / "ticket.json"
    envelope = {
        "accepted_suite_terms": True,
        "allowed_schema": "localbench.result_bundle.v1",
        "bundle_sha256": "a" * 64,
        "expected_suite_manifest_sha256": None,
        "expected_suite_release_id": None,
        "expiry": "2026-07-04T01:00:00Z",
        "max_upload_bytes": 104_857_600,
        "one_use": True,
        "origin": "untrusted",
        "schema_version": "localbench.submission_envelope.v1",
        "submitter_id": "submitter",
        "ticket_id": "ticket_fixture",
    }
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(SubmissionValidationError, match="origin"):
        read_submission_envelope(envelope_path)


@pytest.mark.anyio
async def test_pack_submission_bundle_preserves_bounded_final_scorecard_lane(
    tmp_path: Path,
) -> None:
    from localbench.scoring.scorecard import scorecard_identity

    fixtures = await build_submission_fixtures(tmp_path)
    run = json.loads(fixtures.run_path.read_text(encoding="utf-8"))
    run["manifest"]["suite"]["lane"] = "bounded-final-v1"
    run["manifest"]["scorecard"] = scorecard_identity(
        "answer_only_v1",
        lane_spec_id="bounded-final-v1",
    )
    fixtures.run_path.write_text(json.dumps(run), encoding="utf-8")
    out = tmp_path / "bounded-final.lbsub.zip"

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

    payload = manifest["payload"]
    assert payload["scorecard"]["lane_spec_id"] == "bounded-final-v1"
    validate_suite_and_scorecard(payload, fixtures.suite_dir)


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
    bundle = tmp_path / "localbench-run.json"
    bundle.write_bytes(canonical_json_bytes({"schema_version": "localbench.result_bundle.v1"}) + b"\n")
    bundle_bytes = bundle.read_bytes()
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
    seen_upload = b""
    site_call_headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_upload
        match (request.method, str(request.url)):
            case ("POST", "https://local-bench.ai/api/submissions/tickets"):
                site_call_headers.append(request.headers)
                body = json.loads(request.content)
                assert body == {
                    "accepted_suite_terms": True,
                    "bundle_sha256": bundle_sha,
                    "declared_model_slug": "fixture-model",
                    "public_key": "ab" * 32,
                }
                assert request.headers["x-localbench-admin-secret"] == "admin-secret"
                return httpx.Response(
                    201,
                    json={
                        "accepted_suite_terms": True,
                        "allowed_schema": "localbench.result_bundle.v1",
                        "bundle_sha256": bundle_sha,
                        "declared_model_slug": "fixture-model",
                        "expected_suite_manifest_sha256": "487f337ac436c8b3ee327394cd9efc6d0f5562cbe1966ce114ebb611f18c8a53",
                        "expected_suite_release_id": "suite-v1-partial-text-code-4axis-v1",
                        "expiry": "2026-07-01T01:00:00Z",
                        "max_upload_bytes": 104_857_600,
                        "one_use": True,
                        "origin": "project_anchor",
                        "schema_version": "localbench.submission_envelope.v1",
                        "submitter_id": "public_key:" + ("ab" * 32),
                        "ticket_id": "ticket_fixture",
                    },
                )
            case ("POST", "https://local-bench.ai/api/submissions/request-upload"):
                site_call_headers.append(request.headers)
                assert json.loads(request.content) == {
                    "raw_bundle_sha256": bundle_sha,
                    "ticket_id": "ticket_fixture",
                }
                return httpx.Response(
                    200,
                    json={
                        "bucket": "localbench-submissions",
                        "content_sha256": bundle_sha,
                        "expires_seconds": 3600,
                        "method": "PUT",
                        "r2_key": f"submissions/raw/{bundle_sha}.json",
                        "upload_url": "https://upload.local/raw",
                    },
                )
            case ("PUT", "https://upload.local/raw"):
                seen_upload = request.content
                assert request.headers["content-type"] == "application/json"
                return httpx.Response(200)
            case ("POST", "https://local-bench.ai/api/submissions/ticket_fixture/complete"):
                site_call_headers.append(request.headers)
                body = json.loads(request.content)
                assert body == {"raw_bundle_sha256": bundle_sha, "size_bytes": len(bundle_bytes)}
                return httpx.Response(
                    200,
                    json={
                        "raw_bundle_sha256": bundle_sha,
                        "raw_bundle_size_bytes": len(bundle_bytes),
                        "status": "pending_verification",
                        "submission_id": "ticket_fixture",
                    },
                )
            case ("GET", "https://local-bench.ai/api/submissions/ticket_fixture"):
                site_call_headers.append(request.headers)
                return httpx.Response(
                    200,
                    json={
                        "raw_bundle_sha256": bundle_sha,
                        "raw_bundle_size_bytes": len(bundle_bytes),
                        "status": "pending_verification",
                        "submission_id": "ticket_fixture",
                    },
                )
            case unreachable:
                raise AssertionError(f"unexpected request: {unreachable}")

    transport = httpx.MockTransport(handler)
    credentials = SiteCredentials(
        site="https://local-bench.ai",
        admin_secret="admin-secret",
        bypass_token="private-token",
    )

    # When: the CLI ticket/upload/status helpers run through their public HTTP surfaces.
    ticket = request_submission_ticket(
        SubmissionTicketRequest(
            credentials=credentials,
            declared_model_slug="fixture-model",
            public_key="ab" * 32,
            raw_bundle_sha256=bundle_sha,
        ),
        transport,
    )
    upload_submission_bundle(
        SubmissionUploadRequest(bundle_path=bundle, credentials=credentials, envelope=ticket),
        transport,
    )
    status = get_submission_status(
        SubmissionStatusRequest(credentials=credentials, ticket_id="ticket_fixture"),
        transport,
    )

    # Then: upload goes directly to R2, while the app API receives metadata only.
    assert ticket["ticket_id"] == "ticket_fixture"
    assert seen_upload == bundle_bytes
    assert status["status"] == "pending_verification"
    assert [headers["x-localbench-bypass"] for headers in site_call_headers] == ["private-token"] * 4


def test_submission_client_surfaces_disabled_unauthorized_and_private_gate_paths(tmp_path: Path) -> None:
    # Given: a mocked backend that exposes route-level failures.
    bundle = tmp_path / "localbench-run.json"
    bundle.write_text('{"schema_version":"localbench.result_bundle.v1"}\n', encoding="utf-8")
    bundle_sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    envelope = {
        "accepted_suite_terms": True,
        "allowed_schema": "localbench.result_bundle.v1",
        "bundle_sha256": bundle_sha,
        "expected_suite_manifest_sha256": None,
        "expected_suite_release_id": None,
        "expiry": "2026-07-01T01:00:00Z",
        "max_upload_bytes": 104_857_600,
        "one_use": True,
        "origin": "project_anchor",
        "schema_version": "localbench.submission_envelope.v1",
        "submitter_id": "owner",
        "ticket_id": "ticket_fixture",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        match (request.method, request.url.path):
            case ("POST", "/api/submissions/tickets") if "x-localbench-bypass" not in request.headers:
                return httpx.Response(503, text="local-bench is temporarily private.\n")
            case ("POST", "/api/submissions/request-upload"):
                return httpx.Response(503, json={"code": "r2_signing_disabled"})
            case ("POST", "/api/admin/submissions/ticket_fixture/verification"):
                return httpx.Response(401, json={"code": "unauthorized"})
            case unreachable:
                raise AssertionError(f"unexpected request: {unreachable}")

    transport = httpx.MockTransport(handler)
    public_credentials = SiteCredentials(site="https://local-bench.ai")
    bypass_credentials = SiteCredentials(site="https://local-bench.ai", bypass_token="private-token")
    admin_credentials = SiteCredentials(
        site="https://local-bench.ai",
        admin_secret="wrong-admin-secret",
        bypass_token="private-token",
    )

    # When / Then: missing bypass, disabled upload signing, and bad admin auth surface as HTTP errors.
    with pytest.raises(httpx.HTTPStatusError) as gate_error:
        request_submission_ticket(
            SubmissionTicketRequest(
                credentials=public_credentials,
                raw_bundle_sha256=bundle_sha,
                submitter_id="owner",
            ),
            transport,
        )
    with pytest.raises(httpx.HTTPStatusError) as disabled_error:
        upload_submission_bundle(
            SubmissionUploadRequest(bundle_path=bundle, credentials=bypass_credentials, envelope=envelope),
            transport,
        )
    with pytest.raises(httpx.HTTPStatusError) as unauthorized_error:
        post_admin_verification(
            AdminVerificationRequest(
                credentials=admin_credentials,
                status_update=_status_update(bundle_sha),
                submission_id="ticket_fixture",
            ),
            transport,
        )

    assert gate_error.value.response.status_code == 503
    assert disabled_error.value.response.status_code == 503
    assert unauthorized_error.value.response.status_code == 401


def test_admin_client_posts_verification_update_and_publish_decision() -> None:
    # Given: mocked admin routes for verifier status and publish-state decisions.
    bundle_sha = "a" * 64
    status_update = _status_update(bundle_sha)
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.headers["x-localbench-bypass"] == "private-token"
        assert request.headers["x-localbench-admin-secret"] == "admin-secret"
        match (request.method, request.url.path):
            case ("POST", "/api/admin/submissions/ticket_fixture/verification"):
                assert json.loads(request.content) == status_update
                return httpx.Response(200, json={"status": "accepted", "submission_id": "ticket_fixture"})
            case ("POST", "/api/admin/submissions/ticket_fixture/decision"):
                assert json.loads(request.content) == {"publish_state": "preview"}
                return httpx.Response(200, json={"publish_state": "preview", "submission_id": "ticket_fixture"})
            case unreachable:
                raise AssertionError(f"unexpected request: {unreachable}")

    transport = httpx.MockTransport(handler)
    credentials = SiteCredentials(
        site="https://local-bench.ai",
        admin_secret="admin-secret",
        bypass_token="private-token",
    )

    # When: admin helpers post the Python-authoritative verification and decision payloads.
    verification = post_admin_verification(
        AdminVerificationRequest(
            credentials=credentials,
            status_update=status_update,
            submission_id="ticket_fixture",
        ),
        transport,
    )
    decision = post_admin_decision(
        AdminDecisionRequest(
            credentials=credentials,
            publish_state="preview",
            submission_id="ticket_fixture",
        ),
        transport,
    )

    # Then: both admin routes are driven with the expected headers and bodies.
    assert seen_paths == [
        "/api/admin/submissions/ticket_fixture/verification",
        "/api/admin/submissions/ticket_fixture/decision",
    ]
    assert verification["status"] == "accepted"
    assert decision["publish_state"] == "preview"


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
        assert request.credentials.site == "https://local-bench.ai"
        assert len(request.public_key) == 64
        assert request.raw_bundle_sha256 == hashlib.sha256(bundle.read_bytes()).hexdigest()
        return {
            "accepted_suite_terms": True,
            "allowed_schema": "localbench.result_bundle.v1",
            "bundle_sha256": request.raw_bundle_sha256,
            "expected_suite_manifest_sha256": None,
            "expected_suite_release_id": None,
            "expiry": "2026-07-01T01:00:00Z",
            "max_upload_bytes": 104_857_600,
            "one_use": True,
            "origin": "project_anchor",
            "schema_version": "localbench.submission_envelope.v1",
            "submitter_id": "public_key:" + request.public_key,
            "ticket_id": "ticket_fixture",
        }

    def fake_upload(request: cli_mod.SubmissionUploadRequest) -> dict[str, str]:
        assert request.bundle_path == bundle
        assert request.envelope["ticket_id"] == "ticket_fixture"
        return {"status": "pending_verification", "submission_id": "ticket_fixture"}

    def fake_status(request: cli_mod.SubmissionStatusRequest) -> dict[str, str]:
        assert request.credentials.site == "https://local-bench.ai"
        assert request.ticket_id == "ticket_fixture"
        return {"status": "pending_verification", "submission_id": "ticket_fixture"}

    monkeypatch.setattr(cli_mod, "request_submission_ticket", fake_ticket)
    monkeypatch.setattr(cli_mod, "upload_submission_bundle", fake_upload)
    monkeypatch.setattr(cli_mod, "get_submission_status", fake_status)

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
            "--bundle",
            str(bundle),
            "--out",
            str(ticket_path),
        ],
    )
    upload_code = main(
        [
            "submit",
            "upload",
            "--site",
            "https://local-bench.ai",
            "--ticket",
            str(ticket_path),
            "--bundle",
            str(bundle),
        ],
    )
    status_code = main(
        [
            "submit",
            "status",
            "ticket_fixture",
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
    assert ticket["ticket_id"] == "ticket_fixture"
    assert "public_key " in output
    assert "ticket     " in output
    assert "status     pending_verification" in output


@pytest.mark.anyio
async def test_cli_admin_verify_downloads_rescores_and_marks_needs_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    # Given: a local result bundle and patched admin verification transport helper.
    from localbench.cli import main
    import localbench.cli as cli_mod

    fixtures = await build_submission_fixtures(tmp_path)
    projection_out = tmp_path / "projection.json"
    status_updates: list[dict[str, object]] = []

    def fake_get(request: cli_mod.SubmissionStatusRequest) -> dict[str, object]:
        assert request.credentials.site == "https://local-bench.ai"
        assert request.credentials.admin_secret == "admin-secret"
        assert request.ticket_id == "sub_uploaded"
        return {"submission_id": "sub_uploaded", "status": "pending_verification", "origin": "community"}

    def fake_post(request: cli_mod.AdminVerificationRequest) -> dict[str, str]:
        assert request.credentials.site == "https://local-bench.ai"
        assert request.credentials.admin_secret == "admin-secret"
        assert request.submission_id == "sub_uploaded"
        status_updates.append(dict(request.status_update))
        return {"status": str(request.status_update["status"]), "submission_id": request.submission_id}

    monkeypatch.setenv("LOCALBENCH_ADMIN_SECRET", "admin-secret")
    monkeypatch.setattr(cli_mod, "get_submission_status", fake_get)
    monkeypatch.setattr(cli_mod, "post_admin_verification", fake_post)

    # When: the maintainer verifier command runs.
    code = main(
        [
            "submit",
            "admin-verify",
            "--site",
            "https://local-bench.ai",
            "--submission-id",
            "sub_uploaded",
            "--bundle",
            str(fixtures.run_path),
            "--suite-dir",
            str(fixtures.suite_dir),
            "--projection-out",
            str(projection_out),
        ],
    )

    # Then: the bundle is re-scored locally and posted as a verifier status update.
    output = capsys.readouterr().out
    assert code == 0
    assert status_updates[0]["schema_version"] == "localbench.submission_status_update.v1"
    assert status_updates[0]["raw_bundle_sha256"] == hashlib.sha256(fixtures.run_path.read_bytes()).hexdigest()
    assert "submission sub_uploaded" in output
    assert projection_out.exists()
    projection = json.loads(projection_out.read_text(encoding="utf-8"))
    assert projection["origin"] == "community"
    assert projection["trust_label"] == "community_self_submitted"


@pytest.mark.anyio
async def test_cli_admin_verify_fails_when_server_row_omits_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    from localbench.cli import main
    import localbench.cli as cli_mod

    fixtures = await build_submission_fixtures(tmp_path)

    def fake_get(request: cli_mod.SubmissionStatusRequest) -> dict[str, object]:
        assert request.ticket_id == "sub_uploaded"
        return {"submission_id": "sub_uploaded", "status": "pending_verification"}

    def fake_post(request: cli_mod.AdminVerificationRequest) -> dict[str, str]:
        raise AssertionError("admin verification must not post without origin")

    monkeypatch.setenv("LOCALBENCH_ADMIN_SECRET", "admin-secret")
    monkeypatch.setattr(cli_mod, "get_submission_status", fake_get)
    monkeypatch.setattr(cli_mod, "post_admin_verification", fake_post)

    code = main(
        [
            "submit",
            "admin-verify",
            "--site",
            "https://local-bench.ai",
            "--submission-id",
            "sub_uploaded",
            "--bundle",
            str(fixtures.run_path),
            "--suite-dir",
            str(fixtures.suite_dir),
            "--projection-out",
            str(tmp_path / "projection.json"),
        ],
    )

    output = capsys.readouterr().out
    assert code == 2
    assert "origin" in output


def _status_update(bundle_sha: str) -> dict[str, object]:
    return {
        "schema_version": "localbench.submission_status_update.v1",
        "accepted": True,
        "status": "accepted",
        "reason": "publishable",
        "blocking_reasons": [],
        "projection_sha256": "b" * 64,
        "projection_path": "projection.json",
        "raw_bundle_sha256": bundle_sha,
        "validator_version": "localbench.submission-validator.v1",
        "validator_commit": None,
        "validated_at": "2026-07-01T00:00:00Z",
    }
