from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.submissions.canon import canonical_json_bytes, sha256_bytes
from localbench.submissions.crypto import load_private_key, sign_bytes, verify_bytes
from localbench.submissions.keys import write_private_key

GENESIS_PREV_SHA256: Final = "0" * 64
_LOG_NAME: Final = "decision-log.jsonl"
_KEY_NAME: Final = "ops_log_ed25519.pem"
_ALLOWED_RECORD_KEYS: Final = {
    "action",
    "actor",
    "at",
    "extra",
    "prev_entry_sha256",
    "reason",
    "seq",
    "sig",
    "submission_id",
}


@dataclass(frozen=True, slots=True)
class DecisionLogEntry:
    seq: int
    prev_entry_sha256: str
    at: str
    actor: str
    action: str
    submission_id: str
    reason: str
    extra: JsonObject
    sig: str


@dataclass(frozen=True, slots=True)
class DecisionLogVerification:
    ok: bool
    entries: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionLogError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def localbench_home() -> Path:
    configured = os.environ.get("LOCALBENCH_HOME")
    if configured is not None and configured.strip():
        return Path(configured).expanduser()
    return Path.home() / ".localbench"


def decision_log_path() -> Path:
    return localbench_home() / _LOG_NAME


def decision_log_key_path() -> Path:
    return localbench_home() / _KEY_NAME


def append_decision_log(
    *,
    actor: str,
    action: str,
    submission_id: str,
    reason: str,
    extra: JsonObject | None = None,
) -> DecisionLogEntry:
    path = decision_log_path()
    records = _read_records(path)
    verification = verify_log()
    if not verification.ok:
        raise DecisionLogError(verification.error or "decision log verification failed")
    key_path = _ensure_key()
    prev_hash = _last_record_hash(records)
    seq = _next_seq(records)
    payload: JsonObject = {
        "action": action,
        "actor": actor,
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extra": extra or {},
        "prev_entry_sha256": prev_hash,
        "reason": reason,
        "seq": seq,
        "submission_id": submission_id,
    }
    signed: JsonObject = dict(payload)
    signed["sig"] = sign_bytes(canonical_json_bytes(payload), key_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json_bytes(signed).decode("utf-8") + "\n")
    return _entry_from_record(signed, line_number=seq)


def verify_log() -> DecisionLogVerification:
    path = decision_log_path()
    if not path.exists():
        return DecisionLogVerification(ok=True, entries=0)
    try:
        public_key = load_private_key(decision_log_key_path()).public_key.hex()
        records = _read_records(path)
        expected_prev = GENESIS_PREV_SHA256
        expected_seq = 1
        for line_number, record in enumerate(records, start=1):
            entry = _entry_from_record(record, line_number=line_number)
            if entry.seq != expected_seq:
                return DecisionLogVerification(
                    ok=False,
                    entries=line_number - 1,
                    error=f"seq gap at line {line_number}: expected {expected_seq}, got {entry.seq}",
                )
            if entry.prev_entry_sha256 != expected_prev:
                return DecisionLogVerification(
                    ok=False,
                    entries=line_number - 1,
                    error=f"hash chain mismatch at line {line_number}",
                )
            if not verify_bytes(canonical_json_bytes(_payload(entry)), entry.sig, public_key):
                return DecisionLogVerification(
                    ok=False,
                    entries=line_number - 1,
                    error=f"signature verification failed at line {line_number}",
                )
            expected_prev = sha256_bytes(canonical_json_bytes(record))
            expected_seq += 1
    except (DecisionLogError, OSError, ValueError) as error:
        return DecisionLogVerification(ok=False, entries=0, error=str(error))
    return DecisionLogVerification(ok=True, entries=len(records))


def format_decision_log_entries(tail: int | None = None) -> tuple[str, ...]:
    records = _read_records(decision_log_path())
    entries = [_entry_from_record(record, line_number=index) for index, record in enumerate(records, start=1)]
    shown = entries if tail is None else entries[-tail:] if tail > 0 else []
    return tuple(
        f"{entry.seq} {entry.action} {entry.submission_id} {entry.actor} {entry.reason}"
        for entry in shown
    )


def _ensure_key() -> Path:
    path = decision_log_key_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    public_key = write_private_key(path)
    try:
        path.chmod(0o600)
    except OSError as error:
        print(f"warning    could not restrict ops log key permissions: {error}")
    print(f"ops_log_public_key {public_key}")
    return path


def _read_records(path: Path) -> list[JsonObject]:
    if not path.exists():
        return []
    records: list[JsonObject] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as error:
            raise DecisionLogError(f"malformed decision log line {line_number}: {error.msg}") from error
        if not isinstance(parsed, dict):
            raise DecisionLogError(f"decision log line {line_number} must be a JSON object")
        records.append(dict(parsed))
    return records


def _entry_from_record(record: JsonObject, *, line_number: int) -> DecisionLogEntry:
    unknown_keys = set(record) - _ALLOWED_RECORD_KEYS
    if unknown_keys:
        raise DecisionLogError(f"decision log line {line_number} has unknown fields: {', '.join(sorted(unknown_keys))}")
    return DecisionLogEntry(
        action=_required_text(record, "action", line_number),
        actor=_required_text(record, "actor", line_number),
        at=_required_text(record, "at", line_number),
        extra=_required_object(record, "extra", line_number),
        prev_entry_sha256=_required_text(record, "prev_entry_sha256", line_number),
        reason=_required_text(record, "reason", line_number),
        seq=_required_int(record, "seq", line_number),
        sig=_required_text(record, "sig", line_number),
        submission_id=_required_text(record, "submission_id", line_number),
    )


def _payload(entry: DecisionLogEntry) -> JsonObject:
    return {
        "action": entry.action,
        "actor": entry.actor,
        "at": entry.at,
        "extra": entry.extra,
        "prev_entry_sha256": entry.prev_entry_sha256,
        "reason": entry.reason,
        "seq": entry.seq,
        "submission_id": entry.submission_id,
    }


def _last_record_hash(records: list[JsonObject]) -> str:
    if not records:
        return GENESIS_PREV_SHA256
    return sha256_bytes(canonical_json_bytes(records[-1]))


def _next_seq(records: list[JsonObject]) -> int:
    if not records:
        return 1
    return _entry_from_record(records[-1], line_number=len(records)).seq + 1


def _required_text(record: JsonObject, key: str, line_number: int) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise DecisionLogError(f"decision log line {line_number} field {key} must be a non-empty string")
    return value


def _required_int(record: JsonObject, key: str, line_number: int) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise DecisionLogError(f"decision log line {line_number} field {key} must be an integer")
    return value


def _required_object(record: JsonObject, key: str, line_number: int) -> JsonObject:
    value: JsonValue | None = record.get(key)
    if not isinstance(value, dict):
        raise DecisionLogError(f"decision log line {line_number} field {key} must be an object")
    return dict(value)
