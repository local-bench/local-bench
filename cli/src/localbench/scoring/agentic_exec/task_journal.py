from __future__ import annotations

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.task_journal_core import TaskJournalCore
from localbench.scoring.agentic_exec.task_journal_digest import canonical_result_digest
from localbench.scoring.agentic_exec.task_journal_sleep import (
    RuntimeRevalidationError,
    SleepDuringTaskError,
    SleepWakeMonitor,
)
from localbench.scoring.agentic_exec.task_journal_types import (
    AgenticResumeIdentity,
    AgenticResumeSeed,
    JournalCorruptionError,
    JournalDurabilityError,
    JournalError,
    JournalLockedError,
    JournalRecord,
    ResumeIdentityMismatchError,
    TaskAttemptKey,
)
from localbench.scoring.agentic_exec.task_journal_validation import (
    committed_key,
    object_value,
    record_key,
)
from localbench.submissions.canon import canonical_json_hash


class TaskJournal(TaskJournalCore):
    def append_attempt_started(
        self,
        key: TaskAttemptKey,
        *,
        contract_id: str,
        identity_ref: str,
    ) -> JournalRecord:
        return self.append_record(
            "attempt_started",
            {
                **key.as_dict(),
                "contract_id": contract_id,
                "identity_ref": identity_ref,
            },
        )

    def append_attempt_failed(
        self,
        key: TaskAttemptKey,
        *,
        failure_class: str,
        evidence_ref: str,
        teardown_state: str,
    ) -> JournalRecord:
        return self.append_record(
            "attempt_failed",
            {
                **key.as_dict(),
                "failure_class": failure_class,
                "evidence_ref": evidence_ref,
                "teardown_state": teardown_state,
            },
        )

    def append_result_committed(
        self,
        key: TaskAttemptKey,
        *,
        result: JsonObject,
        diagnostics: JsonObject,
        attestation: JsonObject | None,
    ) -> JournalRecord:
        if self.is_committed(key.task_id, key.run_index):
            raise JournalCorruptionError(
                f"task-run already committed: {key.task_id} run {key.run_index}"
            )
        accepted: JsonObject = {
            "result": result,
            "diagnostics": diagnostics,
            "attestation": attestation,
            "identity": {
                "task_id": key.task_id,
                "run_index": key.run_index,
            },
            "attempt_number": key.attempt_number,
        }
        envelope = {**accepted, "payload_sha256": canonical_json_hash(accepted)}
        return self.append_record("attempt_result_committed", {"envelope": envelope})

    def append_run_boundary(self, run_index: int) -> JournalRecord:
        if run_index not in {1, 2, 3}:
            raise JournalCorruptionError("run boundary index must be one of 1, 2, 3")
        if self.run_closed(run_index):
            raise JournalCorruptionError(f"run {run_index} is already closed")
        return self.append_record("run_boundary", {"run_index": run_index, "closed": True})

    def append_third_run_decision(
        self,
        *,
        trigger_value: float,
        threshold_pp: float,
        decision: bool,
        evidence: JsonObject,
    ) -> JournalRecord:
        if self.third_run_decision is not None:
            raise JournalCorruptionError("conditional third-run decision is already committed")
        return self.append_record(
            "third_run_decision",
            {
                "trigger_value": trigger_value,
                "threshold_pp": threshold_pp,
                "decision": decision,
                "evidence": evidence,
            },
        )

    def committed_task_ids(self, run_index: int) -> tuple[str, ...]:
        return tuple(
            key.task_id
            for record in self._records
            if record.record_type == "attempt_result_committed"
            for key in [committed_key(record.payload)]
            if key.run_index == run_index
        )

    def pending_task_ids(
        self,
        run_index: int,
        task_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        committed = set(self.committed_task_ids(run_index))
        return tuple(task_id for task_id in task_ids if task_id not in committed)

    def is_committed(self, task_id: str, run_index: int) -> bool:
        return task_id in self.committed_task_ids(run_index)

    def next_attempt_number(self, task_id: str, run_index: int) -> int:
        attempts = [
            record_key(record.record_type, record.payload).attempt_number
            for record in self._records
            if record.record_type
            in {"attempt_started", "attempt_failed", "attempt_result_committed"}
            and record_key(record.record_type, record.payload).task_id == task_id
            and record_key(record.record_type, record.payload).run_index == run_index
        ]
        return max(attempts, default=0) + 1

    def run_closed(self, run_index: int) -> bool:
        return any(
            record.record_type == "run_boundary"
            and record.payload.get("run_index") == run_index
            and record.payload.get("closed") is True
            for record in self._records
        )

    def accepted_envelopes(self) -> list[JsonObject]:
        return [
            object_value(record.payload.get("envelope"), "committed envelope")
            for record in self._records
            if record.record_type == "attempt_result_committed"
        ]

    def committed_envelope(self, task_id: str, run_index: int) -> JsonObject:
        for envelope in self.accepted_envelopes():
            identity = object_value(envelope.get("identity"), "committed identity")
            if identity.get("task_id") == task_id and identity.get("run_index") == run_index:
                return envelope
        raise JournalCorruptionError(
            f"committed envelope is missing for {task_id} run {run_index}"
        )

    def canonical_result_digest(self) -> str:
        return canonical_result_digest(
            self.accepted_envelopes(),
            third_run_decision=self.third_run_decision,
        )


__all__ = [
    "AgenticResumeIdentity",
    "AgenticResumeSeed",
    "JournalCorruptionError",
    "JournalDurabilityError",
    "JournalError",
    "JournalLockedError",
    "JournalRecord",
    "ResumeIdentityMismatchError",
    "RuntimeRevalidationError",
    "SleepDuringTaskError",
    "SleepWakeMonitor",
    "TaskAttemptKey",
    "TaskJournal",
    "canonical_result_digest",
]
