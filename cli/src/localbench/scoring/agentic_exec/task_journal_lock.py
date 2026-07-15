from __future__ import annotations

import ctypes
import json
import os
import uuid
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from localbench.scoring.agentic_exec.task_journal_types import (
    JournalDurabilityError,
    JournalLockedError,
)
from localbench.submissions.canon import canonical_json_bytes


class _ProcessState(StrEnum):
    ALIVE = "alive"
    DEAD = "dead"
    UNKNOWN = "unknown"


class JournalLock:
    def __init__(self, path: Path, token: str) -> None:
        self._path = path
        self._token = token
        self._closed = False

    @classmethod
    def acquire(cls, path: Path) -> JournalLock:
        token = _current_process_start_token()
        document = canonical_json_bytes({"pid": os.getpid(), "process_start_token": token})
        for _attempt in range(3):
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                _recover_stale_lock(path)
                continue
            try:
                with os.fdopen(descriptor, "wb", closefd=True) as handle:
                    write_all(handle, document)
                    handle.flush()
                    os.fsync(handle.fileno())
                fsync_directory(path.parent)
                return cls(path, token)
            except OSError as error:
                path.unlink(missing_ok=True)
                raise JournalDurabilityError(f"could not create journal lock: {error}") from error
        raise JournalLockedError(f"journal writer lock is already held: {path}")

    def close(self) -> None:
        if self._closed:
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            self._closed = True
            return
        if (
            isinstance(raw, dict)
            and raw.get("pid") == os.getpid()
            and raw.get("process_start_token") == self._token
        ):
            self._path.unlink(missing_ok=True)
            fsync_directory(self._path.parent)
        self._closed = True


def write_all(handle: BinaryIO, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = handle.write(data[offset:])
        if written is None or written <= 0:
            raise OSError("file write made no progress")
        offset += written


def fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        return


def _recover_stale_lock(path: Path) -> None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JournalLockedError(f"journal lock owner cannot be proven dead: {error}") from error
    if not isinstance(raw, dict):
        raise JournalLockedError("journal lock owner cannot be proven dead: invalid lock object")
    pid = raw.get("pid")
    token = raw.get("process_start_token")
    if not isinstance(pid, int) or isinstance(pid, bool) or not isinstance(token, str):
        raise JournalLockedError("journal lock owner cannot be proven dead: invalid PID/start-time")
    state = _process_instance_state(pid, token)
    if state is _ProcessState.ALIVE:
        raise JournalLockedError(f"journal writer lock is held by live process {pid}")
    if state is _ProcessState.UNKNOWN:
        raise JournalLockedError(f"journal lock owner {pid} cannot be proven dead")
    quarantine = path.with_name(f"{path.name}.stale-{uuid.uuid4().hex}")
    try:
        os.replace(path, quarantine)
    except FileNotFoundError:
        return
    quarantine.unlink(missing_ok=True)
    fsync_directory(path.parent)


def _current_process_start_token() -> str:
    state, token = _read_process_start_token(os.getpid())
    if state is not _ProcessState.ALIVE or token is None:
        raise JournalLockedError("current process start-time cannot be established")
    return token


def _process_instance_state(pid: int, expected_token: str) -> _ProcessState:
    state, observed = _read_process_start_token(pid)
    if state is not _ProcessState.ALIVE:
        return state
    return _ProcessState.ALIVE if observed == expected_token else _ProcessState.DEAD


def _read_process_start_token(pid: int) -> tuple[_ProcessState, str | None]:
    if os.name == "nt":
        return _windows_process_start_token(pid)
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
    except FileNotFoundError:
        return _ProcessState.DEAD, None
    except OSError:
        return _ProcessState.UNKNOWN, None
    if len(fields) <= 21:
        return _ProcessState.UNKNOWN, None
    return _ProcessState.ALIVE, fields[21]


def _windows_process_start_token(pid: int) -> tuple[_ProcessState, str | None]:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    handle = open_process(0x1000, False, pid)
    if not handle:
        return (
            (_ProcessState.DEAD, None)
            if ctypes.get_last_error() == 87
            else (_ProcessState.UNKNOWN, None)
        )
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    try:
        exit_code = wintypes.DWORD()
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        get_exit_code.restype = wintypes.BOOL
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            return _ProcessState.UNKNOWN, None
        if exit_code.value != 259:
            return _ProcessState.DEAD, None
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
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return _ProcessState.UNKNOWN, None
        token = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return _ProcessState.ALIVE, str(token)
    finally:
        kernel32.CloseHandle(handle)
