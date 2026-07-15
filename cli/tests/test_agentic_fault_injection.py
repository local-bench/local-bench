from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest

from agentic_contract_fixtures import write_test_signed_v4_contract
from localbench.scoring.agentic_exec import benchmark, execution_contract
from localbench.scoring.agentic_exec.benchmark import run_appworld_c_benchmark
from localbench.scoring.agentic_exec.contract_scope import execution_contract_scope
from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.loop_types import (
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
)
from localbench.scoring.agentic_exec.model_client import ModelTransportTimeout
from localbench.scoring.agentic_exec.sandbox import (
    SandboxError,
    WorkerSetupError,
)
from localbench.scoring.agentic_exec.task_journal import TaskJournal
from localbench.scoring.agentic_exec.wsl_proxy import (
    WslTransportError,
    WslTransportTimeoutError,
)
from scripts.build_contract_v4_payload import V4_CONTRACT_ID
from test_agentic_task_journal import _identity

_BOUNDARIES = (
    ("worker_startup", FailureClass.INFRA_SANDBOX),
    ("open", FailureClass.INFRA_SANDBOX),
    ("block_rpc", FailureClass.INFRA_TIMEOUT),
    ("model_transport", FailureClass.INFRA_TIMEOUT),
    ("finalize", FailureClass.INFRA_SANDBOX),
    ("close", FailureClass.INFRA_SANDBOX),
    ("teardown", FailureClass.INFRA_SANDBOX),
)


@pytest.mark.parametrize(("boundary", "failure_class"), _BOUNDARIES)
@pytest.mark.parametrize("contract_version", [3, 4])
def test_fault_injection_boundary_classification_evidence_retry_and_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    failure_class: FailureClass,
    contract_version: int,
) -> None:
    monkeypatch.setattr(execution_contract, "assert_execution_contract", lambda: "fixture")
    monkeypatch.setattr(execution_contract, "assert_verdict_mint_allowed", lambda _path=None: None)
    calls = 0

    def run_fault_then_success(*_args: object) -> TaskRunResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _inject_fault(boundary)
        return _result(FailureClass.NONE)

    monkeypatch.setattr(benchmark, "_run_task_with_watchdog", run_fault_then_success)
    journal_path = tmp_path / f"v{contract_version}-{boundary}.bin"
    contract_path = (
        write_test_signed_v4_contract(tmp_path, monkeypatch)
        if contract_version == 4
        else None
    )
    scope = (
        execution_contract_scope(contract_path, expected_contract_id=V4_CONTRACT_ID)
        if contract_path is not None
        else nullcontext()
    )

    with scope, TaskJournal.open(journal_path, _identity()) as journal:
        if contract_version == 3 and boundary in {"worker_startup", "close", "teardown"}:
            with pytest.raises((WorkerSetupError, WslTransportError)) as raised:
                run_appworld_c_benchmark(
                    ["task-a"],
                    lambda _task_id: None,
                    lambda _task_id: nullcontext(),
                    LoopConfig(),
                    journal,
                )
            assert benchmark._classify_harness_exception(raised.value) is failure_class
            report = None
        else:
            report = run_appworld_c_benchmark(
                ["task-a"],
                lambda _task_id: None,
                lambda _task_id: nullcontext(),
                LoopConfig(),
                journal,
            )
        records = journal.records
        gate = journal.gate_verdict(1)

    failed = [record for record in records if record.record_type == "attempt_failed"]
    if contract_version == 4:
        assert len(failed) == 1
        assert failed[0].payload["failure_class"] == failure_class.value
        assert str(failed[0].payload["evidence_ref"]).startswith("sha256:")
        if boundary == "teardown":
            assert calls == 1
            assert failed[0].payload["teardown_state"] == "uncertain"
            assert report is not None and report.tasks_total == 0
            assert gate is not None and gate["decision"] is False
        else:
            assert calls == 2
            assert failed[0].payload["teardown_state"] == "verified"
            assert report is not None and report.agentic_success_rate == 1.0
            assert gate is not None and gate["decision"] is True
        return

    assert calls == 1
    assert gate is None
    if boundary in {"worker_startup", "close"}:
        assert len(failed) == 1
        assert failed[0].payload["failure_class"] == failure_class.value
    elif boundary == "teardown":
        assert failed == []
    else:
        assert report is not None
        assert report.tasks_total == 1
        assert report.tasks_succeeded == 0
        assert report.agentic_success_rate == 0.0


def _inject_fault(boundary: str) -> TaskRunResult:
    if boundary == "worker_startup":
        raise WorkerSetupError("fault:worker-startup")
    if boundary == "open":
        return benchmark._harness_error_result(
            "task-a",
            WslTransportError(operation="open", detail="fault:open"),
        )
    if boundary == "block_rpc":
        return benchmark._harness_error_result(
            "task-a",
            WslTransportTimeoutError(operation="block", detail="fault:block-rpc"),
        )
    if boundary == "model_transport":
        return benchmark._harness_error_result(
            "task-a",
            ModelTransportTimeout("fault:model-transport"),
        )
    if boundary == "finalize":
        return benchmark._harness_error_result("task-a", SandboxError("fault:finalize"))
    if boundary == "close":
        result = _result(FailureClass.NONE)
        result.diagnostics.teardown_failure_count = 1
        result.diagnostics.teardown_failure_detail = "fault:close"
        return result
    if boundary == "teardown":
        raise WslTransportError(operation="teardown", detail="fault:teardown")
    raise AssertionError(f"unknown fault boundary: {boundary}")


def _result(failure_class: FailureClass) -> TaskRunResult:
    success = failure_class is FailureClass.NONE
    diagnostics = TaskDiagnostics(
        task_id="task-a",
        outcome=TaskOutcome.SUCCESS if success else TaskOutcome.HARNESS_ERROR,
        success=success,
        collateral_damage=False,
        turns_used=1,
        blocks_run=1,
        format_failures=0,
        syntax_errors=0,
        runtime_errors=0,
        cap_exceeded=False,
        total_api_calls=0,
        api_docs_uses=0,
        observation_truncations=0,
        total_output_tokens=1,
        failure_class=failure_class,
        turns=[],
    )
    return TaskRunResult(
        task_id="task-a",
        success=success,
        outcome=diagnostics.outcome,
        collateral_damage=False,
        diagnostics=diagnostics,
    )
