from __future__ import annotations

import json
import os
import re
import subprocess
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from localbench.submissions.decision_log import DecisionLogEntry
from localbench.submissions.validate import SubmissionValidationError

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
PostResult = JsonObject
MAX_DETAIL = 300
MAX_API_FAILURES = 5
KEEP_WORK_ENTRIES = 20
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\|/)[^\s,;]+")
SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
SERVER_REASON_CODES = frozenset(
    {
        "bundle_unreadable",
        "schema_violation",
        "rescore_failed",
        "internal_error",
        "unsafe_metadata",
        "suite_mismatch",
        "scorecard_mismatch",
        "signature_invalid",
        "duplicate_artifact",
        "protected_identity",
    },
)


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ConflictError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status=409)


class AlreadyRunningError(RuntimeError):
    pass


class ConfigurationError(RuntimeError):
    pass


class SubmissionApi(Protocol):
    def list_submissions(self, status: str) -> list[JsonObject]: ...

    def get_submission(self, submission_id: str) -> JsonObject: ...

    def download_bundle(self, submission_id: str, destination: Path) -> None: ...


class VerifyCall(Protocol):
    def __call__(
        self,
        bundle_path: Path,
        *,
        suite_dir: Path,
        projection_out: Path,
        validated_at: str,
        validator_commit: str | None,
        origin: str,
        coding_verified_path: Path | None = None,
    ) -> JsonObject: ...


class PostCall(Protocol):
    def __call__(self, submission_id: str, update: JsonObject) -> PostResult: ...


class AppendLogCall(Protocol):
    def __call__(
        self,
        *,
        actor: str,
        action: str,
        submission_id: str,
        reason: str,
        extra: JsonObject | None = None,
    ) -> DecisionLogEntry: ...


@dataclass(frozen=True, slots=True)
class Config:
    site: str
    suite_dir: Path
    validator_secret: str
    root_dir: Path
    work_dir: Path | None = None
    dry_run: bool = False
    validator_commit: str | None = None
    coding_image: str | None = None
    receipt_signing_key: Path | None = None

    @property
    def effective_work_dir(self) -> Path:
        return self.work_dir or self.root_dir / "work"

    @property
    def pause_file(self) -> Path:
        return self.root_dir / "pause"

    @property
    def lock_file(self) -> Path:
        return self.root_dir / "lock.pid"

    @property
    def intent_file(self) -> Path:
        return self.root_dir / "intents.jsonl"

    @property
    def alert_file(self) -> Path:
        return self.root_dir / "ALERT.txt"

    @property
    def log_file(self) -> Path:
        return self.root_dir / "auto-validator.log"


def sort_fifo(rows: list[JsonObject]) -> list[JsonObject]:
    return sorted(rows, key=lambda row: text(row.get("created_at")) or text(row.get("uploaded_at")) or "")


def backoff_seconds(consecutive_failures: int) -> int:
    return min(30 * (2 ** max(consecutive_failures - 1, 0)), 600)


def guard_tripped(pause_file: Path, *, process_listing: str | None = None) -> bool:
    if pause_file.exists():
        return True
    listing = process_listing if process_listing is not None else tasklist()
    lowered = listing.lower()
    return "llama-server" in lowered or any(
        "localbench" in line and "bench" in line
        for line in lowered.splitlines()
    )


def map_rejection(
    error: Exception,
    *,
    secret: str = "",
    validation_types: tuple[type[Exception], ...] = (SubmissionValidationError,),
) -> tuple[str, str]:
    detail = scrub_text(f"{type(error).__name__}: {error}", secret)[:MAX_DETAIL]
    if isinstance(error, (json.JSONDecodeError, zipfile.BadZipFile, OSError)):
        return "bundle_unreadable", detail
    if isinstance(error, validation_types) or "validation" in type(error).__name__.lower() or "contract" in type(error).__name__.lower():
        return reported_reason_code(error) or "schema_violation", detail
    if isinstance(error, ApiError):
        return "internal_error", detail
    if isinstance(error, RuntimeError):
        return "rescore_failed", detail
    return "internal_error", detail


def rejection_update(reason_code: str, reason_detail: str) -> JsonObject:
    return {
        "operation": "initial_decision",
        "status": "rejected",
        "reason_code": reason_code,
        "reason_detail": reason_detail[:MAX_DETAIL],
    }


def initial_update(verified: JsonObject) -> JsonObject:
    if verified.get("status") == "accepted":
        return {**verified, "operation": "initial_decision"}
    blockers = verified.get("blocking_reasons")
    reasons = [value for value in blockers if isinstance(value, str)] if isinstance(blockers, list) else []
    reason_code = next((value for value in reasons if value in SERVER_REASON_CODES), "schema_violation")
    detail = ";".join(reasons) or (text(verified.get("reason")) or "validation failed")
    return rejection_update(reason_code, scrub_text(detail)[:MAX_DETAIL])


def scrub_text(value: str, secret: str = "") -> str:
    scrubbed = value.replace(secret, "[REDACTED]") if secret else value
    return PATH_PATTERN.sub("[PATH]", scrubbed).replace("\r", " ").replace("\n", " ")


def utc_now(*, compact: bool = False) -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y%m%dT%H%M%SZ") if compact else now.strftime("%Y-%m-%dT%H:%M:%SZ")


def reported_reason_code(error: Exception) -> str | None:
    value = getattr(error, "reason_code", None)
    if isinstance(value, str) and value in SERVER_REASON_CODES:
        return value
    first = str(error).split(":", maxsplit=1)[0]
    return first if first in SERVER_REASON_CODES else None


def coding_not_measured(row: JsonObject) -> bool:
    projection = row.get("projection")
    axes = projection.get("axes") if isinstance(projection, dict) else None
    coding = axes.get("coding") if isinstance(axes, dict) else None
    return isinstance(coding, dict) and coding.get("status") == "not_measured"


def json_object(value: JsonValue | bytes) -> JsonObject:
    if not isinstance(value, dict):
        raise ApiError("API response must be a JSON object")
    return value


def text(value: JsonValue) -> str | None:
    return value if isinstance(value, str) and value else None


def required_text(data: JsonObject, key: str) -> str:
    value = text(data.get(key))
    if value is None:
        raise ApiError(f"API response field {key} must be a non-empty string")
    return value


def required_int(data: JsonObject, key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError(f"API response field {key} must be an integer")
    return value


def tasklist() -> str:
    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def run_command(argv: Sequence[str]) -> int:
    return subprocess.run(list(argv), check=False).returncode


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
