from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

import httpx

from localbench._types import JsonObject, JsonValue
from localbench.http_errors import raise_for_status_with_body
from localbench.submissions.origin import SubmissionOrigin, normalize_origin
from localbench.submissions.validate import SubmissionValidationError

PublishState = Literal["hidden", "preview", "published"]


class SubmissionEnvelope(TypedDict):
    accepted_suite_terms: bool
    allowed_schema: str
    bundle_sha256: str
    expected_suite_manifest_sha256: str | None
    expected_suite_release_id: str | None
    expiry: str
    max_upload_bytes: int
    one_use: bool
    origin: SubmissionOrigin
    schema_version: str
    submitter_id: str
    ticket_id: str
    upload_capability: str
    declared_model_slug: NotRequired[str]
    community_model_group_id: NotRequired[str]
    submitter_display_name: NotRequired[str]


class UploadTarget(TypedDict):
    bucket: str
    content_sha256: str
    expires_seconds: int
    method: str
    r2_key: str
    upload_url: str
    upload_headers: NotRequired[dict[str, str]]


@dataclass(frozen=True, slots=True)
class SiteCredentials:
    site: str
    bypass_token: str | None = None
    admin_secret: str | None = None


@dataclass(frozen=True, slots=True)
class TicketProofOfPossession:
    timestamp: str
    signature: str
    message: str


@dataclass(frozen=True, slots=True)
class SubmissionTicketRequest:
    credentials: SiteCredentials
    raw_bundle_sha256: str
    public_key: str | None = None
    submitter_id: str | None = None
    declared_model_slug: str | None = None
    community_model_group_id: str | None = None
    expected_suite_release_id: str | None = None
    expected_suite_manifest_sha256: str | None = None
    pop: TicketProofOfPossession | None = None
    submitter_display_name: str | None = None


@dataclass(frozen=True, slots=True)
class SubmissionUploadRequest:
    bundle_path: Path
    credentials: SiteCredentials
    envelope: SubmissionEnvelope
    accepted_result_projection: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class SubmissionStatusRequest:
    credentials: SiteCredentials
    ticket_id: str


@dataclass(frozen=True, slots=True)
class AdminVerificationRequest:
    credentials: SiteCredentials
    submission_id: str
    status_update: JsonObject
    override: bool = False


@dataclass(frozen=True, slots=True)
class AdminDecisionRequest:
    credentials: SiteCredentials
    submission_id: str
    publish_state: PublishState


def raw_bundle_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_submission_envelope(path: Path) -> SubmissionEnvelope:
    return _envelope(json.loads(path.read_text(encoding="utf-8")))


def request_submission_ticket(
    request: SubmissionTicketRequest,
    transport: httpx.BaseTransport | None = None,
) -> SubmissionEnvelope:
    with _http_client(transport) as client:
        response = client.post(
            _site_url(request.credentials.site, "/api/submissions/tickets"),
            headers=_site_headers(request.credentials),
            json=_ticket_request_body(request),
        )
        raise_for_status_with_body(response)
        return _envelope(response.json())


def upload_submission_bundle(
    request: SubmissionUploadRequest,
    transport: httpx.BaseTransport | None = None,
) -> JsonObject:
    bundle = request.bundle_path.read_bytes()
    bundle_sha = hashlib.sha256(bundle).hexdigest()
    _ensure_bundle_matches_ticket(bundle_sha, request.envelope)
    with _http_client(transport) as client:
        target_response = client.post(
            _site_url(request.credentials.site, "/api/submissions/request-upload"),
            headers=_site_headers(request.credentials),
            json={
                "raw_bundle_sha256": bundle_sha,
                "size_bytes": len(bundle),
                "ticket_id": request.envelope["ticket_id"],
                "upload_capability": request.envelope["upload_capability"],
            },
        )
        raise_for_status_with_body(target_response)
        target = _upload_target(target_response.json())
        if target["content_sha256"] != bundle_sha:
            raise SubmissionValidationError("upload target content_sha256 does not match bundle")
        if target["method"] != "PUT":
            raise SubmissionValidationError("upload target method must be PUT")
        upload_response = client.put(
            target["upload_url"],
            content=bundle,
            headers={"content-type": "application/json", **target.get("upload_headers", {})},
        )
        raise_for_status_with_body(upload_response)
        complete_body: JsonObject = {
            "raw_bundle_sha256": bundle_sha,
            "size_bytes": len(bundle),
            "upload_capability": request.envelope["upload_capability"],
        }
        if request.accepted_result_projection is not None:
            complete_body["accepted_result_projection"] = request.accepted_result_projection
        complete_response = client.post(
            _site_url(
                request.credentials.site,
                f"/api/submissions/{request.envelope['ticket_id']}/complete",
            ),
            headers=_site_headers(request.credentials),
            json=complete_body,
        )
        raise_for_status_with_body(complete_response)
        return _json_object(complete_response.json())


def get_submission_status(
    request: SubmissionStatusRequest,
    transport: httpx.BaseTransport | None = None,
) -> JsonObject:
    with _http_client(transport) as client:
        response = client.get(
            _site_url(request.credentials.site, f"/api/submissions/{request.ticket_id}"),
            headers=_site_headers(request.credentials),
        )
        raise_for_status_with_body(response)
        return _json_object(response.json())


def post_admin_verification(
    request: AdminVerificationRequest,
    transport: httpx.BaseTransport | None = None,
) -> JsonObject:
    with _http_client(transport) as client:
        response = client.post(
            _site_url(
                request.credentials.site,
                f"/api/admin/submissions/{request.submission_id}/verification"
                + ("?override=true" if request.override else ""),
            ),
            headers=_site_headers(request.credentials),
            json=request.status_update,
        )
        raise_for_status_with_body(response)
        return _json_object(response.json())


def post_admin_decision(
    request: AdminDecisionRequest,
    transport: httpx.BaseTransport | None = None,
) -> JsonObject:
    with _http_client(transport) as client:
        response = client.post(
            _site_url(
                request.credentials.site,
                f"/api/admin/submissions/{request.submission_id}/decision",
            ),
            headers=_site_headers(request.credentials),
            json={"publish_state": request.publish_state},
        )
        raise_for_status_with_body(response)
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


def _site_headers(credentials: SiteCredentials) -> dict[str, str]:
    headers: dict[str, str] = {}
    if credentials.bypass_token is not None:
        headers["x-localbench-bypass"] = credentials.bypass_token
    if credentials.admin_secret is not None:
        headers["x-localbench-admin-secret"] = credentials.admin_secret
    return headers


def _ticket_request_body(request: SubmissionTicketRequest) -> JsonObject:
    if (request.public_key is None) == (request.submitter_id is None):
        raise SubmissionValidationError("exactly one of public_key or submitter_id is required")
    payload: JsonObject = {
        "accepted_suite_terms": True,
        "bundle_sha256": request.raw_bundle_sha256,
    }
    if request.public_key is not None:
        payload["public_key"] = request.public_key
    if request.submitter_id is not None:
        payload["submitter_id"] = request.submitter_id
    if request.declared_model_slug is not None:
        payload["declared_model_slug"] = request.declared_model_slug
    if request.community_model_group_id is not None:
        payload["community_model_group_id"] = request.community_model_group_id
    if request.expected_suite_release_id is not None:
        payload["expected_suite_release_id"] = request.expected_suite_release_id
    if request.expected_suite_manifest_sha256 is not None:
        payload["expected_suite_manifest_sha256"] = request.expected_suite_manifest_sha256
    if request.pop is not None:
        payload["pop"] = {
            "timestamp": request.pop.timestamp,
            "signature": request.pop.signature,
        }
    if request.submitter_display_name is not None:
        payload["submitter_display_name"] = request.submitter_display_name
    return payload


def _ensure_bundle_matches_ticket(raw_sha: str, envelope: SubmissionEnvelope) -> None:
    if envelope["bundle_sha256"] != raw_sha:
        raise SubmissionValidationError("bundle sha256 does not match submission envelope")


def _envelope(value: JsonValue) -> SubmissionEnvelope:
    data = _json_object(value)
    envelope: SubmissionEnvelope = {
        "accepted_suite_terms": _required_true(data, "accepted_suite_terms"),
        "allowed_schema": _required_text(data, "allowed_schema"),
        "bundle_sha256": _required_text(data, "bundle_sha256"),
        "expected_suite_manifest_sha256": _nullable_text(data.get("expected_suite_manifest_sha256")),
        "expected_suite_release_id": _nullable_text(data.get("expected_suite_release_id")),
        "expiry": _required_text(data, "expiry"),
        "max_upload_bytes": _required_int(data, "max_upload_bytes"),
        "one_use": _required_true(data, "one_use"),
        "origin": normalize_origin(_required_text(data, "origin")),
        "schema_version": _required_text(data, "schema_version"),
        "submitter_id": _required_text(data, "submitter_id"),
        "ticket_id": _required_text(data, "ticket_id"),
        "upload_capability": _required_text(data, "upload_capability"),
    }
    declared_model_slug = _nullable_text(data.get("declared_model_slug"))
    if declared_model_slug is not None:
        envelope["declared_model_slug"] = declared_model_slug
    submitter_display_name = _nullable_text(data.get("submitter_display_name"))
    if submitter_display_name is not None:
        envelope["submitter_display_name"] = submitter_display_name
    return envelope


def _upload_target(value: JsonValue) -> UploadTarget:
    data = _json_object(value)
    target: UploadTarget = {
        "bucket": _required_text(data, "bucket"),
        "content_sha256": _required_text(data, "content_sha256"),
        "expires_seconds": _required_int(data, "expires_seconds"),
        "method": _required_text(data, "method"),
        "r2_key": _required_text(data, "r2_key"),
        "upload_url": _required_text(data, "upload_url"),
    }
    headers = data.get("upload_headers")
    if headers is not None:
        if not isinstance(headers, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in headers.items()):
            raise SubmissionValidationError("API response field upload_headers must map strings to strings")
        target["upload_headers"] = dict(headers)
    return target


def _json_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise SubmissionValidationError("API response must be a JSON object")
    return value


def _required_text(data: JsonObject, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SubmissionValidationError(f"API response field {key} must be a non-empty string")
    return value


def _nullable_text(value: JsonValue | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise SubmissionValidationError("API response field must be a string or null")


def _required_int(data: JsonObject, key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise SubmissionValidationError(f"API response field {key} must be an integer")
    return value


def _required_true(data: JsonObject, key: str) -> bool:
    if data.get(key) is not True:
        raise SubmissionValidationError(f"API response field {key} must be true")
    return True
