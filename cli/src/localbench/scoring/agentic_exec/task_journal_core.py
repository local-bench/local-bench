from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Final, Self

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.task_journal_format import append_frame, open_journal
from localbench.scoring.agentic_exec.task_journal_types import (
    KNOWN_RECORD_TYPES,
    AgenticResumeIdentity,
    JournalCorruptionError,
    JournalDurabilityError,
    JournalRecord,
    ResumeIdentityMismatchError,
    SCHEMA_ID,
    SCHEMA_VERSION,
)
from localbench.scoring.agentic_exec.task_journal_validation import (
    compare_resume_identity,
    validate_record,
)

_ZERO_DIGEST: Final = "0" * 64


class TaskJournalCore:
    schema_id: Final = SCHEMA_ID

    def __init__(self, path: Path, identity: AgenticResumeIdentity) -> None:
        opened = open_journal(path, identity.as_dict())
        self._path = path
        self._identity = identity
        self._handle = opened.handle
        self._lock = opened.lock
        self._closed = False
        self._frames = list(opened.frames)
        self._records: list[JournalRecord] = []
        try:
            compare_resume_identity(opened.header, identity)
            self._rebuild_records()
        except (JournalCorruptionError, ResumeIdentityMismatchError):
            self._handle.close()
            self._lock.close()
            raise

    @classmethod
    def open(cls, path: Path, identity: AgenticResumeIdentity) -> Self:
        return cls(path, identity)

    @property
    def records(self) -> tuple[JournalRecord, ...]:
        return tuple(self._records)

    @property
    def identity_ref(self) -> str:
        return self._identity.agentic_runtime_identity_sha256

    @property
    def rankable(self) -> bool:
        return all(record.record_type in KNOWN_RECORD_TYPES for record in self._records)

    @property
    def third_run_decision(self) -> JsonObject | None:
        decisions = [
            record.payload
            for record in self._records
            if record.record_type == "third_run_decision"
        ]
        return decisions[-1] if decisions else None

    def append_record(self, record_type: str, payload: JsonObject) -> JournalRecord:
        self._require_open()
        sequence = len(self._records) + 1
        previous = self._records[-1].payload_sha256 if self._records else _ZERO_DIGEST
        document: JsonObject = {
            "schema": SCHEMA_ID,
            "version": SCHEMA_VERSION,
            "sequence": sequence,
            "previous_sha256": previous,
            "record_type": record_type,
            "payload": payload,
        }
        candidate = JournalRecord(sequence, record_type, payload, "")
        validate_record(candidate, self._records)
        frame = append_frame(self._handle, self._path, document)
        record = JournalRecord(sequence, record_type, payload, frame.payload_sha256)
        self._frames.append(frame)
        self._records.append(record)
        return record

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._handle.close()
        finally:
            self._lock.close()
            self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise JournalDurabilityError("journal writer is closed")

    def _rebuild_records(self) -> None:
        for frame in self._frames:
            document = frame.document
            if document.get("schema") != SCHEMA_ID or document.get("version") != SCHEMA_VERSION:
                raise JournalCorruptionError("journal record schema/version is invalid")
            record_type = document.get("record_type")
            payload = document.get("payload")
            sequence = document.get("sequence")
            if not isinstance(record_type, str) or not isinstance(payload, dict):
                raise JournalCorruptionError("journal record type/payload is invalid")
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                raise JournalCorruptionError("journal record sequence is invalid")
            record = JournalRecord(sequence, record_type, payload, frame.payload_sha256)
            validate_record(record, self._records)
            self._records.append(record)
