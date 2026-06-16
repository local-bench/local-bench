from __future__ import annotations

import builtins
import os
import socket
import subprocess
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path


class ConstrainedExecutionError(RuntimeError):
    pass


@contextmanager
def blocked_side_effects(allowed_imports: Iterable[str] | None = None) -> Iterator[None]:
    allowed_roots = frozenset(allowed_imports) if allowed_imports is not None else None
    original_open = builtins.open
    original_import = builtins.__import__
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
    original_os = {
        "makedirs": os.makedirs,
        "mkdir": os.mkdir,
        "popen": os.popen,
        "remove": os.remove,
        "rename": os.rename,
        "replace": os.replace,
        "rmdir": os.rmdir,
        "system": os.system,
        "unlink": os.unlink,
    }
    builtins.open = _blocked_open
    if allowed_roots is not None:
        builtins.__import__ = _limited_import(original_import, allowed_roots)
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
    os.makedirs = _blocked_os_write
    os.mkdir = _blocked_os_write
    os.popen = _blocked_os_system
    os.remove = _blocked_os_write
    os.rename = _blocked_os_write
    os.replace = _blocked_os_write
    os.unlink = _blocked_os_write
    os.rmdir = _blocked_os_write
    os.system = _blocked_os_system
    try:
        yield
    finally:
        builtins.open = original_open
        builtins.__import__ = original_import
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
        os.makedirs = original_os["makedirs"]
        os.mkdir = original_os["mkdir"]
        os.popen = original_os["popen"]
        os.remove = original_os["remove"]
        os.rename = original_os["rename"]
        os.replace = original_os["replace"]
        os.unlink = original_os["unlink"]
        os.rmdir = original_os["rmdir"]
        os.system = original_os["system"]


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


def _blocked_os_system(*_args: object, **_kwargs: object) -> None:
    raise ConstrainedExecutionError("os command execution is blocked")


def _limited_import(
    original_import: Callable[
        [str, object | None, object | None, tuple[str, ...], int],
        object,
    ],
    allowed_roots: frozenset[str],
) -> Callable[[str, object | None, object | None, tuple[str, ...], int], object]:
    def import_module(
        name: str,
        globals_: object = None,
        locals_: object = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if level != 0:
            raise ConstrainedExecutionError("relative imports are blocked")
        root = name.split(".", 1)[0]
        if root not in allowed_roots:
            raise ConstrainedExecutionError(f"import is blocked: {root}")
        return original_import(name, globals_, locals_, fromlist, level)

    return import_module
