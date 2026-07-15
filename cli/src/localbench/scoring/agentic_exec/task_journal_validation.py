from __future__ import annotations

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.task_journal_types import (
    KNOWN_RECORD_TYPES,
    AgenticResumeIdentity,
    JournalCorruptionError,
    JournalRecord,
    ResumeIdentityMismatchError,
    TaskAttemptKey,
)
from localbench.submissions.canon import canonical_json_hash

_TEARDOWN_STATES = frozenset({"verified", "uncertain", "failed"})


def compare_resume_identity(header: JsonObject, identity: AgenticResumeIdentity) -> None:
    recorded = object_value(header.get("resume_identity"), "resume identity")
    for component, observed in identity.as_dict().items():
        expected = recorded.get(component)
        if expected != observed:
            raise ResumeIdentityMismatchError(component, expected, observed)


def validate_record(
    record: JournalRecord,
    existing_records: list[JournalRecord],
) -> None:
    if record.record_type not in KNOWN_RECORD_TYPES:
        return
    if record.record_type in {
        "attempt_started",
        "attempt_failed",
        "attempt_result_committed",
    }:
        key = record_key(record.record_type, record.payload)
        if _run_closed(existing_records, key.run_index):
            raise JournalCorruptionError(f"run {key.run_index} is already closed")
        if record.record_type == "attempt_started":
            string_value(record.payload.get("contract_id"), "contract_id")
            string_value(record.payload.get("identity_ref"), "identity_ref")
        if record.record_type == "attempt_result_committed":
            existing = {
                (committed_key(item.payload).task_id, committed_key(item.payload).run_index)
                for item in existing_records
                if item.record_type == "attempt_result_committed"
            }
            if (key.task_id, key.run_index) in existing:
                raise JournalCorruptionError(
                    f"task-run already committed: {key.task_id} run {key.run_index}"
                )
            validate_envelope(record.payload, key)
        if record.record_type == "attempt_failed":
            failure_class = record.payload.get("failure_class")
            if failure_class not in failure_classes():
                raise JournalCorruptionError(
                    f"attempt_failed failure_class is not contract-covered: {failure_class!r}"
                )
            string_value(record.payload.get("evidence_ref"), "evidence_ref")
            if record.payload.get("teardown_state") not in _TEARDOWN_STATES:
                raise JournalCorruptionError("attempt_failed teardown_state is invalid")
        return
    if record.record_type == "run_boundary":
        run_index = record.payload.get("run_index")
        if run_index not in {1, 2, 3} or record.payload.get("closed") is not True:
            raise JournalCorruptionError("run_boundary payload is invalid")
        if _run_closed(existing_records, int(run_index)):
            raise JournalCorruptionError(f"run {run_index} has duplicate boundaries")
        return
    if record.record_type == "third_run_decision":
        if any(item.record_type == "third_run_decision" for item in existing_records):
            raise JournalCorruptionError("conditional third-run decision is duplicated")
        if not isinstance(record.payload.get("decision"), bool):
            raise JournalCorruptionError("third_run_decision decision is invalid")
        number_value(record.payload.get("trigger_value"), "trigger_value")
        number_value(record.payload.get("threshold_pp"), "threshold_pp")
        object_value(record.payload.get("evidence"), "third-run evidence")


def record_key(record_type: str, payload: JsonObject) -> TaskAttemptKey:
    if record_type == "attempt_result_committed":
        return committed_key(payload)
    return key_from_object(payload)


def committed_key(payload: JsonObject) -> TaskAttemptKey:
    envelope = object_value(payload.get("envelope"), "committed envelope")
    identity = object_value(envelope.get("identity"), "committed identity")
    return TaskAttemptKey(
        task_id=string_value(identity.get("task_id"), "task_id"),
        run_index=integer_value(identity.get("run_index"), "run_index"),
        attempt_number=integer_value(envelope.get("attempt_number"), "attempt_number"),
    )


def key_from_object(payload: JsonObject) -> TaskAttemptKey:
    return TaskAttemptKey(
        task_id=string_value(payload.get("task_id"), "task_id"),
        run_index=integer_value(payload.get("run_index"), "run_index"),
        attempt_number=integer_value(payload.get("attempt_number"), "attempt_number"),
    )


def validate_envelope(payload: JsonObject, key: TaskAttemptKey) -> None:
    envelope = object_value(payload.get("envelope"), "committed envelope")
    expected = envelope.get("payload_sha256")
    accepted = {name: value for name, value in envelope.items() if name != "payload_sha256"}
    if expected != canonical_json_hash(accepted):
        raise JournalCorruptionError("committed envelope payload hash is invalid")
    result = object_value(envelope.get("result"), "committed result")
    if result.get("task_id") != key.task_id:
        raise JournalCorruptionError("committed result task_id differs from its identity key")
    object_value(envelope.get("diagnostics"), "committed diagnostics")
    attestation = envelope.get("attestation")
    if attestation is not None and not isinstance(attestation, dict):
        raise JournalCorruptionError("committed attestation is invalid")


def failure_classes() -> frozenset[str]:
    from localbench.scoring.agentic_exec.execution_contract import load_execution_contract

    contract = load_execution_contract()
    payload = object_value(contract.get("payload"), "execution contract payload")
    covered = object_value(payload.get("covered_behavior"), "covered behavior")
    mapping = object_value(covered.get("failure_to_score"), "failure_to_score")
    return frozenset(key for key in mapping if key not in {"success", "denominator"})


def object_value(value: JsonValue | None, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise JournalCorruptionError(f"journal {field} must be an object")
    return value


def string_value(value: JsonValue | None, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise JournalCorruptionError(f"journal {field} must be a non-empty string")
    return value


def integer_value(value: JsonValue | None, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise JournalCorruptionError(f"journal {field} must be an integer")
    return value


def number_value(value: JsonValue | None, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise JournalCorruptionError(f"journal {field} must be a number")
    return float(value)


def _run_closed(records: list[JournalRecord], run_index: int) -> bool:
    return any(
        record.record_type == "run_boundary"
        and record.payload.get("run_index") == run_index
        and record.payload.get("closed") is True
        for record in records
    )
