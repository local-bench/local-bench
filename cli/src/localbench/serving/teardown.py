from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Protocol


class ProcessLike(Protocol):
    pid: int
    returncode: int | None

    def wait(self, timeout: float | None = None) -> int: ...


class TeardownController(Protocol):
    def terminate_job(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class TeardownEvidence:
    owned_process_tree: list[str]
    terminated: bool
    exit_code: int | None
    gpu_pids_after: list[int]
    teardown_uncertain: bool


@dataclass(frozen=True, slots=True)
class RecordedProcessIdentity:
    pid: int
    executable_path: str
    commandline_sha256: str


@dataclass(frozen=True, slots=True)
class LiveProcessIdentity:
    pid: int
    executable_path: str
    commandline_sha256: str


def teardown_owned_server(
    *,
    process: ProcessLike,
    controller: TeardownController,
    owned_pids: Sequence[int],
    gpu_pid_probe: Callable[[], list[int]] | None = None,
    poll_interval_seconds: float = 1.0,
    timeout_seconds: float = 30.0,
) -> TeardownEvidence:
    job_terminated = True
    try:
        controller.terminate_job()
    except OSError:
        job_terminated = False
    finally:
        controller.close()
    try:
        exit_code = process.wait(timeout=5.0)
    except (OSError, subprocess.TimeoutExpired):
        exit_code = process.returncode
    remaining = _wait_for_gpu_release(
        set(owned_pids),
        gpu_pid_probe or nvidia_smi_gpu_pids,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    terminated = job_terminated and remaining == []
    return TeardownEvidence(
        owned_process_tree=[str(pid) for pid in owned_pids],
        terminated=terminated,
        exit_code=exit_code,
        gpu_pids_after=remaining,
        teardown_uncertain=not terminated,
    )


def terminate_recorded_pid(
    recorded: RecordedProcessIdentity,
    *,
    live_probe: Callable[[int], LiveProcessIdentity | None],
    terminate_pid: Callable[[int], None],
) -> bool:
    live = live_probe(recorded.pid)
    if live is None or live.pid != recorded.pid:
        return False
    if _normalized_executable(live.executable_path) != _normalized_executable(recorded.executable_path):
        return False
    if live.commandline_sha256 != recorded.commandline_sha256:
        return False
    terminate_pid(recorded.pid)
    return True


def nvidia_smi_gpu_pids() -> list[int]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError("nvidia-smi GPU process probe unavailable") from exc
    if completed.returncode != 0:
        raise RuntimeError("nvidia-smi GPU process probe failed")
    pids: list[int] = []
    for line in completed.stdout.splitlines():
        first, _, _rest = line.partition(",")
        stripped = first.strip()
        if stripped.isdigit():
            pids.append(int(stripped))
    return pids


def _wait_for_gpu_release(
    owned: set[int],
    probe: Callable[[], list[int]],
    *,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> list[int]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            gpu_pids = probe()
        except RuntimeError:
            return sorted(owned)
        remaining = sorted(pid for pid in gpu_pids if pid in owned)
        if remaining == [] or time.monotonic() >= deadline:
            return remaining
        time.sleep(poll_interval_seconds)


def _normalized_executable(path: str) -> str:
    return PureWindowsPath(path).as_posix().casefold()
