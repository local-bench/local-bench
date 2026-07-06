"""Typed contracts for the Protocol C agent loop + benchmark entry point.

Separated from the loop module so tests and the (future) benchmark client can import the
record shapes without pulling in the sandbox. All structures are JSON-serialisable via
:meth:`as_dict` so a run row can be written to disk by the GPU benchmark step.

Nothing here imports AppWorld, the sandbox, or a model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TaskOutcome(StrEnum):
    """Why a task ended. Exactly one is recorded per task.

    ``SUCCESS``/``FAILURE`` come from the AppWorld verdict after the model finalized.
    The remaining values are harness-level terminal reasons where no (or no usable) verdict
    was produced — each is a NORMAL, reported failure mode, not a crash.
    """

    SUCCESS = "success"                  # finalized + verdict.success is True
    FAILURE = "failure"                  # finalized + verdict.success is False
    CAP_EXCEEDED = "cap_exceeded"        # hit the turn cap before signalling a final answer
    NO_FINAL_ANSWER = "no_final_answer"  # model stopped/looped without ever finalizing
    HARNESS_ERROR = "harness_error"      # sandbox/model raised irrecoverably (rare; logged)


class FailureClass(StrEnum):
    """Additive subclass for separating infra noise from model behavior."""

    NONE = "none"
    INFRA_TIMEOUT = "infra_timeout"
    INFRA_SANDBOX = "infra_sandbox"
    MODEL_FAILURE = "model_failure"
    MODEL_NO_PROGRESS = "model_no_progress"
    HARNESS_ERROR = "harness_error"


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """One turn of the loop (one model call + at most one executed block)."""

    index: int                       # 1-based turn number
    finish_reason: str               # model finish_reason ("stop"/"length"/...)
    output_tokens: int               # completion tokens this turn (estimate if unknown)
    had_block: bool                  # a single code block was extracted and run
    format_error: str | None         # block_parser kind if the turn was a format failure
    syntax_error: bool               # the executed block raised SyntaxError
    runtime_error: bool              # the executed block raised a (non-syntax) error
    api_calls: int                   # apis.<app>.<api>(...) call expressions in the block
    api_docs_calls: int              # apis.api_docs.* call expressions in the block
    observation_truncated: bool      # the observation fed back was truncated to the cap
    is_final: bool                   # the model signalled a final answer this turn
    raw_response_text: str = ""      # unmodified assistant text for provenance/debugging
    error_detail: str | None = None  # client transport/parse cause when finish_reason="error"
    server_timings: dict[str, Any] | None = None


@dataclass(slots=True)
class TaskDiagnostics:
    """Per-task diagnostics — the axis-falsification signal from the LOCKED design.

    If AppWorld-C mostly tracks ``syntax_error``/``runtime_error`` it is a coding diagnostic,
    not an agentic axis; these counts make that visible. Rates are computed at aggregation
    time from these raw counts so they compose across tasks.
    """

    task_id: str
    outcome: TaskOutcome
    success: bool
    collateral_damage: bool
    turns_used: int
    blocks_run: int
    format_failures: int             # turns rejected by block_parser (0 / >1 / empty block)
    syntax_errors: int               # blocks that raised SyntaxError
    runtime_errors: int              # blocks that raised a non-syntax error
    cap_exceeded: bool
    total_api_calls: int             # summed apis.<app>.<api>(...) across run blocks
    api_docs_uses: int               # summed apis.api_docs.* across run blocks
    observation_truncations: int     # observations truncated to the char cap
    total_output_tokens: int         # summed completion tokens across turns
    finalize_error: str | None = None  # set if finalize itself errored (HARNESS_ERROR)
    # Additive direct-finalize provenance: verdict-channel descriptor + sha256 of the
    # orchestrator's read-back answer. None when the sandbox does not advertise one (mocks).
    finalization: dict[str, Any] | None = None
    turns: list[TurnRecord] = field(default_factory=list)
    failure_class: FailureClass = FailureClass.NONE

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        d["failure_class"] = self.failure_class.value
        return d


@dataclass(frozen=True, slots=True)
class TaskRunResult:
    """Per-task benchmark row: the verdict view + the full diagnostics."""

    task_id: str
    success: bool
    outcome: TaskOutcome
    collateral_damage: bool
    diagnostics: TaskDiagnostics
    attestation: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "task_id": self.task_id,
            "success": self.success,
            "outcome": self.outcome.value,
            "collateral_damage": self.collateral_damage,
            "diagnostics": self.diagnostics.as_dict(),
        }
        if self.attestation is not None:
            result["attestation"] = self.attestation
        return result


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate across a task set: ASR + the diagnostic RATES that falsify the axis."""

    tasks_total: int
    tasks_succeeded: int
    agentic_success_rate: float
    collateral_damage_rate: float
    cap_exceeded_rate: float
    no_final_answer_rate: float
    harness_error_rate: float
    format_failure_rate: float       # format failures per turn (over all turns)
    syntax_error_rate: float         # syntax errors per executed block
    runtime_error_rate: float        # runtime errors per executed block
    observation_truncation_rate: float  # truncations per executed block
    api_docs_usage_rate: float       # fraction of tasks that consulted api_docs at least once
    mean_turns_used: float
    mean_blocks_run: float
    mean_api_calls: float
    mean_output_tokens: float
    outcome_counts: dict[str, int]
    results: list[TaskRunResult]
    asr_excluding_infra: float = 0.0
    infra_timeout_rate: float = 0.0
    infra_sandbox_rate: float = 0.0
    model_failure_rate: float = 0.0
    model_no_progress_rate: float = 0.0
    harness_error_subclass_rate: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tasks_total": self.tasks_total,
            "tasks_succeeded": self.tasks_succeeded,
            "agentic_success_rate": self.agentic_success_rate,
            "asr_excluding_infra": self.asr_excluding_infra,
            "collateral_damage_rate": self.collateral_damage_rate,
            "cap_exceeded_rate": self.cap_exceeded_rate,
            "no_final_answer_rate": self.no_final_answer_rate,
            "harness_error_rate": self.harness_error_rate,
            "infra_timeout_rate": self.infra_timeout_rate,
            "infra_sandbox_rate": self.infra_sandbox_rate,
            "model_failure_rate": self.model_failure_rate,
            "model_no_progress_rate": self.model_no_progress_rate,
            "harness_error_subclass_rate": self.harness_error_subclass_rate,
            "format_failure_rate": self.format_failure_rate,
            "syntax_error_rate": self.syntax_error_rate,
            "runtime_error_rate": self.runtime_error_rate,
            "observation_truncation_rate": self.observation_truncation_rate,
            "api_docs_usage_rate": self.api_docs_usage_rate,
            "mean_turns_used": self.mean_turns_used,
            "mean_blocks_run": self.mean_blocks_run,
            "mean_api_calls": self.mean_api_calls,
            "mean_output_tokens": self.mean_output_tokens,
            "outcome_counts": dict(self.outcome_counts),
            "results": [r.as_dict() for r in self.results],
        }
