from __future__ import annotations

import json
import errno
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

import pytest

from localbench.scoring.agentic_exec.task_journal import (
    AgenticResumeIdentity,
    JournalCorruptionError,
    JournalDurabilityError,
    JournalLockedError,
    ResumeIdentityMismatchError,
    TaskAttemptKey,
    TaskJournal,
    canonical_result_digest,
)
from localbench.submissions.canon import canonical_json_hash


def _identity() -> AgenticResumeIdentity:
    return AgenticResumeIdentity(
        agentic_runtime_identity_sha256="a" * 64,
        model_sha256="b" * 64,
        normalized_server_identity="c" * 64,
        host_loop_scorer_contract_digest="d" * 64,
        task_set_sha256="e" * 64,
        lane="bounded-final-v2",
        profile="generic_think_tags_8192_v1",
        sampling={"temperature": 0.0, "top_p": 1.0, "seed": 1234},
        wsl_kernel_family="6.6-microsoft-standard-WSL2",
        gpu_architecture="NVIDIA RTX 4090",
        driver_runtime_family="driver=600.1;cuda=13.0;runtime=vllm/0.24.0",
    )


def _key(task_id: str = "a30375d_1", run_index: int = 1) -> TaskAttemptKey:
    return TaskAttemptKey(task_id=task_id, run_index=run_index, attempt_number=1)


def _result(task_id: str = "a30375d_1") -> dict[str, object]:
    return {
        "task_id": task_id,
        "success": True,
        "outcome": "success",
        "collateral_damage": False,
    }


def _diagnostics(task_id: str = "a30375d_1") -> dict[str, object]:
    return {
        "task_id": task_id,
        "outcome": "success",
        "success": True,
        "turns_used": 1,
        "server_timings": {"latency_ms": 123.0},
        "artifact_path": "C:/private/run/result.json",
        "segment_id": "segment-9",
        "written_at": "2026-07-15T12:00:00Z",
    }


def _commit(journal: TaskJournal, key: TaskAttemptKey | None = None) -> None:
    selected = key or _key()
    journal.append_attempt_started(
        selected,
        contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v3",
        identity_ref="a" * 64,
    )
    journal.append_result_committed(
        selected,
        result=_result(selected.task_id),
        diagnostics=_diagnostics(selected.task_id),
        attestation={"schema": "localbench.agentic_attestation.v1", "digest": "f" * 64},
    )


def test_journal_round_trip_uses_framed_checksummed_append_only_records(
    tmp_path: Path,
) -> None:
    # Given: a new journal with the frozen resume identity.
    path = tmp_path / "agentic-task-journal.bin"

    # When: one attempt and accepted envelope are durably appended.
    with TaskJournal.open(path, _identity()) as journal:
        _commit(journal)

    # Then: recovery validates the schema, checksum chain, and committed identity.
    with TaskJournal.open(path, _identity()) as recovered:
        assert recovered.schema_id == "localbench.agentic_task_journal.v1"
        assert [record.record_type for record in recovered.records] == [
            "attempt_started",
            "attempt_result_committed",
        ]
        assert recovered.committed_task_ids(1) == ("a30375d_1",)
        assert recovered.rankable is True


def test_torn_final_record_is_truncated_and_task_can_rerun(tmp_path: Path) -> None:
    # Given: a journal whose final committed frame was torn by process death.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        journal.append_attempt_started(
            _key(),
            contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v3",
            identity_ref="a" * 64,
        )
        durable_prefix = path.stat().st_size
        journal.append_result_committed(
            _key(),
            result=_result(),
            diagnostics=_diagnostics(),
            attestation=None,
        )
    with path.open("r+b") as handle:
        handle.truncate(path.stat().st_size - 11)

    # When: recovery opens the journal.
    with TaskJournal.open(path, _identity()) as recovered:
        # Then: only the torn final frame is removed and the task remains pending.
        assert path.stat().st_size == durable_prefix
        assert recovered.committed_task_ids(1) == ()


@pytest.mark.parametrize(
    ("corruption", "message"),
    [("checksum", "non-final"), ("framing", "unexpected bytes")],
)
def test_corrupt_non_final_record_fails_closed_without_truncation(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    # Given: a checksum-corrupt first record followed by a complete final record.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        _commit(journal)
    original = bytearray(path.read_bytes())
    marker = original.index(b"attempt_started")
    corruption_offset = marker if corruption == "checksum" else original.rfind(b"JREC", 0, marker)
    original[corruption_offset] ^= 1
    path.write_bytes(original)
    corrupt_size = path.stat().st_size

    # When / Then: recovery refuses the run and preserves every byte for audit.
    with pytest.raises(JournalCorruptionError, match=message):
        TaskJournal.open(path, _identity())
    assert path.stat().st_size == corrupt_size


def test_unknown_record_is_preserved_and_marks_run_not_rankable(tmp_path: Path) -> None:
    # Given: a future C6 record type in an otherwise valid journal.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        journal.append_record("rank_gate_verdict_v2", {"rankable": True})

    # When: the C5 reader recovers it.
    with TaskJournal.open(path, _identity()) as recovered:
        # Then: the exact unknown payload remains auditable but cannot certify ranking.
        assert recovered.records[0].record_type == "rank_gate_verdict_v2"
        assert recovered.records[0].payload == {"rankable": True}
        assert recovered.rankable is False


@pytest.mark.parametrize(
    "component",
    [
        "agentic_runtime_identity_sha256",
        "model_sha256",
        "normalized_server_identity",
        "host_loop_scorer_contract_digest",
        "task_set_sha256",
        "lane",
        "profile",
        "sampling",
        "wsl_kernel_family",
        "gpu_architecture",
        "driver_runtime_family",
    ],
)
def test_resume_refuses_drift_in_every_identity_component(
    tmp_path: Path,
    component: str,
) -> None:
    # Given: a persisted run-start identity.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()):
        pass
    changed: object = {"temperature": 0.25} if component == "sampling" else f"changed-{component}"

    # When / Then: any one-component drift refuses resume and names its source.
    with pytest.raises(ResumeIdentityMismatchError, match=component) as caught:
        TaskJournal.open(path, replace(_identity(), **{component: changed}))
    assert "dev-vs-installed distribution-version drift" in str(caught.value)
    assert "CLI reinstall/upgrade" in str(caught.value)


def test_matching_identity_resumes_and_skips_exactly_committed_set(tmp_path: Path) -> None:
    # Given: two accepted tasks from a three-task run.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        _commit(journal, _key("a30375d_1"))
        _commit(journal, _key("ccf4b82_1"))

    # When: the matching identity resumes.
    with TaskJournal.open(path, _identity()) as recovered:
        pending = recovered.pending_task_ids(
            1,
            ("a30375d_1", "ccf4b82_1", "0de03ea_2"),
        )

    # Then: precisely the committed set is skipped.
    assert pending == ("0de03ea_2",)


def test_canonical_digest_ignores_time_latency_path_and_segment_metadata() -> None:
    # Given: two accepted-envelope views differing only in excluded metadata.
    first = [{"result": _result(), "diagnostics": _diagnostics(), "attestation": None}]
    changed = json.loads(json.dumps(first))
    changed[0]["diagnostics"]["server_timings"]["latency_ms"] = 9999
    changed[0]["diagnostics"]["artifact_path"] = "D:/other/private/path"
    changed[0]["diagnostics"]["segment_id"] = "segment-100"
    changed[0]["diagnostics"]["written_at"] = "2099-01-01T00:00:00Z"

    # When / Then: the canonical accepted-result digest is identical.
    assert canonical_result_digest(first, third_run_decision=None) == canonical_result_digest(
        changed,
        third_run_decision=None,
    )


def test_canonical_digest_includes_conditional_third_run_decision() -> None:
    # Given: identical accepted results but opposite conditional-third decisions.
    envelopes = [{"result": _result(), "diagnostics": _diagnostics(), "attestation": None}]

    # When: their canonical digests are computed.
    skipped = canonical_result_digest(
        envelopes,
        third_run_decision={"trigger_value": 0.0, "threshold_pp": 5.0, "decision": False},
    )
    triggered = canonical_result_digest(
        envelopes,
        third_run_decision={"trigger_value": 7.0, "threshold_pp": 5.0, "decision": True},
    )

    # Then: the decision is part of the accepted campaign result.
    assert skipped != triggered


def test_canonical_digest_does_not_reintroduce_excluded_metadata_through_payload_hash() -> None:
    # Given: valid committed envelopes whose excluded diagnostics and payload hashes differ.
    def envelope(diagnostics: dict[str, object]) -> dict[str, object]:
        accepted = {
            "result": _result(),
            "diagnostics": diagnostics,
            "attestation": None,
            "identity": {"task_id": "a30375d_1", "run_index": 1},
            "attempt_number": 1,
        }
        return {**accepted, "payload_sha256": canonical_json_hash(accepted)}

    first = envelope(_diagnostics())
    changed_diagnostics = _diagnostics()
    changed_diagnostics["written_at"] = "2099-01-01T00:00:00Z"
    changed_diagnostics["artifact_path"] = "D:/other/private/path"
    changed = envelope(changed_diagnostics)
    assert first["payload_sha256"] != changed["payload_sha256"]

    # When / Then: digest projection still ignores the excluded metadata transitively.
    assert canonical_result_digest([first], third_run_decision=None) == canonical_result_digest(
        [changed], third_run_decision=None
    )


def test_invalid_known_record_is_rejected_before_any_durable_append(tmp_path: Path) -> None:
    # Given: a healthy journal and an invalid contract failure class.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        size_before = path.stat().st_size

        # When / Then: schema validation fails before the append-only file changes.
        with pytest.raises(JournalCorruptionError, match="contract-covered"):
            journal.append_attempt_failed(
                _key(),
                failure_class="builder_invented_failure",
                evidence_ref="fixture",
                teardown_state="verified",
            )
        assert path.stat().st_size == size_before


def test_second_writer_fails_before_writing(tmp_path: Path) -> None:
    # Given: one live writer holding the exclusive lock.
    path = tmp_path / "agentic-task-journal.bin"
    first = TaskJournal.open(path, _identity())
    size_before = path.stat().st_size

    try:
        # When / Then: a second writer is rejected without changing the journal.
        with pytest.raises(JournalLockedError):
            TaskJournal.open(path, _identity())
        assert path.stat().st_size == size_before
    finally:
        first.close()


def test_stale_lock_recovers_only_after_original_process_instance_is_dead(
    tmp_path: Path,
) -> None:
    # Given: a real child process holding the lock for this run directory.
    path = tmp_path / "agentic-task-journal.bin"
    code = (
        "import json,sys,time;"
        "from pathlib import Path;"
        "from localbench.scoring.agentic_exec.task_journal import AgenticResumeIdentity,TaskJournal;"
        "identity=AgenticResumeIdentity(**json.loads(sys.argv[2]));"
        "journal=TaskJournal.open(Path(sys.argv[1]),identity);"
        "print('locked',flush=True);"
        "time.sleep(300)"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(path), json.dumps(_identity().as_dict())],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "locked"
    with pytest.raises(JournalLockedError):
        TaskJournal.open(path, _identity())

    # When: the exact PID/start-time process instance is killed.
    child.kill()
    child.wait(timeout=10)

    # Then: stale-lock proof permits the next writer to recover it.
    with TaskJournal.open(path, _identity()) as recovered:
        assert recovered.records == ()


class _FailingFile:
    def __init__(self, handle: BinaryIO, failure: str) -> None:
        self._handle = handle
        self._failure = failure
        self._write_calls = 0
        self._flush_calls = 0

    def write(self, data: bytes) -> int:
        self._write_calls += 1
        if self._failure == "short_write":
            if self._write_calls == 1:
                return self._handle.write(data[: max(1, len(data) // 2)])
            return 0
        if self._failure == "disk_full":
            self._handle.write(data[: max(1, len(data) // 2)])
            raise OSError(errno.ENOSPC, "injected disk full")
        return self._handle.write(data)

    def flush(self) -> None:
        self._flush_calls += 1
        if self._failure == "flush" and self._flush_calls == 1:
            raise OSError(errno.EIO, "injected flush failure")
        self._handle.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._handle, name)


@pytest.mark.parametrize("failure", ["short_write", "flush", "disk_full"])
def test_io_failure_cannot_yield_falsely_committed_task(
    tmp_path: Path,
    failure: str,
) -> None:
    # Given: a healthy journal whose next durable append will fail at an injected I/O boundary.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        journal.append_attempt_started(
            _key(),
            contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v3",
            identity_ref="a" * 64,
        )
        journal._handle = _FailingFile(journal._handle, failure)

        # When / Then: the append raises and in-memory state never accepts the task.
        with pytest.raises(JournalDurabilityError):
            journal.append_result_committed(
                _key(),
                result=_result(),
                diagnostics=_diagnostics(),
                attestation=None,
            )
        assert journal.committed_task_ids(1) == ()

    with TaskJournal.open(path, _identity()) as recovered:
        assert recovered.committed_task_ids(1) == ()


def test_commit_rejects_duplicate_accepted_result_for_task_run(tmp_path: Path) -> None:
    # Given: a task-run whose accepted result is already durable.
    path = tmp_path / "agentic-task-journal.bin"
    with TaskJournal.open(path, _identity()) as journal:
        _commit(journal)

        # When / Then: the append-only journal rejects a second logical commit.
        with pytest.raises(JournalCorruptionError, match="already committed"):
            journal.append_result_committed(
                _key(),
                result=_result(),
                diagnostics=_diagnostics(),
                attestation=None,
            )


@pytest.mark.parametrize(
    "phase",
    [
        "before_model_call",
        "mid_turn",
        "after_verdict",
        "during_commit",
        "after_commit",
        "between_run_1_run_2",
        "before_third_run_decision",
        "after_third_run_decision",
    ],
)
def test_process_death_crash_matrix_recovers_only_durable_state(
    tmp_path: Path,
    phase: str,
) -> None:
    # Given: a real child writer paused at one required crash-matrix boundary.
    path = tmp_path / "agentic-task-journal.bin"
    worker = Path(__file__).with_name("agentic_journal_process_worker.py")
    child = subprocess.Popen(
        [sys.executable, str(worker), str(path), phase, json.dumps(_identity().as_dict())],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "ready"

    # When: SIGKILL/TerminateProcess ends the writer with no cooperative close.
    child.kill()
    child.wait(timeout=10)

    # Then: recovery exposes only complete durable frames and permits incomplete work to rerun.
    with TaskJournal.open(path, _identity()) as recovered:
        committed_run_1 = recovered.committed_task_ids(1)
        if phase in {"after_commit", "between_run_1_run_2", "before_third_run_decision", "after_third_run_decision"}:
            assert committed_run_1 == ("a30375d_1",)
            assert recovered.accepted_envelopes()[0]["diagnostics"]["fixture_origin"].startswith(
                "DERIVED:"
            )
        else:
            assert committed_run_1 == ()
        assert recovered.run_closed(1) is (
            phase in {"between_run_1_run_2", "before_third_run_decision", "after_third_run_decision"}
        )
        assert recovered.run_closed(2) is (
            phase in {"before_third_run_decision", "after_third_run_decision"}
        )
        assert (recovered.third_run_decision is not None) is (
            phase == "after_third_run_decision"
        )
