"""Protocol C benchmark entry point — the clean surface the GPU run will call.

This is the single function the (separate, GPU-gated) real-model benchmark invokes. It takes
factories so it stays decoupled from both the sandbox internals and any model SDK:

    run_appworld_c_benchmark(
        task_ids=[...],
        model_factory=lambda task_id: <ModelClient>,      # real chat client OR scripted agent
        sandbox_factory=lambda task_id: <context manager yielding a SandboxLike>,
        config=LoopConfig(),
    ) -> BenchmarkReport

For each task it opens a FRESH sandbox (a context manager, so the env-host + bwrap children
are torn down per task — matching the LOCKED "fresh per task" requirement), builds a fresh
model client, runs the Protocol C loop, and collects the per-task verdict + diagnostics.
Then it aggregates ASR + the diagnostic RATES that falsify the axis.

This module imports NO model SDK and NO bwrap; the real benchmark supplies those via the two
factories. A convenience ``appworld_sandbox_factory`` is provided for the real run, but it is
only *imported* lazily inside that helper so this module stays import-safe on every host.

The agentic axis is deliberately NOT registered in the scorer/board/registry here — this is a
weight-0 candidate entry point, callable on demand, with zero headline impact.
"""

from __future__ import annotations

import queue
import hashlib
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol, assert_never, runtime_checkable

from localbench.scoring.agentic_exec.loop_config import (
    TASK_FINALIZE_TEARDOWN_RESERVE_S,
    LoopConfig,
)
from localbench.scoring.agentic_exec.loop_types import (
    BenchmarkReport,
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
)
from localbench.scoring.agentic_exec.model_client import (
    ModelClient,
    ModelTransportError,
    ModelTransportTimeout,
)
from localbench.scoring.agentic_exec.protocol_c_loop import SandboxLike, run_task
from localbench.scoring.agentic_exec.task_journal import (
    RuntimeRevalidationError,
    SleepDuringTaskError,
    SleepWakeMonitor,
    TaskAttemptKey,
    TaskJournal,
)
from localbench.scoring.agentic_exec.task_journal_result import task_result_from_envelope

if TYPE_CHECKING:
    from localbench.scoring.agentic_exec.rank_gate import ContractSemantics

# A sandbox factory yields a context manager that, on __enter__, returns a live SandboxLike.
SandboxFactory = Callable[[str], AbstractContextManager[SandboxLike]]
ModelFactory = Callable[[str], ModelClient]


@dataclass(frozen=True, slots=True)
class _BenchmarkFactories:
    model: ModelFactory
    sandbox: SandboxFactory


@runtime_checkable
class _ForceKillable(Protocol):
    def force_kill(self) -> None:
        ...


@runtime_checkable
class _TaskDeadlineAware(Protocol):
    def set_task_deadline(self, deadline: float) -> None:
        ...


@runtime_checkable
class _Cancellable(Protocol):
    def cancel(self) -> None:
        ...


@runtime_checkable
class _TeardownDiagnostic(Protocol):
    @property
    def teardown_failure(self) -> str | None:
        ...


def run_appworld_c_benchmark(
    task_ids: list[str],
    model_factory: ModelFactory,
    sandbox_factory: SandboxFactory,
    config: LoopConfig | None = None,
    journal: TaskJournal | None = None,
    run_index: int = 1,
    sleep_wake_monitor: SleepWakeMonitor | None = None,
    runtime_revalidator: Callable[[], None] | None = None,
) -> BenchmarkReport:
    """Run Protocol C over ``task_ids``; return ASR + diagnostics aggregate.

    Tasks run sequentially (each owns a fresh sandbox process pair). A per-task harness error
    is captured as a ``HARNESS_ERROR`` row rather than aborting the whole run, so one bad task
    never sinks the batch.
    """
    # This is the execution choke point shared by every host-side producer of a
    # scored BenchmarkReport.  Keep the assertion before factory construction and
    # before the first task so direct callers cannot bypass the v3 packaging gate.
    from localbench.scoring.agentic_exec.execution_contract import assert_execution_contract

    assert_execution_contract()
    cfg = config or LoopConfig()
    factories = _BenchmarkFactories(model=model_factory, sandbox=sandbox_factory)
    from localbench.scoring.agentic_exec.rank_gate import (
        RankGatePolicy,
        resolve_contract_semantics,
    )

    semantics = resolve_contract_semantics()
    if semantics.rank_gate_policy is RankGatePolicy.NON_MEASUREMENT:
        if journal is None:
            from localbench.scoring.agentic_exec.rank_gate import ContractSemanticsError

            raise ContractSemanticsError(
                "journal",
                "v4+ ranked execution requires an append-only task journal",
            )
        return _run_v4_benchmark(
            tuple(task_ids),
            factories,
            cfg,
            journal=journal,
            run_index=run_index,
            sleep_wake_monitor=sleep_wake_monitor,
            runtime_revalidator=runtime_revalidator,
            semantics=semantics,
        )
    return _run_v3_benchmark(
        tuple(task_ids),
        factories,
        cfg,
        journal=journal,
        run_index=run_index,
        sleep_wake_monitor=sleep_wake_monitor,
        runtime_revalidator=runtime_revalidator,
    )


def _run_v3_benchmark(
    task_ids: tuple[str, ...],
    factories: _BenchmarkFactories,
    cfg: LoopConfig,
    *,
    journal: TaskJournal | None,
    run_index: int,
    sleep_wake_monitor: SleepWakeMonitor | None,
    runtime_revalidator: Callable[[], None] | None,
) -> BenchmarkReport:
    from localbench.scoring.agentic_exec.sandbox import WorkerSetupError

    results: list[TaskRunResult] = []
    for task_id in task_ids:
        if journal is None:
            results.append(_run_task_with_watchdog(task_id, factories, cfg))
            continue
        if journal.is_committed(task_id, run_index):
            results.append(
                task_result_from_envelope(journal.committed_envelope(task_id, run_index))
            )
            continue
        started = sleep_wake_monitor.task_started() if sleep_wake_monitor is not None else None
        if started is not None and started.slept_between_tasks:
            if runtime_revalidator is None:
                raise RuntimeRevalidationError(
                    "sleep detected between agentic tasks but no runtime revalidator is configured"
                )
            runtime_revalidator()
        key = TaskAttemptKey(task_id, run_index, journal.next_attempt_number(task_id, run_index))
        journal.append_attempt_started(
            key,
            contract_id=_execution_contract_id(),
            identity_ref=_journal_identity_ref(journal),
        )
        try:
            result = _run_task_with_watchdog(task_id, factories, cfg)
        except WorkerSetupError as error:
            journal.append_attempt_failed(
                key,
                failure_class=FailureClass.INFRA_SANDBOX.value,
                evidence_ref=_error_evidence_ref(error),
                teardown_state="failed",
            )
            raise
        if started is not None and sleep_wake_monitor is not None:
            if sleep_wake_monitor.task_finished(started):
                journal.append_attempt_failed(
                    key,
                    failure_class=FailureClass.INFRA_TIMEOUT.value,
                    evidence_ref="sleep-wake-divergence",
                    teardown_state="verified",
                )
                raise SleepDuringTaskError(
                    f"sleep detected during agentic task {task_id}; uncommitted attempt invalidated"
                )
        if result.diagnostics.teardown_failure_count > 0:
            journal.append_attempt_failed(
                key,
                failure_class=FailureClass.INFRA_SANDBOX.value,
                evidence_ref=hashlib.sha256(
                    str(result.diagnostics.teardown_failure_detail).encode("utf-8")
                ).hexdigest(),
                teardown_state="failed",
            )
            raise WorkerSetupError(
                result.diagnostics.teardown_failure_detail
                or "agentic sandbox teardown verification failed"
            )
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
        results.append(result)
    return aggregate(results)


def _run_v4_benchmark(
    task_ids: tuple[str, ...],
    factories: _BenchmarkFactories,
    cfg: LoopConfig,
    *,
    journal: TaskJournal,
    run_index: int,
    sleep_wake_monitor: SleepWakeMonitor | None,
    runtime_revalidator: Callable[[], None] | None,
    semantics: ContractSemantics,
) -> BenchmarkReport:
    from localbench.scoring.agentic_exec.rank_gate import evaluate_rank_gate
    from localbench.scoring.agentic_exec.rank_gate_execution import execute_v4_task

    results: list[TaskRunResult] = []
    for task_id in task_ids:
        if journal.is_committed(task_id, run_index):
            results.append(
                task_result_from_envelope(journal.committed_envelope(task_id, run_index))
            )
            continue

        def _attempt() -> TaskRunResult:
            started = (
                sleep_wake_monitor.task_started()
                if sleep_wake_monitor is not None
                else None
            )
            if started is not None and started.slept_between_tasks:
                if runtime_revalidator is None:
                    raise RuntimeRevalidationError(
                        "sleep detected between agentic tasks but no runtime revalidator "
                        "is configured"
                    )
                runtime_revalidator()
            result = _run_task_with_watchdog(task_id, factories, cfg)
            if (
                started is not None
                and sleep_wake_monitor is not None
                and sleep_wake_monitor.task_finished(started)
            ):
                raise SleepDuringTaskError(
                    f"sleep detected during agentic task {task_id}; "
                    "uncommitted attempt invalidated"
                )
            return result

        result = execute_v4_task(
            task_id,
            run_index=run_index,
            journal=journal,
            semantics=semantics,
            run_attempt=_attempt,
        )
        if result is not None:
            results.append(result)
    evaluate_rank_gate(journal, required_task_ids=task_ids, run_index=run_index)
    return aggregate(results)


def _execution_contract_id() -> str:
    from localbench.scoring.agentic_exec.contract_scope import active_execution_contract

    return active_execution_contract(None)[1]


def _journal_identity_ref(journal: TaskJournal) -> str:
    return journal.identity_ref


def _error_evidence_ref(error: Exception) -> str:
    value = f"{type(error).__name__}:{error}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run_task_with_watchdog(
    task_id: str,
    factories: _BenchmarkFactories,
    cfg: LoopConfig,
) -> TaskRunResult:
    result_slot: queue.Queue[TaskRunResult | Exception] = queue.Queue(maxsize=1)
    cleanup_slot: queue.Queue[SandboxLike] = queue.Queue(maxsize=1)
    model_slot: queue.Queue[ModelClient] = queue.Queue(maxsize=1)
    task_started = time.monotonic()
    transport_deadline = task_started + max(
        0.0,
        cfg.per_task_timeout_s - TASK_FINALIZE_TEARDOWN_RESERVE_S,
    )

    def _worker() -> None:
        try:
            with factories.sandbox(task_id) as sandbox:
                cleanup_slot.put(sandbox)
                model = factories.model(task_id)
                model_slot.put(model)
                if isinstance(model, _TaskDeadlineAware):
                    model.set_task_deadline(transport_deadline)
                task_result = run_task(sandbox, model, task_id, cfg)
            _record_teardown_diagnostic(task_result, sandbox)
            result_slot.put(task_result)
        except Exception as exc:  # noqa: BLE001 — isolate per-task setup/teardown failures.
            result_slot.put(exc)

    worker = threading.Thread(target=_worker, name=f"lb-task-{task_id}", daemon=True)
    worker.start()
    worker.join(cfg.per_task_timeout_s)
    if worker.is_alive():
        _cancel_model(_model_handle(model_slot))
        _force_kill_sandbox(_cleanup_handle(cleanup_slot))
        # Never advance while a timed-out generation is still using llama-server. The task-wide
        # transport deadline leaves teardown reserve, and cancel closes the active HTTP socket.
        worker.join()
        return _task_timeout_result(task_id, cfg.per_task_timeout_s)

    try:
        published = result_slot.get_nowait()
    except queue.Empty:
        return _harness_error_result(task_id, RuntimeError("task worker ended without a result"))

    match published:
        case TaskRunResult():
            return published
        case Exception():
            from localbench.scoring.agentic_exec.sandbox import WorkerSetupError  # noqa: PLC0415
            from localbench.scoring.agentic_exec.wsl_proxy import (  # noqa: PLC0415
                WslTransportError,
            )

            if isinstance(published, WorkerSetupError) or (
                isinstance(published, WslTransportError)
                and published.operation == "teardown"
            ):
                raise published
            return _harness_error_result(task_id, published)
        case unreachable:
            assert_never(unreachable)


def _cleanup_handle(cleanup_slot: queue.Queue[SandboxLike]) -> SandboxLike | None:
    try:
        return cleanup_slot.get_nowait()
    except queue.Empty:
        return None


def _model_handle(model_slot: queue.Queue[ModelClient]) -> ModelClient | None:
    try:
        return model_slot.get_nowait()
    except queue.Empty:
        return None


def _cancel_model(model: ModelClient | None) -> None:
    if isinstance(model, _Cancellable):
        model.cancel()


def _force_kill_sandbox(sandbox: SandboxLike | None) -> None:
    if isinstance(sandbox, _ForceKillable):
        sandbox.force_kill()


def _record_teardown_diagnostic(result: TaskRunResult, sandbox: SandboxLike) -> None:
    if not isinstance(sandbox, _TeardownDiagnostic) or sandbox.teardown_failure is None:
        return
    result.diagnostics.teardown_failure_count += 1
    result.diagnostics.teardown_failure_detail = sandbox.teardown_failure


def _task_timeout_result(task_id: str, timeout_s: float) -> TaskRunResult:
    from localbench.scoring.agentic_exec.sandbox import SandboxTimeoutError  # noqa: PLC0415

    return _harness_error_result(
        task_id,
        SandboxTimeoutError(f"task exceeded per-task watchdog ({timeout_s}s)"),
    )


def aggregate(results: list[TaskRunResult]) -> BenchmarkReport:
    """Compute ASR + diagnostic rates from per-task results (pure; unit-testable)."""
    n = len(results)
    succeeded = sum(1 for r in results if r.success)
    infra_timeout = _count_failure_class(results, FailureClass.INFRA_TIMEOUT)
    infra_sandbox = _count_failure_class(results, FailureClass.INFRA_SANDBOX)
    infra_failures = infra_timeout + infra_sandbox
    transport_failures = sum(r.diagnostics.transport_failure_count for r in results)
    transport_attempts = sum(r.diagnostics.transport_attempt_count for r in results)
    teardown_failures = sum(r.diagnostics.teardown_failure_count for r in results)
    tasks_with_infra = sum(
        1
        for result in results
        if result.diagnostics.failure_class
        in {FailureClass.INFRA_TIMEOUT, FailureClass.INFRA_SANDBOX}
        or result.diagnostics.transport_failure_count > 0
        or result.diagnostics.teardown_failure_count > 0
    )

    # Per-block / per-turn denominators for the rate diagnostics.
    total_turns = sum(r.diagnostics.turns_used for r in results)
    total_blocks = sum(r.diagnostics.blocks_run for r in results)
    total_format_failures = sum(r.diagnostics.format_failures for r in results)
    total_syntax = sum(r.diagnostics.syntax_errors for r in results)
    total_runtime = sum(r.diagnostics.runtime_errors for r in results)
    total_truncations = sum(r.diagnostics.observation_truncations for r in results)
    total_api_calls = sum(r.diagnostics.total_api_calls for r in results)
    total_output_tokens = sum(r.diagnostics.total_output_tokens for r in results)

    outcome_counts: dict[str, int] = {o.value: 0 for o in TaskOutcome}
    for r in results:
        outcome_counts[r.outcome.value] += 1

    tasks_with_docs = sum(1 for r in results if r.diagnostics.api_docs_uses > 0)
    tasks_with_collateral = sum(1 for r in results if r.collateral_damage)

    return BenchmarkReport(
        tasks_total=n,
        tasks_succeeded=succeeded,
        # TODO(C6): Exclude infra attempts as non-measurements before ranked ASR aggregation.
        agentic_success_rate=_safe_div(succeeded, n),
        asr_excluding_infra=_safe_div(succeeded, n - infra_failures),
        collateral_damage_rate=_safe_div(tasks_with_collateral, n),
        cap_exceeded_rate=_safe_div(outcome_counts[TaskOutcome.CAP_EXCEEDED.value], n),
        no_final_answer_rate=_safe_div(outcome_counts[TaskOutcome.NO_FINAL_ANSWER.value], n),
        harness_error_rate=_safe_div(outcome_counts[TaskOutcome.HARNESS_ERROR.value], n),
        infra_timeout_rate=_safe_div(infra_timeout, n),
        infra_sandbox_rate=_safe_div(infra_sandbox, n),
        infra_failure_rate=_safe_div(tasks_with_infra, n),
        transport_failure_count=transport_failures,
        transport_attempt_count=transport_attempts,
        transport_failure_rate=_safe_div(transport_failures, transport_attempts),
        teardown_failure_count=teardown_failures,
        teardown_failure_rate=_safe_div(teardown_failures, n),
        model_failure_rate=_safe_div(_count_failure_class(results, FailureClass.MODEL_FAILURE), n),
        model_no_progress_rate=_safe_div(
            _count_failure_class(results, FailureClass.MODEL_NO_PROGRESS),
            n,
        ),
        harness_error_subclass_rate=_safe_div(
            _count_failure_class(results, FailureClass.HARNESS_ERROR),
            n,
        ),
        format_failure_rate=_safe_div(total_format_failures, total_turns),
        syntax_error_rate=_safe_div(total_syntax, total_blocks),
        runtime_error_rate=_safe_div(total_runtime, total_blocks),
        observation_truncation_rate=_safe_div(total_truncations, total_blocks),
        api_docs_usage_rate=_safe_div(tasks_with_docs, n),
        mean_turns_used=_safe_div(total_turns, n),
        mean_blocks_run=_safe_div(total_blocks, n),
        mean_api_calls=_safe_div(total_api_calls, n),
        mean_output_tokens=_safe_div(total_output_tokens, n),
        outcome_counts=outcome_counts,
        results=results,
    )


def appworld_sandbox_factory(
    sandbox_config: object | None = None,
) -> SandboxFactory:
    """Real-run sandbox factory: ``task_id -> AppWorldSandbox(task_id)`` context manager.

    Imported lazily so this module stays import-safe where AppWorld/bwrap are absent. The GPU
    benchmark calls this to get the factory it hands to ``run_appworld_c_benchmark``. A custom
    ``SandboxConfig`` may be supplied (e.g. tighter timeouts); otherwise defaults are used.
    """
    from localbench.scoring.agentic_exec.sandbox import (  # noqa: PLC0415 — lazy by design.
        AppWorldSandbox,
        SandboxConfig,
    )

    cfg = sandbox_config if isinstance(sandbox_config, SandboxConfig) else None

    def _factory(task_id: str) -> AbstractContextManager[SandboxLike]:
        return AppWorldSandbox(
            task_id,
            cfg or SandboxConfig(experiment_name=f"lb_protocol_c_{task_id}"),
        )

    return _factory


def _harness_error_result(task_id: str, exc: Exception) -> TaskRunResult:
    failure_class = _classify_harness_exception(exc)
    diag = TaskDiagnostics(
        task_id=task_id,
        outcome=TaskOutcome.HARNESS_ERROR,
        success=False,
        collateral_damage=False,
        turns_used=0,
        blocks_run=0,
        format_failures=0,
        syntax_errors=0,
        runtime_errors=0,
        cap_exceeded=False,
        total_api_calls=0,
        api_docs_uses=0,
        observation_truncations=0,
        total_output_tokens=0,
        failure_class=failure_class,
        finalize_error=f"{type(exc).__name__}: {exc}",
        turns=[],
    )
    return TaskRunResult(
        task_id=task_id,
        success=False,
        outcome=TaskOutcome.HARNESS_ERROR,
        collateral_damage=False,
        diagnostics=diag,
    )


def _safe_div(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _count_failure_class(results: list[TaskRunResult], failure_class: FailureClass) -> int:
    return sum(1 for r in results if r.diagnostics.failure_class == failure_class)


def _classify_harness_exception(exc: Exception) -> FailureClass:
    from localbench.scoring.agentic_exec.sandbox import (  # noqa: PLC0415
        SandboxError,
        SandboxTimeoutError,
    )

    match exc:
        case ModelTransportTimeout():
            return FailureClass.INFRA_TIMEOUT
        case ModelTransportError():
            return FailureClass.INFRA_SANDBOX
        case SandboxTimeoutError():
            return FailureClass.INFRA_TIMEOUT
        case SandboxError():
            return FailureClass.INFRA_SANDBOX
        case _:
            return FailureClass.HARNESS_ERROR
