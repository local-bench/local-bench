from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest

from agentic_contract_fixtures import write_test_signed_v4_contract
from localbench.scoring.agentic_exec import benchmark, execution_contract
from localbench.scoring.agentic_exec.benchmark import run_appworld_c_benchmark
from localbench.scoring.agentic_exec.contract_scope import execution_contract_scope
from localbench.scoring.agentic_exec.execution_contract import load_execution_contract
from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.loop_types import (
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
)
from localbench.scoring.agentic_exec.rank_gate import (
    ContractSemanticsError,
    RankGatePolicy,
    evaluate_rank_gate,
    resolve_contract_semantics,
)
from localbench.submissions.canon import canonical_json_hash
from scripts.build_contract_v4_payload import V4_CONTRACT_ID, build_v4_payload
from localbench.scoring.agentic_exec.task_journal import TaskAttemptKey, TaskJournal
from localbench.scoring.agentic_exec.task_journal_types import JOURNAL_READER_VERSION
from test_agentic_task_journal import _identity


def test_active_v3_contract_resolves_legacy_semantics() -> None:
    # Given / When: the production-signed v3 contract is the active contract.
    semantics = resolve_contract_semantics()

    # Then: C6 is inert and every legacy failure remains a scored zero.
    assert semantics.contract_version == 3
    assert semantics.whole_task_retry_count == 0
    assert semantics.retryable_failure_classes == frozenset()
    assert semantics.non_retryable_failure_classes == frozenset(
        {
            "cap_exceeded",
            "harness_error",
            "infra_sandbox",
            "infra_timeout",
            "model_failure",
            "model_no_progress",
            "no_final_answer",
        }
    )
    assert semantics.rank_gate_policy is RankGatePolicy.LEGACY_ZEROS_IN_DENOMINATOR
    assert semantics.non_measurement_failure_classes == frozenset()


def test_v2_journal_reader_understands_c6_gate_verdict(tmp_path: Path) -> None:
    # Given: a v1 append-only journal opened by the C6-aware reader.
    path = tmp_path / "agentic-task-journal.bin"

    # When: the C6 gate decision is appended with accepted-envelope evidence pointers.
    with TaskJournal.open(path, _identity()) as journal:
        record = journal.append_gate_verdict(
            run_index=1,
            decision=False,
            evidence={
                "accepted_result_records": [2],
                "unresolved_infra_records": [4],
                "uncertain_teardown_records": [],
            },
        )

        # Then: the new reader recognizes the record without changing the journal schema.
        assert JOURNAL_READER_VERSION == 2
        assert record.record_type == "c6_gate_verdict"
        assert journal.rankable is True
        assert journal.gate_verdict(1) == record.payload


def test_test_signed_v4_contract_resolves_builder_derived_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a non-production signature over the builder's own v4 payload output.
    path = write_test_signed_v4_contract(tmp_path, monkeypatch)

    # When: the contract is activated through the real context-local selector.
    with execution_contract_scope(path, expected_contract_id=V4_CONTRACT_ID):
        semantics = resolve_contract_semantics()

    # Then: the round-trip payload and every C6 policy field are contract-derived.
    assert load_execution_contract(path, expected_contract_id=V4_CONTRACT_ID)["payload"] == (
        build_v4_payload(gate_status="not-yet-passed")
    )
    assert semantics.contract_version == 4
    assert semantics.whole_task_retry_count == 2
    assert semantics.retryable_failure_classes == frozenset(
        {"infra_sandbox", "infra_timeout"}
    )
    assert semantics.non_measurement_failure_classes == frozenset(
        {"harness_error", "infra_sandbox", "infra_timeout"}
    )
    assert semantics.rank_gate_policy is RankGatePolicy.NON_MEASUREMENT


def test_v4_contract_missing_retry_count_is_a_typed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a builder-derived v4 payload whose required retry count is removed before signing.
    payload = build_v4_payload(gate_status="not-yet-passed")
    covered = payload["covered_behavior"]
    assert isinstance(covered, dict)
    transport = covered["transport_policy"]
    assert isinstance(transport, dict)
    transport.pop("whole_task_retry_count")
    payload["covered_behavior_sha256"] = canonical_json_hash(covered)
    path = write_test_signed_v4_contract(
        tmp_path,
        monkeypatch,
        payload=payload,
    )

    # When / Then: the active resolver fails closed without a default.
    with execution_contract_scope(path, expected_contract_id=V4_CONTRACT_ID):
        with pytest.raises(
            ContractSemanticsError,
            match="whole_task_retry_count",
        ):
            resolve_contract_semantics()


def test_test_signed_v4_contract_passes_runtime_source_and_packaging_assertions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = build_v4_payload(
        gate_status="passed-current-repo-harness-vs-appliance"
    )
    path = write_test_signed_v4_contract(
        tmp_path,
        monkeypatch,
        payload=payload,
    )

    with execution_contract_scope(path, expected_contract_id=V4_CONTRACT_ID):
        observed_digest = execution_contract.assert_execution_contract()

    assert observed_digest == canonical_json_hash(payload)


def test_v4_rank_gate_uses_accepted_envelopes_not_attempt_history_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: equivalent accepted task sets with different failed-attempt history and digests.
    contract_path = write_test_signed_v4_contract(tmp_path, monkeypatch)
    direct_path = tmp_path / "direct.bin"
    retried_path = tmp_path / "retried.bin"

    with execution_contract_scope(contract_path, expected_contract_id=V4_CONTRACT_ID):
        with TaskJournal.open(direct_path, _identity()) as direct:
            _append_measurement(direct, "task-a", attempt_number=1)
            direct_verdict = evaluate_rank_gate(
                direct,
                required_task_ids=("task-a",),
                run_index=1,
            )
            direct_digest = direct.canonical_result_digest()

        with TaskJournal.open(retried_path, _identity()) as retried:
            first = TaskAttemptKey("task-a", 1, 1)
            retried.append_attempt_started(
                first,
                contract_id=V4_CONTRACT_ID,
                identity_ref=retried.identity_ref,
            )
            retried.append_attempt_failed(
                first,
                failure_class="infra_timeout",
                evidence_ref="fault:model-transport",
                teardown_state="verified",
            )
            _append_measurement(retried, "task-a", attempt_number=2)
            retried_verdict = evaluate_rank_gate(
                retried,
                required_task_ids=("task-a",),
                run_index=1,
            )
            retried_digest = retried.canonical_result_digest()

    # Then: attempt-number/digest inequality cannot turn an accepted measurement into drift.
    assert direct_digest != retried_digest
    assert direct_verdict.decision is True
    assert retried_verdict.decision is True
    assert retried_verdict.unresolved_infra_task_ids == ()


def test_v4_gate_verdict_append_is_recovery_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_path = write_test_signed_v4_contract(tmp_path, monkeypatch)
    with execution_contract_scope(contract_path, expected_contract_id=V4_CONTRACT_ID):
        with TaskJournal.open(tmp_path / "idempotent.bin", _identity()) as journal:
            _append_measurement(journal, "task-a", attempt_number=1)
            first = evaluate_rank_gate(
                journal,
                required_task_ids=("task-a",),
                run_index=1,
            )
            second = evaluate_rank_gate(
                journal,
                required_task_ids=("task-a",),
                run_index=1,
            )

            assert first == second
            assert sum(
                record.record_type == "c6_gate_verdict" for record in journal.records
            ) == 1


@pytest.mark.parametrize(
    ("teardown_state", "accepted_after_failure"),
    [("verified", False), ("uncertain", True)],
)
def test_v4_rank_gate_blocks_unresolved_infra_or_uncertain_teardown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    teardown_state: str,
    accepted_after_failure: bool,
) -> None:
    # Given: either an exhausted infrastructure task or a retry after uncertain teardown.
    contract_path = write_test_signed_v4_contract(tmp_path, monkeypatch)
    journal_path = tmp_path / f"{teardown_state}.bin"

    with execution_contract_scope(contract_path, expected_contract_id=V4_CONTRACT_ID):
        with TaskJournal.open(journal_path, _identity()) as journal:
            first = TaskAttemptKey("task-a", 1, 1)
            journal.append_attempt_started(
                first,
                contract_id=V4_CONTRACT_ID,
                identity_ref=journal.identity_ref,
            )
            journal.append_attempt_failed(
                first,
                failure_class="infra_sandbox",
                evidence_ref=f"fault:{teardown_state}",
                teardown_state=teardown_state,
            )
            if accepted_after_failure:
                _append_measurement(journal, "task-a", attempt_number=2)

            # When: the C6 gate evaluates accepted envelopes and retained failure evidence.
            verdict = evaluate_rank_gate(
                journal,
                required_task_ids=("task-a",),
                run_index=1,
            )

            # Then: the run is unrankable and its blocking record sequence is retained.
            assert verdict.decision is False
            assert journal.gate_verdict(1) is not None
            if teardown_state == "uncertain":
                assert verdict.uncertain_teardown_record_sequences
            else:
                assert verdict.unresolved_infra_task_ids == ("task-a",)


@pytest.mark.parametrize(
    ("failure_classes", "expected_attempts", "expected_rankable"),
    [
        (
            (FailureClass.INFRA_TIMEOUT, FailureClass.INFRA_SANDBOX),
            3,
            True,
        ),
        (
            (
                FailureClass.INFRA_TIMEOUT,
                FailureClass.INFRA_SANDBOX,
                FailureClass.INFRA_TIMEOUT,
            ),
            3,
            False,
        ),
    ],
)
def test_v4_bounded_retry_retains_attempts_and_controls_rank_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_classes: tuple[FailureClass, ...],
    expected_attempts: int,
    expected_rankable: bool,
) -> None:
    # Given: builder-derived v4 semantics and retryable infra outcomes before success/exhaustion.
    contract_path = write_test_signed_v4_contract(tmp_path, monkeypatch)
    monkeypatch.setattr(execution_contract, "assert_execution_contract", lambda: "fixture")
    monkeypatch.setattr(execution_contract, "assert_verdict_mint_allowed", lambda _path=None: None)
    outcomes = [_task_result("task-a", failure_class) for failure_class in failure_classes]
    if len(failure_classes) < expected_attempts:
        outcomes.append(_task_result("task-a", FailureClass.NONE))
    calls = iter(outcomes)
    monkeypatch.setattr(
        benchmark,
        "_run_task_with_watchdog",
        lambda *_args: next(calls),
    )

    # When: one required task executes through the real benchmark/journal choke point.
    journal_path = tmp_path / "retry.bin"
    with execution_contract_scope(contract_path, expected_contract_id=V4_CONTRACT_ID):
        with TaskJournal.open(journal_path, _identity()) as journal:
            report = run_appworld_c_benchmark(
                task_ids=["task-a"],
                model_factory=lambda _task_id: None,
                sandbox_factory=lambda _task_id: nullcontext(),
                config=LoopConfig(),
                journal=journal,
                run_index=1,
            )
            records = journal.records
            gate = journal.gate_verdict(1)

    # Then: the contract bound is exact, every trigger is retained, and infra is not measured.
    started = [record for record in records if record.record_type == "attempt_started"]
    failed = [record for record in records if record.record_type == "attempt_failed"]
    assert [record.payload["attempt_number"] for record in started] == list(
        range(1, expected_attempts + 1)
    )
    assert [record.payload["failure_class"] for record in failed] == [
        failure_class.value for failure_class in failure_classes
    ]
    assert all(record.payload["evidence_ref"] for record in failed)
    assert gate is not None
    assert gate["decision"] is expected_rankable
    assert report.tasks_total == (1 if expected_rankable else 0)
    assert report.agentic_success_rate == (1.0 if expected_rankable else 0.0)
    assert "asr_excluding_infra" not in gate


def test_v3_infra_result_remains_one_scored_zero_without_retry_or_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: active v3 and an infra result followed by a value that must never be consumed.
    monkeypatch.setattr(execution_contract, "assert_execution_contract", lambda: "fixture")
    monkeypatch.setattr(execution_contract, "assert_verdict_mint_allowed", lambda _path=None: None)
    calls = iter(
        [
            _task_result("task-a", FailureClass.INFRA_TIMEOUT),
            _task_result("task-a", FailureClass.NONE),
        ]
    )
    consumed: list[TaskRunResult] = []

    def next_result(*_args: object) -> TaskRunResult:
        result = next(calls)
        consumed.append(result)
        return result

    monkeypatch.setattr(benchmark, "_run_task_with_watchdog", next_result)

    # When: the unchanged v3 benchmark path records the task.
    with TaskJournal.open(tmp_path / "v3.bin", _identity()) as journal:
        report = run_appworld_c_benchmark(
            task_ids=["task-a"],
            model_factory=lambda _task_id: None,
            sandbox_factory=lambda _task_id: nullcontext(),
            config=LoopConfig(),
            journal=journal,
            run_index=1,
        )

        # Then: v3 consumes one attempt, scores it as zero, and appends no C6 verdict.
        assert len(consumed) == 1
        assert report.tasks_total == 1
        assert report.tasks_succeeded == 0
        assert report.agentic_success_rate == 0.0
        assert journal.gate_verdict(1) is None


@pytest.mark.parametrize(
    ("failure_count", "teardown_state"),
    [(3, "verified"), (1, "uncertain")],
)
def test_v4_resume_never_advances_past_retry_bound_or_uncertain_teardown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_count: int,
    teardown_state: str,
) -> None:
    contract_path = write_test_signed_v4_contract(tmp_path, monkeypatch)
    monkeypatch.setattr(execution_contract, "assert_execution_contract", lambda: "fixture")
    monkeypatch.setattr(execution_contract, "assert_verdict_mint_allowed", lambda _path=None: None)
    monkeypatch.setattr(
        benchmark,
        "_run_task_with_watchdog",
        lambda *_args: pytest.fail("resume must not execute another attempt"),
    )

    with execution_contract_scope(contract_path, expected_contract_id=V4_CONTRACT_ID):
        with TaskJournal.open(tmp_path / f"resume-{teardown_state}.bin", _identity()) as journal:
            for attempt_number in range(1, failure_count + 1):
                key = TaskAttemptKey("task-a", 1, attempt_number)
                journal.append_attempt_started(
                    key,
                    contract_id=V4_CONTRACT_ID,
                    identity_ref=journal.identity_ref,
                )
                journal.append_attempt_failed(
                    key,
                    failure_class="infra_timeout",
                    evidence_ref=f"fault:{attempt_number}",
                    teardown_state=teardown_state,
                )

            report = run_appworld_c_benchmark(
                task_ids=["task-a"],
                model_factory=lambda _task_id: None,
                sandbox_factory=lambda _task_id: nullcontext(),
                config=LoopConfig(),
                journal=journal,
                run_index=1,
            )

            assert report.tasks_total == 0
            assert journal.gate_verdict(1) is not None


def _append_measurement(
    journal: TaskJournal,
    task_id: str,
    *,
    attempt_number: int,
) -> None:
    key = TaskAttemptKey(task_id, 1, attempt_number)
    journal.append_attempt_started(
        key,
        contract_id=V4_CONTRACT_ID,
        identity_ref=journal.identity_ref,
    )
    journal.append_result_committed(
        key,
        result={
            "task_id": task_id,
            "success": True,
            "outcome": "success",
            "collateral_damage": False,
        },
        diagnostics={},
        attestation=None,
    )


def _task_result(task_id: str, failure_class: FailureClass) -> TaskRunResult:
    success = failure_class is FailureClass.NONE
    outcome = TaskOutcome.SUCCESS if success else TaskOutcome.HARNESS_ERROR
    diagnostics = TaskDiagnostics(
        task_id=task_id,
        outcome=outcome,
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
        transport_attempt_count=1,
        turns=[],
    )
    return TaskRunResult(
        task_id=task_id,
        success=success,
        outcome=outcome,
        collateral_damage=False,
        diagnostics=diagnostics,
    )
