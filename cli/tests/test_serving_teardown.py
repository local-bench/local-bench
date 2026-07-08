from __future__ import annotations

from pathlib import Path

import pytest

from localbench.serving import process as process_mod
from localbench.serving.job_object import JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, WindowsJobObject
from localbench.serving.teardown import (
    LiveProcessIdentity,
    RecordedProcessIdentity,
    teardown_owned_server,
    terminate_recorded_pid,
)
from serving_helpers import FakeKernel32, FakeProcess, FakeTeardownController


def test_teardown_marks_uncertain_when_owned_gpu_pid_remains() -> None:
    # Given: a launched process whose PID still appears in nvidia-smi after termination.
    process = FakeProcess(pid=1234, returncode=0)
    controller = FakeTeardownController()

    # When: tearing down the owned server tree.
    evidence = teardown_owned_server(
        process=process,
        controller=controller,
        owned_pids=[1234],
        gpu_pid_probe=lambda: [1234],
        poll_interval_seconds=0,
        timeout_seconds=0,
    )

    # Then: teardown is marked uncertain and the residual PID is recorded.
    assert process.terminated is False
    assert controller.terminated_job is True
    assert evidence.terminated is False
    assert evidence.gpu_pids_after == [1234]
    assert evidence.teardown_uncertain is True


def test_recorded_pid_cleanup_requires_exe_and_commandline_fingerprint_match() -> None:
    recorded = RecordedProcessIdentity(
        pid=1234,
        executable_path="C:/tools/llama-server.exe",
        commandline_sha256="a" * 64,
    )
    killed: list[int] = []

    terminated = terminate_recorded_pid(
        recorded,
        live_probe=lambda pid: LiveProcessIdentity(
            pid=pid,
            executable_path="C:/tools/llama-server.exe",
            commandline_sha256="a" * 64,
        ),
        terminate_pid=killed.append,
    )

    assert terminated is True
    assert killed == [1234]


def test_recorded_pid_cleanup_refuses_pid_reuse_or_commandline_drift() -> None:
    recorded = RecordedProcessIdentity(
        pid=1234,
        executable_path="C:/tools/llama-server.exe",
        commandline_sha256="a" * 64,
    )
    killed: list[int] = []

    exe_drift = terminate_recorded_pid(
        recorded,
        live_probe=lambda pid: LiveProcessIdentity(
            pid=pid,
            executable_path="C:/Windows/System32/notepad.exe",
            commandline_sha256="a" * 64,
        ),
        terminate_pid=killed.append,
    )
    commandline_drift = terminate_recorded_pid(
        recorded,
        live_probe=lambda pid: LiveProcessIdentity(
            pid=pid,
            executable_path="C:/tools/llama-server.exe",
            commandline_sha256="b" * 64,
        ),
        terminate_pid=killed.append,
    )
    exited = terminate_recorded_pid(recorded, live_probe=lambda _pid: None, terminate_pid=killed.append)

    assert exe_drift is False
    assert commandline_drift is False
    assert exited is False
    assert killed == []


def test_job_object_wrapper_marshals_kill_on_close_and_assigns_process() -> None:
    # Given: a fake kernel32 facade.
    kernel32 = FakeKernel32()
    job = WindowsJobObject(kernel32=kernel32)

    # When: creating, assigning, terminating, and closing a job.
    handle = job.create()
    job.assign_process(handle, process_handle=222)
    job.terminate(handle, exit_code=70)
    job.close(handle)

    # Then: the Windows calls receive the expected handles and kill-on-close flag.
    assert handle == 111
    assert kernel32.info_class == 9
    assert kernel32.limit_flags == JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert kernel32.assigned == (111, 222)
    assert kernel32.terminated == (111, 70)
    assert kernel32.closed == [111]


def test_launch_llama_cpp_cleans_spawned_process_when_job_assignment_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a process is spawned, then Job Object assignment raises before launch returns.
    spawned = _SpawnedProcess()
    job = _RaisingAssignJob()
    log_path = tmp_path / "serve.log"
    log_handle = _FakeLogHandle()

    def fake_open(path: Path, mode: str = "r", encoding: str | None = None):
        if path == log_path:
            return log_handle
        return original_open(path, mode, encoding=encoding)

    def fake_popen(
        argv,
        *,
        cwd,
        stdout,
        stderr,
        text,
        env,
    ) -> _SpawnedProcess:
        assert stdout is log_handle
        return spawned

    original_open = Path.open
    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr(process_mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(process_mod, "WindowsJobObject", lambda: job)

    # When / Then: launch re-raises the assignment error after cleaning owned handles.
    with pytest.raises(OSError, match="AssignProcessToJobObject failed"):
        process_mod.launch_llama_cpp(["llama-server.exe"], cwd=tmp_path, log_path=log_path)
    assert spawned.terminated is True
    assert spawned.wait_timeout == 5.0
    assert job.closed == [111]
    assert log_handle.closed is True


class _SpawnedProcess:
    pid = 1234
    returncode: int | None = None
    _handle = 222

    def __init__(self) -> None:
        self.terminated = False
        self.wait_timeout: float | None = None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeout = timeout
        return 70


class _RaisingAssignJob:
    def __init__(self) -> None:
        self.closed: list[int] = []

    def create(self) -> int:
        return 111

    def assign_process(self, handle: int, *, process_handle: int) -> None:
        raise OSError("AssignProcessToJobObject failed")

    def close(self, handle: int) -> None:
        self.closed.append(handle)


class _FakeLogHandle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True
