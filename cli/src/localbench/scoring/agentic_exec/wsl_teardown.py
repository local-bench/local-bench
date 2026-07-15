from __future__ import annotations

import os
import json
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

WORKER_TOKEN_ENV = "LOCALBENCH_WORKER_TOKEN"
_SIGKILL: Final[int] = int(getattr(signal, "SIGKILL", 9))


class TeardownError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessPin:
    pid: int
    process_group_id: int
    session_id: int
    start_time_ticks: int
    executable: str

    def as_json(self) -> dict[str, int | str]:
        return {
            "pid": self.pid,
            "process_group_id": self.process_group_id,
            "session_id": self.session_id,
            "start_time_ticks": self.start_time_ticks,
            "executable": self.executable,
        }

    @classmethod
    def from_json(cls, value: object) -> ProcessPin:
        if not isinstance(value, dict):
            raise TeardownError("worker process identity is not an object")
        try:
            pid = value["pid"]
            process_group_id = value["process_group_id"]
            session_id = value["session_id"]
            start_time_ticks = value["start_time_ticks"]
            executable = value["executable"]
        except KeyError as error:
            raise TeardownError(f"worker process identity is missing {error.args[0]}") from error
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or not isinstance(process_group_id, int)
            or isinstance(process_group_id, bool)
            or not isinstance(session_id, int)
            or isinstance(session_id, bool)
            or not isinstance(start_time_ticks, int)
            or isinstance(start_time_ticks, bool)
            or not isinstance(executable, str)
            or not executable
        ):
            raise TeardownError("worker process identity has invalid fields")
        return cls(
            pid=pid,
            process_group_id=process_group_id,
            session_id=session_id,
            start_time_ticks=start_time_ticks,
            executable=executable,
        )


class _ProcessTable(Protocol):
    def _read_process(self, pid: int) -> ProcessPin | None: ...

    def capture(self, pid: int, *, token: str | None = None) -> ProcessPin: ...

    def owned_processes(self, pin: ProcessPin, *, token: str) -> list[ProcessPin]: ...


@dataclass(frozen=True, slots=True)
class LinuxProcfs:
    root: Path = Path("/proc")
    read_executable: Callable[[Path], str] = field(default=os.readlink, repr=False)

    def capture(self, pid: int, *, token: str | None = None) -> ProcessPin:
        process = self._read_process(pid)
        if process is None:
            raise TeardownError(f"worker pid {pid} is not present")
        if token is not None and not self._has_token(pid, token):
            raise TeardownError(f"worker pid {pid} does not carry its spawn token")
        return process

    def processes(self) -> list[ProcessPin]:
        processes: list[ProcessPin] = []
        try:
            children = tuple(self.root.iterdir())
        except OSError as error:
            raise TeardownError(f"could not enumerate {self.root}: {error}") from error
        for child in children:
            if not child.name.isdigit():
                continue
            try:
                process = self._read_process(int(child.name))
            except TeardownError:
                continue
            if process is not None:
                processes.append(process)
        return sorted(processes, key=lambda process: process.pid)

    def owned_processes(self, pin: ProcessPin, *, token: str) -> list[ProcessPin]:
        return [
            process
            for process in self.processes()
            if (
                self._has_token(process.pid, token)
                and not self._is_session_launcher(process.pid)
            )
            or (
                process.process_group_id == pin.process_group_id
                and process.session_id == pin.session_id
            )
        ]

    def find_worker(self, *, token: str) -> ProcessPin:
        matches = [
            process
            for process in self.processes()
            if self._has_token(process.pid, token)
            and not self._is_session_launcher(process.pid)
            and process.pid == process.process_group_id == process.session_id
            and self._cmdline_contains(process.pid, b"localbench.scoring.agentic_exec.wsl_worker")
        ]
        if len(matches) != 1:
            raise TeardownError(
                f"expected one worker for spawn token, found {[process.pid for process in matches]}",
            )
        return matches[0]

    def _read_process(self, pid: int) -> ProcessPin | None:
        process_root = self.root / str(pid)
        try:
            stat = (process_root / "stat").read_text(encoding="utf-8")
            executable = self.read_executable(process_root / "exe")
            fields = stat[stat.rindex(")") + 2 :].split()
            return ProcessPin(
                pid=pid,
                process_group_id=int(fields[2]),
                session_id=int(fields[3]),
                start_time_ticks=int(fields[19]),
                executable=executable,
            )
        except (FileNotFoundError, ProcessLookupError):
            return None
        except (IndexError, OSError, UnicodeError, ValueError) as error:
            raise TeardownError(f"could not read process identity for pid {pid}: {error}") from error

    def _has_token(self, pid: int, token: str) -> bool:
        expected = f"{WORKER_TOKEN_ENV}={token}".encode()
        try:
            environment = (self.root / str(pid) / "environ").read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            return False
        except OSError as error:
            raise TeardownError(f"could not read process environment for pid {pid}: {error}") from error
        return expected in environment.split(b"\0")

    def _cmdline_contains(self, pid: int, expected: bytes) -> bool:
        return expected in self._cmdline(pid)

    def _is_session_launcher(self, pid: int) -> bool:
        commandline = self._cmdline(pid)
        return bool(commandline) and commandline[0].endswith(b"/setsid")

    def _cmdline(self, pid: int) -> list[bytes]:
        try:
            commandline = (self.root / str(pid) / "cmdline").read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            return False
        except OSError as error:
            raise TeardownError(f"could not read process command line for pid {pid}: {error}") from error
        return [field for field in commandline.split(b"\0") if field]


def terminate_linux_worker(
    pin: ProcessPin,
    *,
    token: str,
    procfs: _ProcessTable | None = None,
    signal_group: Callable[[int, int], None] | None = None,
    timeout_s: float = 5.0,
    poll_interval_s: float = 0.05,
) -> None:
    process_table = procfs or LinuxProcfs()
    group_signaller = signal_group or _kill_process_group
    live = process_table._read_process(pin.pid)
    if live is not None:
        _verify_worker_pin(process_table, pin, token=token)
    owned = process_table.owned_processes(pin, token=token)
    if not owned:
        return
    _signal_owned_groups(owned, signal.SIGTERM, signal_group=group_signaller)
    if _wait_until_empty(
        process_table,
        pin,
        token=token,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    ):
        return
    _verify_worker_not_reused(process_table, pin)
    remaining = process_table.owned_processes(pin, token=token)
    _signal_owned_groups(remaining, _SIGKILL, signal_group=group_signaller)
    if not _wait_until_empty(
        process_table,
        pin,
        token=token,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    ):
        remaining_pids = [process.pid for process in process_table.owned_processes(pin, token=token)]
        raise TeardownError(f"worker process groups did not terminate: {remaining_pids}")


def verify_linux_worker_terminated(
    pin: ProcessPin,
    *,
    token: str,
    procfs: _ProcessTable | None = None,
) -> None:
    remaining = (procfs or LinuxProcfs()).owned_processes(pin, token=token)
    if remaining:
        raise TeardownError(
            f"worker process groups remain after teardown: {[process.pid for process in remaining]}",
        )


def current_worker_process() -> tuple[str, ProcessPin] | None:
    token = os.environ.get(WORKER_TOKEN_ENV)
    if not token:
        return None
    return token, LinuxProcfs().capture(os.getpid(), token=token)


def _verify_worker_pin(procfs: _ProcessTable, pin: ProcessPin, *, token: str) -> None:
    live = procfs.capture(pin.pid, token=token)
    if live.start_time_ticks != pin.start_time_ticks:
        raise TeardownError(f"worker pid {pin.pid} start time changed; refusing to signal")
    if live.executable != pin.executable:
        raise TeardownError(f"worker pid {pin.pid} executable changed; refusing to signal")
    if (
        live.process_group_id != pin.process_group_id
        or live.session_id != pin.session_id
    ):
        raise TeardownError(f"worker pid {pin.pid} process group changed; refusing to signal")


def _verify_worker_not_reused(procfs: _ProcessTable, pin: ProcessPin) -> None:
    try:
        live = procfs.capture(pin.pid)
    except TeardownError as error:
        if "is not present" in str(error):
            return
        raise
    if live.start_time_ticks != pin.start_time_ticks or live.executable != pin.executable:
        raise TeardownError(f"worker pid {pin.pid} was reused; refusing to signal")


def _signal_owned_groups(
    processes: list[ProcessPin],
    signum: int,
    *,
    signal_group: Callable[[int, int], None],
) -> None:
    for process_group_id in sorted({process.process_group_id for process in processes}):
        try:
            signal_group(process_group_id, signum)
        except ProcessLookupError:
            continue
        except OSError as error:
            raise TeardownError(
                f"signal {signum} failed for process group {process_group_id}: {error}",
            ) from error


def _kill_process_group(process_group_id: int, signum: int) -> None:
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        raise OSError("process-group signalling is unavailable")
    killpg(process_group_id, signum)


def _wait_until_empty(
    procfs: _ProcessTable,
    pin: ProcessPin,
    *,
    token: str,
    timeout_s: float,
    poll_interval_s: float,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        if not procfs.owned_processes(pin, token=token):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_s)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        operation, token, pin = _parse_command(arguments)
        procfs = LinuxProcfs()
        if operation == "discover":
            result = procfs.find_worker(token=token).as_json()
        elif operation == "verify":
            assert pin is not None
            _verify_worker_pin(procfs, pin, token=token)
            result = pin.as_json()
        elif operation == "terminate":
            assert pin is not None
            terminate_linux_worker(pin, token=token, procfs=procfs)
            result = {"terminated": True}
        else:
            assert operation == "verify-terminated" and pin is not None
            verify_linux_worker_terminated(pin, token=token, procfs=procfs)
            result = {"terminated": True}
    except (TeardownError, ValueError) as error:
        sys.stderr.write(f"{error}\n")
        return 3
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


def _parse_command(arguments: list[str]) -> tuple[str, str, ProcessPin | None]:
    if len(arguments) == 2 and arguments[0] == "discover":
        return arguments[0], arguments[1], None
    if len(arguments) != 7 or arguments[0] not in {
        "verify",
        "terminate",
        "verify-terminated",
    }:
        raise ValueError(
            "usage: wsl_teardown discover TOKEN | "
            "(verify|terminate|verify-terminated) TOKEN PID PGID SID START_TIME EXECUTABLE",
        )
    return (
        arguments[0],
        arguments[1],
        ProcessPin(
            pid=int(arguments[2]),
            process_group_id=int(arguments[3]),
            session_id=int(arguments[4]),
            start_time_ticks=int(arguments[5]),
            executable=arguments[6],
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
