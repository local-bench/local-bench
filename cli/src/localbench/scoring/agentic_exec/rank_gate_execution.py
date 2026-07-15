from __future__ import annotations

import hashlib
from collections.abc import Callable

from localbench.scoring.agentic_exec.loop_types import FailureClass, TaskRunResult
from localbench.scoring.agentic_exec.rank_gate import (
    ContractSemantics,
)
from localbench.scoring.agentic_exec.sandbox import WorkerSetupError
from localbench.scoring.agentic_exec.task_journal import (
    SleepDuringTaskError,
    TaskAttemptKey,
    TaskJournal,
)
from localbench.scoring.agentic_exec.wsl_proxy import WslTransportError
from localbench.submissions.canon import canonical_json_hash

RunAttempt = Callable[[], TaskRunResult]


def execute_v4_task(
    task_id: str,
    *,
    run_index: int,
    journal: TaskJournal,
    semantics: ContractSemantics,
    run_attempt: RunAttempt,
) -> TaskRunResult | None:
    prior_failures = journal.failed_attempts(task_id, run_index)
    if any(
        record.payload.get("teardown_state") == "uncertain"
        for record in prior_failures
    ):
        return None
    if prior_failures and (
        prior_failures[-1].payload.get("failure_class")
        not in semantics.retryable_failure_classes
    ):
        return None
    next_attempt = journal.next_attempt_number(task_id, run_index)
    maximum_attempt = semantics.whole_task_retry_count + 1
    if next_attempt > maximum_attempt:
        return None
    for _ in range(maximum_attempt - next_attempt + 1):
        key = TaskAttemptKey(
            task_id,
            run_index,
            journal.next_attempt_number(task_id, run_index),
        )
        journal.append_attempt_started(
            key,
            contract_id=semantics.contract_id,
            identity_ref=journal.identity_ref,
        )
        try:
            result = run_attempt()
        except WslTransportError as error:
            teardown_state = "uncertain" if error.operation == "teardown" else "verified"
            _append_failed(
                journal,
                key,
                failure_class=FailureClass.INFRA_SANDBOX.value,
                evidence_ref=_exception_evidence_ref(error),
                teardown_state=teardown_state,
            )
            if teardown_state == "uncertain":
                return None
            if _may_retry(FailureClass.INFRA_SANDBOX.value, key, semantics):
                continue
            return None
        except WorkerSetupError as error:
            _append_failed(
                journal,
                key,
                failure_class=FailureClass.INFRA_SANDBOX.value,
                evidence_ref=_exception_evidence_ref(error),
                teardown_state="verified",
            )
            if _may_retry(FailureClass.INFRA_SANDBOX.value, key, semantics):
                continue
            return None
        except SleepDuringTaskError as error:
            _append_failed(
                journal,
                key,
                failure_class=FailureClass.INFRA_TIMEOUT.value,
                evidence_ref=_exception_evidence_ref(error),
                teardown_state="verified",
            )
            if _may_retry(FailureClass.INFRA_TIMEOUT.value, key, semantics):
                continue
            return None

        failure_class = (
            FailureClass.INFRA_SANDBOX.value
            if result.diagnostics.teardown_failure_count > 0
            else result.diagnostics.failure_class.value
        )
        if failure_class not in semantics.non_measurement_failure_classes:
            _append_committed(journal, key, result)
            return result

        _append_failed(
            journal,
            key,
            failure_class=failure_class,
            evidence_ref=_result_evidence_ref(result),
            teardown_state="verified",
        )
        if _may_retry(failure_class, key, semantics):
            continue
        return None
    raise AssertionError("bounded retry loop exhausted without a terminal decision")


def _may_retry(
    failure_class: str,
    key: TaskAttemptKey,
    semantics: ContractSemantics,
) -> bool:
    return (
        failure_class in semantics.retryable_failure_classes
        and key.attempt_number <= semantics.whole_task_retry_count
    )


def _append_failed(
    journal: TaskJournal,
    key: TaskAttemptKey,
    *,
    failure_class: str,
    evidence_ref: str,
    teardown_state: str,
) -> None:
    journal.append_attempt_failed(
        key,
        failure_class=failure_class,
        evidence_ref=evidence_ref,
        teardown_state=teardown_state,
    )

def _append_committed(
    journal: TaskJournal,
    key: TaskAttemptKey,
    result: TaskRunResult,
) -> None:
    journal.append_result_committed(
        key,
        result={
            "task_id": result.task_id,
            "success": result.success,
            "outcome": result.outcome.value,
            "collateral_damage": result.collateral_damage,
        },
        diagnostics=result.diagnostics.as_dict(),
        attestation=result.attestation,
    )


def _exception_evidence_ref(error: Exception) -> str:
    value = f"{type(error).__name__}:{error}"
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _result_evidence_ref(result: TaskRunResult) -> str:
    return f"sha256:{canonical_json_hash(result.diagnostics.as_dict())}"
