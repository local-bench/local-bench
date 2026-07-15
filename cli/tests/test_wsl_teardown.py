from __future__ import annotations

import shutil
import signal
from pathlib import Path

import pytest

from localbench.scoring.agentic_exec.wsl_teardown import (
    LinuxProcfs,
    TeardownError,
    terminate_linux_worker,
)


def test_linux_teardown_refuses_reused_worker_pid_before_signalling(tmp_path: Path) -> None:
    procfs = _fixture_procfs(tmp_path)
    token = "worker-token"
    _write_process(
        tmp_path,
        pid=101,
        process_group_id=101,
        session_id=101,
        start_time_ticks=1000,
        token=token,
    )
    pin = procfs.capture(101, token=token)
    _write_process(
        tmp_path,
        pid=101,
        process_group_id=101,
        session_id=101,
        start_time_ticks=2000,
        token=token,
    )
    signals: list[tuple[int, int]] = []

    with pytest.raises(TeardownError, match="start time changed"):
        terminate_linux_worker(
            pin,
            token=token,
            procfs=procfs,
            signal_group=lambda process_group_id, signum: signals.append(
                (process_group_id, signum),
            ),
            timeout_s=0.0,
        )

    assert signals == []


def test_linux_teardown_kills_owned_groups_and_proves_they_are_empty(tmp_path: Path) -> None:
    procfs = _fixture_procfs(tmp_path)
    token = "worker-token"
    _write_process(
        tmp_path,
        pid=91,
        process_group_id=91,
        session_id=1,
        start_time_ticks=900,
        token=token,
        executable="/usr/bin/setsid",
        commandline=(
            "/usr/bin/setsid\0--wait\0/opt/localbench/venv/bin/python\0-m\0"
            "localbench.scoring.agentic_exec.wsl_worker\0"
        ),
    )
    _write_process(
        tmp_path,
        pid=101,
        process_group_id=101,
        session_id=101,
        start_time_ticks=1000,
        token=token,
    )
    _write_process(
        tmp_path,
        pid=102,
        process_group_id=101,
        session_id=101,
        start_time_ticks=1001,
        token=None,
    )
    _write_process(
        tmp_path,
        pid=201,
        process_group_id=201,
        session_id=201,
        start_time_ticks=2000,
        token=token,
        executable="/opt/localbench/venv/bin/env_host",
        commandline="python\0-m\0localbench.scoring.agentic_exec.env_host\0",
    )
    pin = procfs.capture(101, token=token)
    assert procfs.find_worker(token=token) == pin
    signals: list[tuple[int, int]] = []

    def signal_group(process_group_id: int, signum: int) -> None:
        signals.append((process_group_id, signum))
        for process in procfs.processes():
            if process.process_group_id == process_group_id:
                shutil.rmtree(tmp_path / str(process.pid))

    terminate_linux_worker(
        pin,
        token=token,
        procfs=procfs,
        signal_group=signal_group,
        timeout_s=0.1,
        poll_interval_s=0.0,
    )

    assert signals == [(101, signal.SIGTERM), (201, signal.SIGTERM)]
    assert procfs.owned_processes(pin, token=token) == []
    assert [process.pid for process in procfs.processes()] == [91]


def test_linux_teardown_reports_failed_group_signal(tmp_path: Path) -> None:
    procfs = _fixture_procfs(tmp_path)
    token = "worker-token"
    _write_process(
        tmp_path,
        pid=101,
        process_group_id=101,
        session_id=101,
        start_time_ticks=1000,
        token=token,
    )
    pin = procfs.capture(101, token=token)

    def fail_signal(_process_group_id: int, _signum: int) -> None:
        raise OSError("signal refused")

    with pytest.raises(TeardownError, match="signal refused"):
        terminate_linux_worker(
            pin,
            token=token,
            procfs=procfs,
            signal_group=fail_signal,
            timeout_s=0.0,
        )


def _fixture_procfs(root: Path) -> LinuxProcfs:
    return LinuxProcfs(
        root=root,
        read_executable=lambda path: path.read_text(encoding="utf-8"),
    )


def _write_process(
    root: Path,
    *,
    pid: int,
    process_group_id: int,
    session_id: int,
    start_time_ticks: int,
    token: str | None,
    executable: str = "/opt/localbench/venv/bin/python",
    commandline: str = "python\0-m\0localbench.scoring.agentic_exec.wsl_worker\0",
) -> None:
    process_root = root / str(pid)
    process_root.mkdir(parents=True, exist_ok=True)
    stat_fields = [
        "S",
        "1",
        str(process_group_id),
        str(session_id),
        *("0" for _ in range(15)),
        str(start_time_ticks),
    ]
    (process_root / "stat").write_text(
        f"{pid} (worker) {' '.join(stat_fields)}\n",
        encoding="utf-8",
    )
    (process_root / "exe").write_text(executable, encoding="utf-8")
    (process_root / "cmdline").write_bytes(commandline.encode())
    environment = b"APPWORLD_ROOT=/home/lbworker/appworld\0"
    if token is not None:
        environment += f"LOCALBENCH_WORKER_TOKEN={token}\0".encode()
    (process_root / "environ").write_bytes(environment)
