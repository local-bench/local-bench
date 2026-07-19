from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from localbench._types import JsonObject, JsonValue
from localbench.http_errors import response_error_detail
from localbench.submissions.client import (
    SiteCredentials,
    SubmissionEnvelope,
    SubmissionStatusRequest,
    SubmissionTicketRequest,
    SubmissionUploadRequest,
    TicketProofOfPossession,
    get_submission_status,
    request_submission_ticket,
    upload_submission_bundle,
)
from localbench.submissions.client_projection import build_client_reported_projection
from localbench.submissions.crypto import sign_bytes
from localbench.submissions.foundation import is_site_released_suite_pair, site_released_suite_pairs
from localbench.submissions.bundle_input import load_result_bundle_input
from localbench.submissions.foundation import result_bundle_headline_complete
from localbench.submissions.submit_run_inputs import (
    DEFAULT_SITE,
    BundleInfo,
    KeyIdentity,
    SubmitConfig,
    SubmitInputError,
    bundle_lines,
    default_signing_key_path,
    key_lines,
    prepare_bundle,
    read_config,
    resolve_key,
    submit_config_path,
    write_config,
)
from localbench.submissions.submit_run_output import dry_run_lines, summary_lines

__all__ = [
    "DEFAULT_SITE",
    "SubmitRunError",
    "SubmitRunOptions",
    "default_signing_key_path",
    "submit_finished_run",
]


@dataclass(frozen=True, slots=True)
class SubmitRunOptions:
    site: str | None
    run: Path | None
    bundle: Path | None
    suite_dir: Path | None
    signing_key: Path | None
    display_name: str | None
    bypass_token: str | None
    bypass_token_file: Path | None
    dry_run: bool


@dataclass(frozen=True, slots=True)
class SubmitRunResult:
    exit_code: int
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubmitRunError(Exception):
    message: str
    exit_code: int = 2

    def __str__(self) -> str:
        return self.message


class TicketExpiredError(Exception):
    pass


class AlreadySubmittedError(Exception):
    def __init__(self, submission_id: str) -> None:
        super().__init__(submission_id)
        self.submission_id = submission_id

def submit_finished_run(options: SubmitRunOptions) -> SubmitRunResult:
    config_path = submit_config_path()
    try:
        config = read_config(config_path)
        site = options.site or config.site or DEFAULT_SITE
        display_name = options.display_name if options.display_name is not None else config.display_name
        key = resolve_key(options.signing_key)
    except SubmitInputError as error:
        raise SubmitRunError(str(error)) from error
    lines = key_lines(key)
    try:
        with tempfile.TemporaryDirectory(prefix="localbench-submit-") as temp_name:
            bundle = prepare_bundle(
                run=options.run,
                bundle=options.bundle,
                suite_dir=options.suite_dir,
                signing_key=key.path,
                temp_dir=Path(temp_name),
            )
            lines.extend(bundle_lines(bundle))
            if not result_bundle_headline_complete(load_result_bundle_input(bundle.path).record):
                raise SubmitInputError(
                    "incomplete_run: submissions require all six headline axes; "
                    "finish coding and agentic grading before submitting",
                )
            if options.dry_run:
                lines.extend(dry_run_lines(site, key.public_key, display_name, bundle))
                return SubmitRunResult(exit_code=0, lines=tuple(lines))
            _precheck_registered_suite_pair(bundle)
            validated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            ticket = _request_ticket(site, options, key, display_name, bundle)
            projection = build_client_reported_projection(
                bundle.path,
                ticket,
                validated_at=validated_at,
                suite_dir=options.suite_dir,
            )
            try:
                upload = _upload_bundle(site, options, ticket, bundle.path, projection)
            except TicketExpiredError:
                ticket = _request_ticket(site, options, key, display_name, bundle)
                projection = build_client_reported_projection(
                    bundle.path,
                    ticket,
                    suite_dir=options.suite_dir,
                    validated_at=validated_at,
                )
                try:
                    upload = _upload_bundle(site, options, ticket, bundle.path, projection)
                except TicketExpiredError as error:
                    raise SubmitRunError("ticket expired again after rotation") from error
            submission_id = _text(upload.get("submission_id")) or ticket["ticket_id"]
            status = _status(site, options, submission_id)
            if options.display_name is not None:
                write_config(config_path, SubmitConfig(display_name=options.display_name, site=site))
            lines.extend(summary_lines(status, submission_id, site))
            return SubmitRunResult(exit_code=0, lines=tuple(lines))
    except AlreadySubmittedError as error:
        if options.display_name is not None:
            write_config(config_path, SubmitConfig(display_name=options.display_name, site=site))
        lines.append(
            f"this exact bundle is already submitted as {error.submission_id}; "
            "a re-run produces a new bundle you can submit",
        )
        return SubmitRunResult(exit_code=0, lines=tuple(lines))
    except SubmitInputError as error:
        raise SubmitRunError(str(error)) from error


def _precheck_registered_suite_pair(bundle: BundleInfo) -> None:
    if is_site_released_suite_pair(bundle.suite_release_id, bundle.suite_manifest_sha256):
        return
    registered = ", ".join(sorted(site_released_suite_pairs()))
    raise SubmitRunError(
        "suite release pair is not registered for submission: "
        f"{bundle.suite_release_id} / {bundle.suite_manifest_sha256}. "
        "Run against a current registered release before submitting. "
        f"Registered releases: {registered}.",
    )


def _request_ticket(
    site: str,
    options: SubmitRunOptions,
    key: KeyIdentity,
    display_name: str | None,
    bundle: BundleInfo,
) -> SubmissionEnvelope:
    pop = _pop(bundle, key.path)
    request = SubmissionTicketRequest(
        credentials=SiteCredentials(site=site, bypass_token=_bypass_token(options)),
        raw_bundle_sha256=bundle.sha256,
        public_key=key.public_key,
        declared_model_slug=bundle.declared_model_slug,
        expected_suite_release_id=bundle.suite_release_id,
        expected_suite_manifest_sha256=bundle.suite_manifest_sha256,
        pop=pop,
        submitter_display_name=display_name,
    )
    try:
        return request_submission_ticket(request)
    except httpx.RequestError as error:
        raise SubmitRunError(f"network failure during ticket: {error}") from error
    except httpx.HTTPStatusError as error:
        raise _mapped_http_error(error, "ticket") from error


def _pop(bundle: BundleInfo, signing_key: Path) -> TicketProofOfPossession:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = "\n".join(
        (
            "localbench.ticket_pop.v1",
            bundle.sha256,
            bundle.suite_release_id,
            bundle.suite_manifest_sha256,
            timestamp,
        ),
    )
    return TicketProofOfPossession(
        timestamp=timestamp,
        signature=sign_bytes(message.encode("utf-8"), signing_key),
        message=message,
    )


def _upload_bundle(
    site: str,
    options: SubmitRunOptions,
    envelope: SubmissionEnvelope,
    bundle_path: Path,
    projection: JsonObject,
) -> JsonObject:
    try:
        return upload_submission_bundle(
            SubmissionUploadRequest(
                bundle_path=bundle_path,
                credentials=SiteCredentials(site=site, bypass_token=_bypass_token(options)),
                envelope=envelope,
                accepted_result_projection=projection,
            ),
        )
    except httpx.RequestError as error:
        raise SubmitRunError(f"network failure during upload: {error}") from error
    except httpx.HTTPStatusError as error:
        mapped = _mapped_http_error(error, "upload")
        if isinstance(mapped, TicketExpiredError):
            raise mapped from error
        raise mapped from error


def _status(site: str, options: SubmitRunOptions, submission_id: str) -> JsonObject:
    try:
        return get_submission_status(
            SubmissionStatusRequest(
                credentials=SiteCredentials(site=site, bypass_token=_bypass_token(options)),
                ticket_id=submission_id,
            ),
        )
    except httpx.RequestError as error:
        raise SubmitRunError(f"network failure during status: {error}") from error
    except httpx.HTTPStatusError as error:
        raise _mapped_http_error(error, "status") from error


def _mapped_http_error(error: httpx.HTTPStatusError, leg: str) -> Exception:
    payload = _response_json(error.response)
    code = _text(payload.get("code"))
    if error.response.status_code == 409 and code == "bundle_already_submitted":
        raise AlreadySubmittedError(_text(payload.get("submission_id")) or "unknown")
    if error.response.status_code == 410 and code == "ticket_expired":
        return TicketExpiredError()
    if error.response.status_code == 429 and code in {"rate_limited", "upload_byte_budget_exceeded"}:
        retry_after = payload.get("retry_after_seconds")
        return SubmitRunError(f"rate_limited retry_after_seconds={retry_after}", exit_code=3)
    if error.response.status_code == 429 and code == "pending_review_limit":
        return SubmitRunError(
            "submission cap: you already have the maximum submissions awaiting maintainer "
            "review; this clears when one is reviewed (not with time). Check them with "
            "`localbench submit status <submission_id>`",
            exit_code=3,
        )
    if code == "pop_stale":
        return SubmitRunError("check your system clock (server allows ±10 minutes)")
    if code == "invalid_ticket_request":
        detail = response_error_detail(error.response)
        prefix = "ticket failed: invalid_ticket_request"
        if detail and detail != "invalid_ticket_request":
            prefix = f"{prefix}: {detail.removeprefix('invalid_ticket_request: ')}"
        return SubmitRunError(
            f"{prefix} — the server rejected a request field. "
            "The most common cause is --display-name: 2-40 chars, ASCII letters/digits at the "
            "start and end, only spaces . _ ' - in between (no accents, parentheses, or URLs). "
            "Retry with a simpler name, or omit --display-name entirely."
        )
    return SubmitRunError(f"{leg} failed: {response_error_detail(error.response) or error.response.status_code}")


def _response_json(response: httpx.Response) -> JsonObject:
    try:
        parsed = response.json()
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _bypass_token(options: SubmitRunOptions) -> str | None:
    if options.bypass_token_file is not None:
        return options.bypass_token_file.read_text(encoding="utf-8").strip()
    return options.bypass_token


def _text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None
