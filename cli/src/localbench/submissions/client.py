from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict

import httpx

from localbench._types import JsonObject, JsonValue
from localbench.suite_resolver import DEFAULT_SUITE_ID
from localbench.submissions.validate import SubmissionValidationError


class SubmissionTicket(TypedDict):
    max_bytes: int
    server_nonce: str
    site: str
    status: str
    submission_id: str
    suite_hash: str
    upload_url: str
    account_id: NotRequired[str | None]


@dataclass(frozen=True, slots=True)
class SubmissionTicketRequest:
    public_key: str
    site: str
    suite_id: str = DEFAULT_SUITE_ID


@dataclass(frozen=True, slots=True)
class SubmissionUploadRequest:
    bundle_path: Path
    ticket: SubmissionTicket


@dataclass(frozen=True, slots=True)
class SubmissionStatusRequest:
    site: str
    submission_id: str


@dataclass(frozen=True, slots=True)
class AdminSubmissionListRequest:
    admin_secret: str
    site: str
    limit: int = 20
    status: str = "uploaded"


@dataclass(frozen=True, slots=True)
class AdminBundleDownloadRequest:
    download_url: str
    out_path: Path
    expected_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class AdminVerificationResultRequest:
    admin_secret: str
    site: str
    status: str
    submission_id: str
    error: str | None = None
    result_r2_key: str | None = None


class AdminSubmission(TypedDict):
    download_url: str
    r2_key: str
    status: str
    submission_id: str
    bundle_sha256: NotRequired[str | None]
    manifest_payload_sha256: NotRequired[str | None]
    size: NotRequired[int | None]


def read_submission_ticket(path: Path) -> SubmissionTicket:
    return _ticket(json.loads(path.read_text(encoding="utf-8")))


def request_submission_ticket(
    request: SubmissionTicketRequest,
    transport: httpx.BaseTransport | None = None,
) -> SubmissionTicket:
    with _http_client(transport) as client:
        response = client.post(
            _site_url(request.site, "/api/submissions/tickets"),
            json={"public_key": request.public_key, "suite_id": request.suite_id},
        )
        response.raise_for_status()
        return _ticket(response.json())


def upload_submission_bundle(
    request: SubmissionUploadRequest,
    transport: httpx.BaseTransport | None = None,
) -> JsonObject:
    bundle = request.bundle_path.read_bytes()
    bundle_sha = hashlib.sha256(bundle).hexdigest()
    with _http_client(transport) as client:
        upload_response = client.put(request.ticket["upload_url"], content=bundle)
        upload_response.raise_for_status()
        complete_response = client.post(
            _site_url(request.ticket["site"], f"/api/submissions/{request.ticket['submission_id']}/complete"),
            json={
                "bundle_sha256": bundle_sha,
                "manifest_payload_sha256": _manifest_payload_sha(request.bundle_path),
                "size": len(bundle),
            },
        )
        complete_response.raise_for_status()
        return _json_object(complete_response.json())


def complete_uploaded_bundle(
    request: SubmissionStatusRequest,
    transport: httpx.BaseTransport | None = None,
) -> JsonObject:
    with _http_client(transport) as client:
        response = client.get(_site_url(request.site, f"/api/submissions/{request.submission_id}"))
        response.raise_for_status()
        return _json_object(response.json())


def list_admin_submissions(
    request: AdminSubmissionListRequest,
    transport: httpx.BaseTransport | None = None,
) -> tuple[AdminSubmission, ...]:
    with _http_client(transport) as client:
        response = client.get(
            _site_url(request.site, "/api/admin/submissions"),
            headers=_admin_headers(request.admin_secret),
            params={"limit": request.limit, "status": request.status},
        )
        response.raise_for_status()
        data = _json_object(response.json())
        submissions = data.get("submissions")
        if not isinstance(submissions, list):
            raise SubmissionValidationError("admin submissions response must contain a submissions list")
        return tuple(_admin_submission(value) for value in submissions)


def download_admin_bundle(
    request: AdminBundleDownloadRequest,
    transport: httpx.BaseTransport | None = None,
) -> None:
    with _http_client(transport) as client:
        response = client.get(request.download_url)
        response.raise_for_status()
        data = response.content
    if request.expected_sha256 is not None:
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != request.expected_sha256:
            raise SubmissionValidationError(f"downloaded bundle sha256 mismatch: {actual_sha} != {request.expected_sha256}")
    request.out_path.parent.mkdir(parents=True, exist_ok=True)
    request.out_path.write_bytes(data)


def mark_admin_verification_result(
    request: AdminVerificationResultRequest,
    transport: httpx.BaseTransport | None = None,
) -> JsonObject:
    payload: JsonObject = {"status": request.status}
    if request.error is not None:
        payload["error"] = request.error
    if request.result_r2_key is not None:
        payload["result_r2_key"] = request.result_r2_key
    with _http_client(transport) as client:
        response = client.post(
            _site_url(request.site, f"/api/admin/submissions/{request.submission_id}/verification"),
            headers=_admin_headers(request.admin_secret),
            json=payload,
        )
        response.raise_for_status()
        return _json_object(response.json())


def _http_client(transport: httpx.BaseTransport | None) -> httpx.Client:
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
    if transport is not None:
        return httpx.Client(transport=transport, timeout=timeout, follow_redirects=True)
    return httpx.Client(
        transport=httpx.HTTPTransport(retries=3),
        timeout=timeout,
        follow_redirects=True,
    )


def _site_url(site: str, path: str) -> str:
    return f"{site.rstrip('/')}{path}"


def _admin_headers(secret: str) -> dict[str, str]:
    return {"x-localbench-admin-secret": secret}


def _ticket(value: JsonValue) -> SubmissionTicket:
    data = _json_object(value)
    return {
        "account_id": _nullable_text(data.get("account_id")),
        "max_bytes": _required_int(data, "max_bytes"),
        "server_nonce": _required_text(data, "server_nonce"),
        "site": _required_text(data, "site"),
        "status": _required_text(data, "status"),
        "submission_id": _required_text(data, "submission_id"),
        "suite_hash": _required_text(data, "suite_hash"),
        "upload_url": _required_text(data, "upload_url"),
    }


def _admin_submission(value: JsonValue) -> AdminSubmission:
    data = _json_object(value)
    return {
        "bundle_sha256": _nullable_text(data.get("bundle_sha256")),
        "download_url": _required_text(data, "download_url"),
        "manifest_payload_sha256": _nullable_text(data.get("manifest_payload_sha256")),
        "r2_key": _required_text(data, "r2_key"),
        "size": _nullable_int(data.get("size")),
        "status": _required_text(data, "status"),
        "submission_id": _required_text(data, "submission_id"),
    }


def _json_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise SubmissionValidationError("API response must be a JSON object")
    return value


def _manifest_payload_sha(bundle_path: Path) -> str:
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise SubmissionValidationError("bundle manifest.json is missing or invalid") from error
    if not isinstance(manifest, dict):
        raise SubmissionValidationError("bundle manifest must be a JSON object")
    payload_sha = manifest.get("payload_sha256")
    if not isinstance(payload_sha, str):
        raise SubmissionValidationError("bundle manifest payload_sha256 must be a string")
    return payload_sha


def _required_text(data: JsonObject, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SubmissionValidationError(f"API response field {key} must be a non-empty string")
    return value


def _nullable_text(value: JsonValue | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise SubmissionValidationError("API response account_id must be a string or null")


def _nullable_int(value: JsonValue | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise SubmissionValidationError("API response size must be an integer or null")


def _required_int(data: JsonObject, key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise SubmissionValidationError(f"API response field {key} must be an integer")
    return value
