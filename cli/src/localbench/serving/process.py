from __future__ import annotations

import ctypes
import hashlib
import json
import os
import socket
import subprocess
from dataclasses import dataclass
from ctypes import wintypes
from ipaddress import ip_address
from pathlib import Path, PureWindowsPath
from typing import TextIO

from localbench.serving.job_object import WindowsJobObject
from localbench.serving.teardown import LiveProcessIdentity, RecordedProcessIdentity, terminate_recorded_pid


@dataclass(slots=True)
class LaunchedServer:
    process: subprocess.Popen[str]
    job: WindowsJobObject
    job_handle: int
    log_handle: TextIO
    log_start_byte: int
    identity: RecordedProcessIdentity

    def close_log(self) -> None:
        self.log_handle.close()


@dataclass(frozen=True, slots=True)
class JobController:
    job: WindowsJobObject
    job_handle: int

    def terminate_job(self) -> None:
        self.job.terminate(self.job_handle, exit_code=70)

    def close(self) -> None:
        self.job.close(self.job_handle)


def launch_llama_cpp(argv: list[str], *, cwd: Path, log_path: Path) -> LaunchedServer:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    try:
        log_start_byte = log_path.stat().st_size
    except FileNotFoundError:
        log_start_byte = 0
    job = WindowsJobObject()
    job_handle = job.create()
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        env=serve_env(),
    )
    identity: RecordedProcessIdentity | None = None
    try:
        process_handle = getattr(process, "_handle", None)
        if not isinstance(process_handle, int):
            raise RuntimeError("could not obtain Windows process handle for Job Object assignment")
        identity = failed_launch_identity(
            argv,
            process.pid,
            process_birth_token_from_handle(process_handle),
        )
        job.assign_process(job_handle, process_handle=process_handle)
    except BaseException:  # noqa: BROAD_EXCEPT_OK
        _cleanup_failed_launch(
            process,
            job,
            job_handle,
            log_handle,
            recorded=identity,
        )
        raise
    return LaunchedServer(
        process=process,
        job=job,
        job_handle=job_handle,
        log_handle=log_handle,
        log_start_byte=log_start_byte,
        identity=identity,
    )


def _cleanup_failed_launch(
    process: subprocess.Popen[str],
    job: WindowsJobObject,
    job_handle: int,
    log_handle: TextIO,
    *,
    recorded: RecordedProcessIdentity | None,
) -> None:
    if recorded is None:
        _terminate_known_process(process, process.pid)
    else:
        _terminate_failed_launch_process(process, recorded)
    try:
        job.close(job_handle)
    except OSError:
        return
    finally:
        log_handle.close()


def failed_launch_identity(
    argv: list[str],
    pid: int,
    process_birth_token: str,
) -> RecordedProcessIdentity:
    return RecordedProcessIdentity(
        pid=pid,
        executable_path=str(Path(argv[0]).resolve()),
        commandline_sha256=commandline_sha256(argv),
        process_birth_token=process_birth_token,
    )


def commandline_sha256(argv: list[str]) -> str:
    return hashlib.sha256(subprocess.list2cmdline(argv).encode("utf-8")).hexdigest()


def probe_process_identity(pid: int) -> LiveProcessIdentity | None:
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\"; "
        "if ($null -ne $p) { "
        "@{ ExecutablePath = $p.ExecutablePath; CommandLine = $p.CommandLine } | ConvertTo-Json -Compress "
        "}"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0 or completed.stdout.strip() == "":
        return None
    try:
        record = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    executable_path = record.get("ExecutablePath")
    commandline = record.get("CommandLine")
    if not isinstance(executable_path, str) or not isinstance(commandline, str):
        return None
    process_birth_token = probe_process_birth_token(pid)
    if process_birth_token is None:
        return None
    return LiveProcessIdentity(
        pid=pid,
        executable_path=executable_path,
        commandline_sha256=hashlib.sha256(commandline.encode("utf-8")).hexdigest(),
        process_birth_token=process_birth_token,
    )


def process_birth_token_from_handle(process_handle: int) -> str:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    return _process_birth_token_from_handle(kernel32, process_handle)


def probe_process_birth_token(pid: int) -> str | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    handle = open_process(0x1000, False, pid)
    if not handle:
        return None
    try:
        return _process_birth_token_from_handle(kernel32, handle)
    except OSError:
        return None
    finally:
        kernel32.CloseHandle(handle)


def _process_birth_token_from_handle(kernel32, process_handle: int) -> str:
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    get_times = kernel32.GetProcessTimes
    get_times.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    get_times.restype = wintypes.BOOL
    if not get_times(
        process_handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
    return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)


def probe_loopback_listener_owner_pid(host: str, port: int) -> int | None:
    try:
        address = ip_address(host)
    except ValueError:
        return None
    if not address.is_loopback or port <= 0 or port > 65535:
        return None
    script = (
        "$owners = @(Get-NetTCPConnection -State Listen "
        f"-LocalAddress '{address}' -LocalPort {port} -ErrorAction Stop | "
        "Select-Object -ExpandProperty OwningProcess -Unique); "
        "if ($owners.Count -eq 1) { $owners[0] }"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    owner = completed.stdout.strip()
    if completed.returncode != 0 or not owner.isdigit():
        return None
    return int(owner)


def process_identity_matches(
    recorded: RecordedProcessIdentity,
    live: LiveProcessIdentity | None,
) -> bool:
    if live is None or live.pid != recorded.pid:
        return False
    if (
        PureWindowsPath(live.executable_path).as_posix().casefold()
        != PureWindowsPath(recorded.executable_path).as_posix().casefold()
    ):
        return False
    return (
        live.commandline_sha256 == recorded.commandline_sha256
        and live.process_birth_token == recorded.process_birth_token
    )


def _terminate_failed_launch_process(process: subprocess.Popen[str], recorded: RecordedProcessIdentity) -> None:
    terminate_recorded_pid(
        recorded,
        live_probe=probe_process_identity,
        terminate_pid=lambda pid: _terminate_known_process(process, pid),
    )


def _terminate_known_process(process: subprocess.Popen[str], pid: int) -> None:
    if process.pid != pid:
        return
    try:
        process.terminate()
        process.wait(timeout=5.0)
    except (OSError, subprocess.TimeoutExpired):
        return


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    if not isinstance(port, int):
        raise RuntimeError("failed to allocate loopback port")
    return port


def serve_env() -> dict[str, str]:
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = "0"
    return env
