from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from localbench.scoring.agentic_exec import execution_contract
from localbench.scoring.agentic_exec import scripted_agent as sa
from localbench.scoring.agentic_exec.benchmark import run_appworld_c_benchmark
from localbench.scoring.agentic_exec.funnel import (
    Stage,
    SubsetSpec,
    run_stage,
    run_with_reruns,
)
from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.sandbox import WorkerSetupError
from localbench.scoring.agentic_exec.task_journal import (
    AgenticResumeIdentity,
    SleepDuringTaskError,
    SleepWakeMonitor,
    TaskJournal,
)
from test_appworld_protocol_c_units import FakeSandbox


@pytest.fixture(autouse=True)
def _passed_execution_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution_contract, "assert_execution_contract", lambda: "contract")
    monkeypatch.setattr(
        execution_contract,
        "assert_verdict_mint_allowed",
        lambda _path=None: None,
    )


def _identity() -> AgenticResumeIdentity:
    return AgenticResumeIdentity(
        agentic_runtime_identity_sha256="a" * 64,
        model_sha256="b" * 64,
        normalized_server_identity="c" * 64,
        host_loop_scorer_contract_digest="d" * 64,
        task_set_sha256="e" * 64,
        lane="bounded-final-v2",
        profile="generic_think_tags_8192_v1",
        sampling={
            "max_turns": 24,
            "max_output_tokens_per_turn": 3072,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 1234,
        },
        wsl_kernel_family="6.6-microsoft-standard-WSL2",
        gpu_architecture="NVIDIA RTX 4090",
        driver_runtime_family="driver=600.1;cuda=13.0;runtime=vllm/0.24.0",
    )


def _subset() -> SubsetSpec:
    return SubsetSpec(
        name="c0-scripted",
        split="dev",
        size=2,
        seed=20260624,
        task_ids=("fac291d_1", "50e1ac9_1"),
    )


def _sandbox(task_id: str, *, succeeds: bool = True) -> FakeSandbox:
    fixtures = {
        "fac291d_1": (
            5 if succeeds else -1,
            "How many unique songs are in my library across songs, albums and playlists?",
        ),
        "50e1ac9_1": (
            "Bravo, Delta, Alpha" if succeeds else "wrong",
            "What are the titles of the top 3 most played R&B songs in my library?",
        ),
    }
    gold, instruction = fixtures[task_id]
    return FakeSandbox(gold_answer=gold, instruction=instruction, supervisor_email="b@x.com")


def _factory(task_id: str) -> FakeSandbox:
    return _sandbox(task_id)


def test_verified_teardown_must_finish_before_result_commit_is_durable(
    tmp_path: Path,
) -> None:
    class TeardownFailure:
        def __enter__(self) -> FakeSandbox:
            self.sandbox = _factory("fac291d_1")
            return self.sandbox

        def __exit__(self, exc_type, exc, tb) -> None:
            raise WorkerSetupError("injected teardown verification failure")

    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        # Given: finalize succeeds but the sandbox teardown verification fails.
        with pytest.raises(WorkerSetupError, match="teardown verification"):
            # When: the benchmark attempts the task under journaling.
            run_appworld_c_benchmark(
                task_ids=["fac291d_1"],
                model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
                sandbox_factory=lambda _task_id: TeardownFailure(),
                config=LoopConfig(),
                journal=journal,
                run_index=1,
            )

        # Then: no accepted envelope precedes verified teardown.
        assert journal.committed_task_ids(1) == ()
        failed = [record for record in journal.records if record.record_type == "attempt_failed"]
        assert len(failed) == 1
        assert failed[0].payload["teardown_state"] == "failed"


def test_resume_never_reruns_committed_task_and_reruns_incomplete_task(
    tmp_path: Path,
) -> None:
    path = tmp_path / "agentic-task-journal.bin"
    first_models: list[str] = []

    def first_model(task_id: str) -> sa.ScriptedSolverAgent:
        first_models.append(task_id)
        return sa.ScriptedSolverAgent(task_id)

    def interrupted_factory(task_id: str):
        if task_id == "50e1ac9_1":
            raise WorkerSetupError("injected process-death boundary")
        return _factory(task_id)

    # Given: task one committed before task two became incomplete.
    with TaskJournal.open(path, _identity()) as journal:
        with pytest.raises(WorkerSetupError, match="process-death boundary"):
            run_appworld_c_benchmark(
                task_ids=list(_subset().task_ids),
                model_factory=first_model,
                sandbox_factory=interrupted_factory,
                config=LoopConfig(),
                journal=journal,
                run_index=1,
            )
        assert journal.committed_task_ids(1) == ("fac291d_1",)

    resumed_models: list[str] = []

    def resumed_model(task_id: str) -> sa.ScriptedSolverAgent:
        resumed_models.append(task_id)
        return sa.ScriptedSolverAgent(task_id)

    # When: the matching run resumes.
    with TaskJournal.open(path, _identity()) as journal:
        report = run_appworld_c_benchmark(
            task_ids=list(_subset().task_ids),
            model_factory=resumed_model,
            sandbox_factory=_factory,
            config=LoopConfig(),
            journal=journal,
            run_index=1,
        )
        resumed_envelope = journal.committed_envelope("50e1ac9_1", 1)
        assert resumed_envelope["attempt_number"] == 2

    # Then: the accepted task is reconstructed and only the incomplete task executes.
    assert first_models == ["fac291d_1"]
    assert resumed_models == ["50e1ac9_1"]
    assert [result.task_id for result in report.results] == list(_subset().task_ids)
    assert report.tasks_succeeded == 2


def test_sleep_during_task_invalidates_attempt_after_verified_teardown(
    tmp_path: Path,
) -> None:
    wall = iter((0.0, 1.0, 30.0))
    monotonic = iter((0.0, 1.0, 2.0))
    monitor = SleepWakeMonitor(
        wall_clock=lambda: next(wall),
        monotonic_clock=lambda: next(monotonic),
        threshold_seconds=5.0,
    )
    path = tmp_path / "agentic-task-journal.bin"

    # Given: wall time diverges from monotonic time while one task is executing.
    with TaskJournal.open(path, _identity()) as journal:
        # When / Then: the accepted result is invalidated and execution stops cleanly.
        with pytest.raises(SleepDuringTaskError):
            run_appworld_c_benchmark(
                task_ids=["fac291d_1"],
                model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
                sandbox_factory=_factory,
                config=LoopConfig(),
                journal=journal,
                run_index=1,
                sleep_wake_monitor=monitor,
            )
        assert journal.committed_task_ids(1) == ()
        failed = [record for record in journal.records if record.record_type == "attempt_failed"]
        assert failed[-1].payload["failure_class"] == "infra_timeout"
        assert failed[-1].payload["teardown_state"] == "verified"


def test_sleep_between_tasks_forces_runtime_revalidation_before_continue(
    tmp_path: Path,
) -> None:
    wall = iter((0.0, 1.0, 2.0, 30.0, 31.0))
    monotonic = iter((0.0, 1.0, 2.0, 3.0, 4.0))
    monitor = SleepWakeMonitor(
        wall_clock=lambda: next(wall),
        monotonic_clock=lambda: next(monotonic),
        threshold_seconds=5.0,
    )
    revalidations: list[str] = []
    path = tmp_path / "agentic-task-journal.bin"

    # Given: the host sleeps after task one has durably committed.
    with TaskJournal.open(path, _identity()) as journal:
        # When: execution reaches task two.
        report = run_appworld_c_benchmark(
            task_ids=list(_subset().task_ids),
            model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
            sandbox_factory=_factory,
            config=LoopConfig(),
            journal=journal,
            run_index=1,
            sleep_wake_monitor=monitor,
            runtime_revalidator=lambda: revalidations.append("revalidated"),
        )

        # Then: server/runtime validation runs before task two and both results commit.
        assert revalidations == ["revalidated"]
        assert journal.committed_task_ids(1) == _subset().task_ids
        assert report.tasks_succeeded == 2


def _varying_factory(*, logical_run_offset: int = 0) -> Callable[[str], FakeSandbox]:
    call_count = 0

    def factory(task_id: str) -> FakeSandbox:
        nonlocal call_count
        logical_run = logical_run_offset + (call_count // len(_subset().task_ids)) + 1
        call_count += 1
        return _sandbox(task_id, succeeds=logical_run != 2)

    return factory


def test_resumed_and_uninterrupted_scripted_campaigns_have_same_canonical_digest(
    tmp_path: Path,
) -> None:
    config = LoopConfig(max_output_tokens_per_turn=3072)
    control_dir = tmp_path / "control"
    resumed_dir = tmp_path / "resumed"

    # Given: an uninterrupted C0 scripted campaign whose run-two ASR triggers run three.
    control = run_with_reruns(
        label="c0-control",
        stage=Stage.SCORED,
        subset=_subset(),
        model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
        sandbox_factory=_varying_factory(),
        config=config,
        base_count=2,
        results_dir=control_dir,
        resume_identity=_identity(),
    )
    assert control.triggered_third_run is True

    # And: a matching campaign interrupted after its durable run-one boundary.
    journal_path = resumed_dir / "agentic-task-journal.bin"
    resumed_dir.mkdir(parents=True)
    with TaskJournal.open(journal_path, _identity()) as journal:
        run_stage(
            label="c0-resumed",
            stage=Stage.SCORED,
            subset=_subset(),
            model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
            sandbox_factory=_varying_factory(),
            config=config,
            run_index=1,
            results_dir=resumed_dir,
            journal=journal,
        )

    # When: it resumes and executes only logical runs two and three.
    resumed = run_with_reruns(
        label="c0-resumed",
        stage=Stage.SCORED,
        subset=_subset(),
        model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
        sandbox_factory=_varying_factory(logical_run_offset=1),
        config=config,
        base_count=2,
        results_dir=resumed_dir,
        resume_identity=_identity(),
    )

    # Then: accepted campaign results and the conditional-third decision are digest-identical.
    assert resumed.triggered_third_run is True
    assert resumed.canonical_result_digest == control.canonical_result_digest
    assert resumed.asr_series == control.asr_series


def test_stage_report_is_rebuilt_from_closed_journal_without_task_execution(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "stage"
    journal_path = results_dir / "agentic-task-journal.bin"
    model_calls: list[str] = []

    # Given: a closed journal and its derived end-of-stage report.
    results_dir.mkdir(parents=True)
    with TaskJournal.open(journal_path, _identity()) as journal:
        first = run_stage(
            label="c0-stage",
            stage=Stage.SCORED,
            subset=_subset(),
            model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
            sandbox_factory=_factory,
            config=LoopConfig(),
            run_index=1,
            results_dir=results_dir,
            journal=journal,
        )
    assert first.results_path is not None
    first_document = json.loads(Path(first.results_path).read_text(encoding="utf-8"))
    Path(first.results_path).unlink()

    # When: recovery recreates the missing summary.
    with TaskJournal.open(journal_path, _identity()) as journal:
        rebuilt = run_stage(
            label="c0-stage",
            stage=Stage.SCORED,
            subset=_subset(),
            model_factory=lambda task_id: model_calls.append(task_id),
            sandbox_factory=_factory,
            config=LoopConfig(),
            run_index=1,
            results_dir=results_dir,
            journal=journal,
        )

    # Then: no task reruns and the scoring/report payload is derivable from accepted envelopes.
    assert model_calls == []
    rebuilt_document = json.loads(Path(rebuilt.results_path or "").read_text(encoding="utf-8"))
    assert rebuilt_document["report"] == first_document["report"]
    assert rebuilt_document["canonical_result_digest"] == first_document["canonical_result_digest"]
