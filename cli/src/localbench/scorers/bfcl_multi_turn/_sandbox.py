from __future__ import annotations

import builtins
import os
import socket
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ConstrainedExecutionError(RuntimeError):
    pass


@contextmanager
def blocked_side_effects() -> Iterator[None]:
    original_open = builtins.open
    original_path_open = Path.open
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_subprocess = {
        "Popen": subprocess.Popen,
        "run": subprocess.run,
        "call": subprocess.call,
        "check_call": subprocess.check_call,
        "check_output": subprocess.check_output,
    }
    original_socket = socket.socket
    original_create_connection = socket.create_connection
    original_os = {"remove": os.remove, "unlink": os.unlink, "rmdir": os.rmdir}
    builtins.open = _blocked_open
    Path.open = _blocked_path_open
    Path.write_text = _blocked_path_write
    Path.write_bytes = _blocked_path_write
    subprocess.Popen = _blocked_subprocess
    subprocess.run = _blocked_subprocess
    subprocess.call = _blocked_subprocess
    subprocess.check_call = _blocked_subprocess
    subprocess.check_output = _blocked_subprocess
    socket.socket = _blocked_socket
    socket.create_connection = _blocked_socket
    os.remove = _blocked_os_write
    os.unlink = _blocked_os_write
    os.rmdir = _blocked_os_write
    try:
        yield
    finally:
        builtins.open = original_open
        Path.open = original_path_open
        Path.write_text = original_write_text
        Path.write_bytes = original_write_bytes
        subprocess.Popen = original_subprocess["Popen"]
        subprocess.run = original_subprocess["run"]
        subprocess.call = original_subprocess["call"]
        subprocess.check_call = original_subprocess["check_call"]
        subprocess.check_output = original_subprocess["check_output"]
        socket.socket = original_socket
        socket.create_connection = original_create_connection
        os.remove = original_os["remove"]
        os.unlink = original_os["unlink"]
        os.rmdir = original_os["rmdir"]


def _blocked_open(*_args: object, **_kwargs: object) -> object:
    raise ConstrainedExecutionError("filesystem access through open() is blocked")


def _blocked_path_open(*_args: object, **_kwargs: object) -> object:
    raise ConstrainedExecutionError("filesystem access through Path.open() is blocked")


def _blocked_path_write(*_args: object, **_kwargs: object) -> None:
    raise ConstrainedExecutionError("filesystem writes are blocked")


def _blocked_subprocess(*_args: object, **_kwargs: object) -> None:
    raise ConstrainedExecutionError("subprocess execution is blocked")


def _blocked_socket(*_args: object, **_kwargs: object) -> None:
    raise ConstrainedExecutionError("network access is blocked")


def _blocked_os_write(*_args: object, **_kwargs: object) -> None:
    raise ConstrainedExecutionError("filesystem writes are blocked")
