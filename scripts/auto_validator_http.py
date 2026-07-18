from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import localbench.submissions.client as submission_client
from localbench.submissions.client import AdminVerificationRequest, SiteCredentials, post_admin_verification

from auto_validator_model import ApiError, ConflictError, JsonObject, json_object


class StdlibApi:
    def __init__(self, site: str, validator_secret: str) -> None:
        self.site = site.rstrip("/")
        self.validator_secret = validator_secret

    def list_submissions(self, status: str) -> list[JsonObject]:
        query = urllib.parse.urlencode({"status": status, "limit": 50})
        payload = self._json_request(f"/api/admin/submissions?{query}", authenticated=True)
        rows = payload.get("submissions")
        if not isinstance(rows, list):
            raise ApiError("submission listing has no submissions array")
        return [json_object(row) for row in rows]

    def get_submission(self, submission_id: str) -> JsonObject:
        quoted = urllib.parse.quote(submission_id, safe="")
        return self._json_request(f"/api/submissions/{quoted}", authenticated=False)

    def download_bundle(self, submission_id: str, destination: Path) -> None:
        quoted = urllib.parse.quote(submission_id, safe="")
        request = urllib.request.Request(
            f"{self.site}/api/admin/submissions/{quoted}/bundle",
            headers={"x-localbench-validator-secret": self.validator_secret},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                data = response.read()
        except urllib.error.HTTPError as error:
            raise ApiError(f"bundle download HTTP {error.code}", status=error.code) from error
        except urllib.error.URLError as error:
            raise ApiError(f"bundle download failed: {error.reason}") from error
        destination.write_bytes(data)

    def _json_request(self, path: str, *, authenticated: bool) -> JsonObject:
        headers = {"x-localbench-validator-secret": self.validator_secret} if authenticated else {}
        request = urllib.request.Request(f"{self.site}{path}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return json_object(json.loads(response.read()))
        except urllib.error.HTTPError as error:
            raise ApiError(f"GET {path} HTTP {error.code}", status=error.code) from error
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ApiError(f"GET {path} failed: {error}") from error


class ValidatorHeaderTransport(submission_client.httpx.BaseTransport):
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def handle_request(self, request: submission_client.httpx.Request) -> submission_client.httpx.Response:
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() != "x-localbench-admin-secret"
        }
        headers["x-localbench-validator-secret"] = self.secret
        wire_request = urllib.request.Request(
            str(request.url),
            data=request.read() or None,
            headers=headers,
            method=request.method,
        )
        try:
            with urllib.request.urlopen(wire_request, timeout=30) as response:  # noqa: S310
                return submission_client.httpx.Response(
                    response.status,
                    headers=dict(response.headers.items()),
                    content=response.read(),
                    request=request,
                )
        except urllib.error.HTTPError as error:
            return submission_client.httpx.Response(
                error.code,
                headers=dict(error.headers.items()),
                content=error.read(),
                request=request,
            )
        except urllib.error.URLError as error:
            raise ApiError(f"verification POST failed: {error.reason}") from error


def post_with_installed_helper(
    site: str,
    validator_secret: str,
    submission_id: str,
    update: JsonObject,
) -> JsonObject:
    request = AdminVerificationRequest(
        credentials=SiteCredentials(site=site, admin_secret=validator_secret),
        submission_id=submission_id,
        status_update=update,
    )
    try:
        return post_admin_verification(request, transport=ValidatorHeaderTransport(validator_secret))
    except ApiError:
        raise
    except submission_client.httpx.HTTPError as error:
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        if status == 409:
            raise ConflictError("verification POST conflict") from error
        raise ApiError(f"verification POST failed with HTTP {status or 'transport error'}", status=status) from error
