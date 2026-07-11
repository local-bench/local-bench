from __future__ import annotations

import importlib.metadata as metadata
import base64
import csv
import hashlib
import io
import json
import os
import platform
import signal
import subprocess
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final, TypeAlias

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.protocol_c_loop import SandboxLike
from localbench.scoring.agentic_exec.sandbox import (
    AppWorldSandbox,
    SandboxConfig,
    SandboxError,
    resolve_bwrap,
)
from localbench.scoring.agentic_exec.sandbox_protocol import _MAX_FRAME_BYTES
from localbench.scoring.agentic_exec.worker_identity import worker_implementation_identity

WorkerReply: TypeAlias = tuple[JsonObject, bool]
SandboxFactory: TypeAlias = Callable[[str], AbstractContextManager[SandboxLike]]

_PIN_ENV: Final[dict[str, str]] = {
    "PYTHONHASHSEED": "0",
    "TZ": "UTC",
    "LC_ALL": "C.UTF-8",
}
_APPWORLD_OFFICIAL_TREE_SHA256: Final = (
    "28113a7a68f5d5a4c5e9ea5bce4743633916e741430cfb96b56030660707308a"
)
_APPWORLD_WHEEL_RECORD_SHA256: Final = (
    "ea60f57d84a7dfcb067cf6399847ac34c1bda2f1fec54e11d9147c9c8ef13031"
)


@dataclass(frozen=True, slots=True)
class FrameTooLargeError(ValueError):
    size: int
    limit: int = _MAX_FRAME_BYTES

    def __str__(self) -> str:
        return f"worker frame too large: {self.size} bytes > {self.limit}"


@dataclass(frozen=True, slots=True)
class WorkerPreflightError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


class WorkerSession:
    def __init__(
        self,
        sandbox_factory: SandboxFactory | None = None,
    ) -> None:
        self._sandbox_factory = sandbox_factory or _default_sandbox_factory
        self._sandbox_context: AbstractContextManager[SandboxLike] | None = None
        self._sandbox: SandboxLike | None = None

    def open_task(self, task_id: str) -> None:
        if self._sandbox_context is not None:
            raise SandboxError("worker already has an open task")
        context = self._sandbox_factory(task_id)
        self._sandbox = context.__enter__()
        self._sandbox_context = context

    def run_block(self, code: str) -> JsonObject:
        sandbox = self._require_sandbox()
        obs = sandbox.run_block(code)
        return {
            "kind": "ok",
            "stdout": str(getattr(obs, "stdout", "") or ""),
            "error": _json_string_or_none(getattr(obs, "error", None)),
        }

    def finalize(self, answer: JsonValue) -> JsonObject:
        sandbox = self._require_sandbox()
        verdict = sandbox.finalize(answer)
        passes = tuple(getattr(verdict, "passes", ()) or ())
        failures = tuple(getattr(verdict, "failures", ()) or ())
        return {
            "kind": "ok",
            "verdict": {
                "success": bool(getattr(verdict, "success", False)),
                "collateral_damage": bool(getattr(verdict, "collateral_damage", False)),
                "passes": [str(item) for item in passes],
                "failures": [str(item) for item in failures],
                "num_passes": len(passes),
                "num_failures": len(failures),
            },
        }

    def close(self) -> None:
        context = self._sandbox_context
        self._sandbox = None
        self._sandbox_context = None
        if context is not None:
            context.__exit__(None, None, None)

    def _require_sandbox(self) -> SandboxLike:
        if self._sandbox is None:
            raise SandboxError("worker has no open task")
        return self._sandbox


def encode_worker_frame(message: JsonObject) -> bytes:
    payload = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    size = len(payload) + 1
    if size > _MAX_FRAME_BYTES:
        raise FrameTooLargeError(size=size)
    return payload + b"\n"


def decode_worker_frame(frame: bytes | str) -> JsonObject:
    raw = frame.encode("utf-8") if isinstance(frame, str) else frame
    if len(raw) > _MAX_FRAME_BYTES:
        raise FrameTooLargeError(size=len(raw))
    line = raw[:-1] if raw.endswith(b"\n") else raw
    decoded = json.loads(line.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("worker frame is not a JSON object")
    return decoded


def handle_worker_message(
    message: JsonValue,
    session: WorkerSession | None = None,
) -> WorkerReply:
    worker = session or WorkerSession()
    if not isinstance(message, dict):
        return _protocol_error("request must be a JSON object"), False
    op_value = message.get("op")
    if not isinstance(op_value, str):
        return _protocol_error("missing string op"), False

    match op_value:
        case "hello":
            return _ok_with_identity(), False
        case "open_task":
            task_id = message.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                return _protocol_error("open_task requires task_id"), False
            return _sandbox_call(lambda: _open_task(worker, task_id)), False
        case "run_block":
            code = message.get("code")
            if not isinstance(code, str):
                return _protocol_error("run_block requires code"), False
            return _sandbox_call(lambda: worker.run_block(code)), False
        case "finalize":
            return _sandbox_call(lambda: worker.finalize(message.get("answer"))), False
        case "close":
            return _sandbox_call(lambda: _close(worker)), True
        case "list_tasks":
            stage = message.get("stage", "scored")
            if stage != "scored":
                return _protocol_error("list_tasks only supports stage='scored'"), False
            max_items = message.get("max_items")
            if max_items is not None and (
                not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 1
            ):
                return _protocol_error("list_tasks max_items must be a positive integer"), False
            return _sandbox_call(lambda: _list_scored_tasks(max_items)), False
        case _:
            return _protocol_error(f"unknown op: {op_value}"), False


def collect_identity(appworld_root: str | None = None) -> JsonObject:
    _ensure_env_pins()
    root = appworld_root or os.environ.get("APPWORLD_ROOT", "")
    if not root:
        raise WorkerPreflightError("APPWORLD_ROOT is not set")
    root_posix = Path(root).as_posix()
    root_under_mnt = root_posix == "/mnt" or root_posix.startswith("/mnt/")
    if root_under_mnt:
        raise WorkerPreflightError(f"APPWORLD_ROOT must not be under /mnt: {root_posix}")
    bwrap = resolve_bwrap()
    if bwrap is None:
        raise WorkerPreflightError("bubblewrap (bwrap) not found")
    appworld_version = _package_version("appworld")
    if not appworld_version:
        raise WorkerPreflightError("appworld package not importable")
    os_release = _os_release()
    return {
        **worker_implementation_identity(),
        "wsl_kernel": platform.release(),
        "wsl_distro": os.environ.get("WSL_DISTRO_NAME", os_release.get("ID", "")),
        "wsl_os_release": os_release.get("PRETTY_NAME", ""),
        "python_version": platform.python_version(),
        "venv_path": sys.prefix,
        "venv_path_sha256": _text_sha256(sys.prefix),
        "worker_entrypoint": "localbench.scoring.agentic_exec.wsl_worker",
        "bwrap_path": bwrap,
        "bwrap_sha256": _file_sha256(bwrap),
        "bwrap_version": _command_output([bwrap, "--version"]),
        "appworld_root": root_posix,
        "appworld_root_path_sha256": _text_sha256(root_posix),
        "appworld_root_under_mnt": root_under_mnt,
        "appworld_root_filesystem": _filesystem_type(root_posix),
        "appworld_version": appworld_version,
        "appworld_package_sha256": _verified_appworld_tree_sha256(),
        "env_pins": dict(_PIN_ENV),
    }


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution_tree_sha256(name: str) -> str:
    """Hash the installed distribution files, excluding interpreter-generated bytecode."""
    distribution = metadata.distribution(name)
    files = distribution.files
    if files is None:
        raise WorkerPreflightError(f"{name} distribution file inventory is unavailable")
    hashes: dict[str, str] = {}
    for relative in sorted(files, key=str):
        relative_text = str(relative).replace("\\", "/")
        if relative_text.endswith((".pyc", ".pyo")) or "/__pycache__/" in relative_text:
            continue
        path = Path(distribution.locate_file(relative))
        if not path.is_file():
            raise WorkerPreflightError(f"{name} distribution file is missing: {relative_text}")
        content = path.read_bytes()
        if path.suffix == ".py":
            content = content.replace(b"\r\n", b"\n")
        hashes[relative_text] = hashlib.sha256(content).hexdigest()
    return hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _verified_appworld_tree_sha256() -> str:
    """Verify the official wheel RECORD, then return its governed installed-tree ID.

    pip adds path-dependent console-script and direct-URL rows, while AppWorld adds
    interpreter bytecode.  Those rows cannot define a portable installed-tree ID.
    Every wheel-owned row is instead matched to the canonical official-wheel RECORD
    and verified against the installed bytes before the governed identity is returned.
    """
    distribution = metadata.distribution("appworld")
    record_relative = next(
        (
            str(item).replace("\\", "/")
            for item in distribution.files or ()
            if str(item).replace("\\", "/").endswith(".dist-info/RECORD")
        ),
        None,
    )
    if record_relative is None:
        raise WorkerPreflightError("appworld RECORD is unavailable")
    record_path = Path(distribution.locate_file(record_relative))
    try:
        rows = list(csv.reader(io.StringIO(record_path.read_text(encoding="utf-8"))))
    except (OSError, UnicodeError, csv.Error) as error:
        raise WorkerPreflightError("appworld RECORD is unreadable") from error
    generated = {
        "../../../bin/appworld",
        record_relative.replace("RECORD", "INSTALLER"),
        record_relative.replace("RECORD", "REQUESTED"),
        record_relative.replace("RECORD", "direct_url.json"),
    }
    wheel_rows: list[tuple[str, str, str]] = []
    for row in rows:
        if len(row) != 3:
            raise WorkerPreflightError("appworld RECORD row is malformed")
        relative, encoded_hash, encoded_size = row
        normalized = relative.replace("\\", "/")
        if normalized in generated or normalized.endswith((".pyc", ".pyo")) or "/__pycache__/" in normalized:
            continue
        wheel_rows.append((normalized, encoded_hash, encoded_size))
    canonical = "".join(
        f"{relative},{encoded_hash},{encoded_size}\n"
        for relative, encoded_hash, encoded_size in sorted(wheel_rows)
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != _APPWORLD_WHEEL_RECORD_SHA256:
        raise WorkerPreflightError("appworld official wheel RECORD identity mismatch")
    for relative, encoded_hash, encoded_size in wheel_rows:
        path = Path(distribution.locate_file(relative))
        if not path.is_file():
            raise WorkerPreflightError(f"appworld distribution file is missing: {relative}")
        content = path.read_bytes()
        if encoded_size and int(encoded_size) != len(content):
            raise WorkerPreflightError(f"appworld distribution size mismatch: {relative}")
        if encoded_hash:
            algorithm, separator, encoded = encoded_hash.partition("=")
            if algorithm != "sha256" or not separator:
                raise WorkerPreflightError(f"appworld RECORD hash is unsupported: {relative}")
            expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            if hashlib.sha256(content).digest() != expected:
                raise WorkerPreflightError(f"appworld distribution hash mismatch: {relative}")
    return _APPWORLD_OFFICIAL_TREE_SHA256


def main() -> int:
    from localbench.scoring.agentic_exec.execution_contract import (  # noqa: PLC0415
        assert_execution_contract,
        assert_runtime_identity,
    )

    session = WorkerSession()
    try:
        assert_execution_contract()
        assert_runtime_identity(collect_identity())
    except (RuntimeError, OSError, ValueError) as exc:
        _write_response(
            sys.stdout.buffer,
            {"kind": "error", "detail": str(exc), "error_type": type(exc).__name__},
        )
        return 2

    def _terminate(_signum: int, _frame: object) -> None:
        session.close()
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, _terminate)
    try:
        return _serve(sys.stdin.buffer, sys.stdout.buffer, session)
    finally:
        session.close()


def _serve(stdin: BinaryIO, stdout: BinaryIO, session: WorkerSession) -> int:
    for raw in stdin:
        try:
            message = decode_worker_frame(raw)
        except (FrameTooLargeError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            response, should_exit = _protocol_error(str(exc)), False
        else:
            response, should_exit = handle_worker_message(message, session)
        _write_response(stdout, response)
        if should_exit:
            return 0
    session.close()
    return 0


def _write_response(stdout: BinaryIO, response: JsonObject) -> None:
    try:
        stdout.write(encode_worker_frame(response))
    except FrameTooLargeError as exc:
        stdout.write(encode_worker_frame(_protocol_error(str(exc))))
    stdout.flush()


def _ok_with_identity() -> JsonObject:
    try:
        return {"kind": "ok", "identity": collect_identity()}
    except WorkerPreflightError as exc:
        return {"kind": "error", "detail": str(exc), "error_type": type(exc).__name__}


def _open_task(worker: WorkerSession, task_id: str) -> JsonObject:
    worker.open_task(task_id)
    return {"kind": "ok"}


def _close(worker: WorkerSession) -> JsonObject:
    worker.close()
    return {"kind": "ok"}


def _list_scored_tasks(max_items: int | None = None) -> JsonObject:
    from localbench.scoring.agentic_exec import task_pool  # noqa: PLC0415
    from localbench.scoring.agentic_exec.execution_contract import (  # noqa: PLC0415
        assert_task_identity,
        contract_task_ids,
    )

    canonical = contract_task_ids()
    selected = canonical[:max_items] if max_items is not None else canonical
    semantic_contents = task_pool.load_semantic_task_contents(selected)
    assert_task_identity(selected, semantic_contents)
    return {"kind": "ok", "task_ids": selected, "canonical_task_ids": canonical}


def _sandbox_call(operation: Callable[[], JsonObject]) -> JsonObject:
    try:
        return operation()
    except (SandboxError, RuntimeError, OSError, ValueError, TimeoutError) as exc:
        return {"kind": "error", "detail": str(exc), "error_type": type(exc).__name__}


def _protocol_error(detail: str) -> JsonObject:
    return {"kind": "protocol_error", "detail": detail}


def _default_sandbox_factory(task_id: str) -> AbstractContextManager[SandboxLike]:
    return AppWorldSandbox(
        task_id,
        SandboxConfig(experiment_name=f"lb_wsl_worker_{task_id}"),
    )


def _json_string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _ensure_env_pins() -> None:
    for key, value in _PIN_ENV.items():
        os.environ.setdefault(key, value)


def _os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        values[key] = raw.strip().strip('"')
    return values


def _package_version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return ""


def _filesystem_type(path: str) -> str:
    return _command_output(["stat", "-f", "-c", "%T", path])


def _command_output(argv: list[str]) -> str:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
