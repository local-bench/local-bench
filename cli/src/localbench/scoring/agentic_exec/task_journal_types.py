from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from localbench._types import JsonObject, JsonValue

SCHEMA_ID: Final = "localbench.agentic_task_journal.v1"
SCHEMA_VERSION: Final = 1
JOURNAL_READER_VERSION: Final = 2
KNOWN_RECORD_TYPES: Final = frozenset(
    {
        "attempt_started",
        "attempt_failed",
        "attempt_result_committed",
        "run_boundary",
        "third_run_decision",
        "c6_gate_verdict",
    }
)


class JournalError(Exception):
    __slots__ = ("detail",)

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    def __str__(self) -> str:
        return self.detail


class JournalCorruptionError(JournalError):
    pass


class JournalDurabilityError(JournalError):
    pass


class JournalLockedError(JournalError):
    pass


class ResumeIdentityMismatchError(JournalError):
    __slots__ = ("component", "expected", "observed")

    def __init__(self, component: str, expected: JsonValue, observed: JsonValue) -> None:
        detail = (
            f"agentic resume refused: {component} drifted; expected {expected!r}, "
            f"observed {observed!r}. A dev-vs-installed distribution-version drift "
            "after a CLI reinstall/upgrade is a possible cause; these identities differ "
            "by design, so start a new run with the current installation."
        )
        super().__init__(detail)
        self.component = component
        self.expected = expected
        self.observed = observed


@dataclass(frozen=True, slots=True)
class TaskAttemptKey:
    task_id: str
    run_index: int
    attempt_number: int

    def __post_init__(self) -> None:
        if not self.task_id:
            raise JournalCorruptionError("journal task_id must be non-empty")
        if self.run_index not in {1, 2, 3}:
            raise JournalCorruptionError("journal run_index must be one of 1, 2, 3")
        if self.attempt_number < 1:
            raise JournalCorruptionError("journal attempt_number must be at least 1")

    def as_dict(self) -> JsonObject:
        return {
            "task_id": self.task_id,
            "run_index": self.run_index,
            "attempt_number": self.attempt_number,
        }


@dataclass(frozen=True, slots=True)
class AgenticResumeIdentity:
    agentic_runtime_identity_sha256: str
    model_sha256: str
    normalized_server_identity: str
    host_loop_scorer_contract_digest: str
    task_set_sha256: str
    lane: str
    profile: str
    sampling: JsonObject
    wsl_kernel_family: str
    gpu_architecture: str
    driver_runtime_family: str

    def as_dict(self) -> JsonObject:
        return {
            "agentic_runtime_identity_sha256": self.agentic_runtime_identity_sha256,
            "model_sha256": self.model_sha256,
            "normalized_server_identity": self.normalized_server_identity,
            "host_loop_scorer_contract_digest": self.host_loop_scorer_contract_digest,
            "task_set_sha256": self.task_set_sha256,
            "lane": self.lane,
            "profile": self.profile,
            "sampling": self.sampling,
            "wsl_kernel_family": self.wsl_kernel_family,
            "gpu_architecture": self.gpu_architecture,
            "driver_runtime_family": self.driver_runtime_family,
        }


@dataclass(frozen=True, slots=True)
class AgenticResumeSeed:
    agentic_runtime_identity_sha256: str
    model_sha256: str
    normalized_server_identity: str
    host_loop_scorer_contract_digest: str
    lane: str
    profile: str
    wsl_kernel_family: str
    gpu_architecture: str
    driver_runtime_family: str

    def build(
        self,
        *,
        task_set_sha256: str,
        sampling: JsonObject,
    ) -> AgenticResumeIdentity:
        return AgenticResumeIdentity(
            agentic_runtime_identity_sha256=self.agentic_runtime_identity_sha256,
            model_sha256=self.model_sha256,
            normalized_server_identity=self.normalized_server_identity,
            host_loop_scorer_contract_digest=self.host_loop_scorer_contract_digest,
            task_set_sha256=task_set_sha256,
            lane=self.lane,
            profile=self.profile,
            sampling=sampling,
            wsl_kernel_family=self.wsl_kernel_family,
            gpu_architecture=self.gpu_architecture,
            driver_runtime_family=self.driver_runtime_family,
        )


@dataclass(frozen=True, slots=True)
class JournalRecord:
    sequence: int
    record_type: str
    payload: JsonObject
    payload_sha256: str
