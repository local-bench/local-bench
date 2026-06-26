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

from contextlib import AbstractContextManager
from typing import Callable

from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.loop_types import (
    BenchmarkReport,
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
)
from localbench.scoring.agentic_exec.model_client import ModelClient
from localbench.scoring.agentic_exec.protocol_c_loop import SandboxLike, run_task

# A sandbox factory yields a context manager that, on __enter__, returns a live SandboxLike.
SandboxFactory = Callable[[str], AbstractContextManager[SandboxLike]]
ModelFactory = Callable[[str], ModelClient]


def run_appworld_c_benchmark(
    task_ids: list[str],
    model_factory: ModelFactory,
    sandbox_factory: SandboxFactory,
    config: LoopConfig | None = None,
) -> BenchmarkReport:
    """Run Protocol C over ``task_ids``; return ASR + diagnostics aggregate.

    Tasks run sequentially (each owns a fresh sandbox process pair). A per-task harness error
    is captured as a ``HARNESS_ERROR`` row rather than aborting the whole run, so one bad task
    never sinks the batch.
    """
    cfg = config or LoopConfig()
    results: list[TaskRunResult] = []
    for task_id in task_ids:
        try:
            with sandbox_factory(task_id) as sandbox:
                model = model_factory(task_id)
                results.append(run_task(sandbox, model, task_id, cfg))
        except Exception as exc:  # noqa: BLE001 — isolate per-task setup/teardown failures.
            results.append(_harness_error_result(task_id, exc))
    return aggregate(results)


def aggregate(results: list[TaskRunResult]) -> BenchmarkReport:
    """Compute ASR + diagnostic rates from per-task results (pure; unit-testable)."""
    n = len(results)
    succeeded = sum(1 for r in results if r.success)
    infra_timeout = _count_failure_class(results, FailureClass.INFRA_TIMEOUT)
    infra_sandbox = _count_failure_class(results, FailureClass.INFRA_SANDBOX)
    infra_failures = infra_timeout + infra_sandbox

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
        agentic_success_rate=_safe_div(succeeded, n),
        asr_excluding_infra=_safe_div(succeeded, n - infra_failures),
        collateral_damage_rate=_safe_div(tasks_with_collateral, n),
        cap_exceeded_rate=_safe_div(outcome_counts[TaskOutcome.CAP_EXCEEDED.value], n),
        no_final_answer_rate=_safe_div(outcome_counts[TaskOutcome.NO_FINAL_ANSWER.value], n),
        harness_error_rate=_safe_div(outcome_counts[TaskOutcome.HARNESS_ERROR.value], n),
        infra_timeout_rate=_safe_div(infra_timeout, n),
        infra_sandbox_rate=_safe_div(infra_sandbox, n),
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
        case SandboxTimeoutError():
            return FailureClass.INFRA_TIMEOUT
        case SandboxError():
            return FailureClass.INFRA_SANDBOX
        case _:
            return FailureClass.HARNESS_ERROR
