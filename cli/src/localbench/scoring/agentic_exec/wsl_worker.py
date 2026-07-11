from __future__ import annotations

import importlib.metadata as metadata
import hashlib
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
            return _sandbox_call(_list_scored_tasks), False
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


def main() -> int:
    from localbench.scoring.agentic_exec import task_pool  # noqa: PLC0415
    from localbench.scoring.agentic_exec.execution_contract import (  # noqa: PLC0415
        assert_execution_contract,
        assert_task_identity,
        contract_task_ids,
    )

    assert_execution_contract()
    task_ids = contract_task_ids()
    semantic_contents = task_pool.load_semantic_task_contents(task_ids)
    assert_task_identity(task_ids, semantic_contents)
    session = WorkerSession()

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


def _list_scored_tasks() -> JsonObject:
    from localbench.scoring.agentic_exec.execution_contract import contract_task_ids  # noqa: PLC0415

    return {"kind": "ok", "task_ids": contract_task_ids()}


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
