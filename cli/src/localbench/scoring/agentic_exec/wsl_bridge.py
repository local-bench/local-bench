from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.protocol_c_loop import SandboxLike
from localbench.scoring.agentic_exec.sandbox import (
    BlockObservation,
    SandboxError,
    FINALIZATION_PROVENANCE,
)
from localbench.scoring.agentic_exec.wsl_worker import (
    decode_worker_frame,
    encode_worker_frame,
)

_DEFAULT_WSL_VENV_PYTHON: Final = "~/appworld-harness/venv/bin/python3"
_DEFAULT_APPWORLD_ROOT: Final = "/home/michael/appworld-data"


@dataclass(frozen=True, slots=True)
class WslWorkerConfig:
    repo_root_wsl_path: str
    venv_python: str = _DEFAULT_WSL_VENV_PYTHON
    appworld_root: str = _DEFAULT_APPWORLD_ROOT
    log_dir: Path = Path("runs") / "agentic-wsl"
    open_task_timeout_s: float = 180.0
    op_timeout_s: float = 300.0
    finalize_timeout_s: float = 120.0
    close_timeout_s: float = 5.0
    worker_argv: tuple[str, ...] | None = None
    worker_env: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class WslVerdict:
    success: bool
    collateral_damage: bool
    passes: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()

    @property
    def num_passes(self) -> int:
        return len(self.passes)

    @property
    def num_failures(self) -> int:
        return len(self.failures)


@dataclass(frozen=True, slots=True)
class WslPreflightResult:
    identity: JsonObject
    task_ids: tuple[str, ...]

    def provenance(self) -> JsonObject:
        return provenance_from_identity(self.identity)


class WslSandboxProxy(AbstractContextManager[SandboxLike]):
    def __init__(self, task_id: str | None, config: WslWorkerConfig) -> None:
        self.task_id = task_id
        self.config = config
        self.identity: JsonObject | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._stderr_handle: BinaryIO | None = None
        self._closed = False

    def __enter__(self) -> WslSandboxProxy:
        self._start()
        try:
            hello = self._request({"op": "hello"}, timeout_s=self.config.op_timeout_s)
            identity = hello.get("identity")
            if not isinstance(identity, dict):
                raise SandboxError("wsl worker hello returned no identity")
            self.identity = identity
            if self.task_id is not None:
                self._request(
                    {"op": "open_task", "task_id": self.task_id},
                    timeout_s=self.config.open_task_timeout_s,
                )
        except BaseException:
            # Any enter-time failure (hello/open_task timeout or error) must not leak the wsl.exe
            # worker + its stderr log handle: __exit__ never runs when __enter__ raises. Over a
            # 96-task run these would accumulate. Tear down before propagating.
            self.force_kill()
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def run_block(self, code: str) -> BlockObservation:
        response = self._request(
            {"op": "run_block", "code": code},
            timeout_s=self.config.op_timeout_s,
        )
        stdout = response.get("stdout")
        error = response.get("error")
        return BlockObservation(
            stdout=stdout if isinstance(stdout, str) else "",
            error=error if isinstance(error, str) else None,
        )

    def finalize(self, answer: JsonValue) -> WslVerdict:
        response = self._request(
            {"op": "finalize", "answer": answer},
            timeout_s=self.config.finalize_timeout_s,
        )
        verdict = response.get("verdict")
        if not isinstance(verdict, dict):
            raise SandboxError("wsl worker finalize returned no verdict")
        return WslVerdict(
            success=bool(verdict.get("success", False)),
            collateral_damage=bool(verdict.get("collateral_damage", False)),
            passes=_string_tuple(verdict.get("passes"), fallback_count=_int_field(verdict.get("num_passes"))),
            failures=_string_tuple(
                verdict.get("failures"),
                fallback_count=_int_field(verdict.get("num_failures")),
            ),
        )

    def finalization_provenance(self) -> JsonObject:
        # The proxy delegates finalize to the trusted WSL worker, which drives the same env-host
        # stdin control channel (AppWorldSandbox.finalize) — the verdict path is identical, so
        # the descriptor is shared. Every hop (proxy -> worker -> env-host) is trusted.
        return dict(FINALIZATION_PROVENANCE)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        try:
            if proc is not None and proc.poll() is None:
                try:
                    self._request({"op": "close"}, timeout_s=self.config.close_timeout_s)
                    proc.wait(timeout=self.config.close_timeout_s)
                except (SandboxError, subprocess.TimeoutExpired):
                    self.force_kill()
        finally:
            self._close_log()

    def force_kill(self) -> None:
        proc = self._proc
        if proc is None:
            self._close_log()
            return
        if proc.poll() is not None:
            self._close_log()
            return
        _kill_process_tree(proc)
        try:
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
        self._close_log()

    def list_tasks(self, stage: str = "scored") -> list[str]:
        response = self._request(
            {"op": "list_tasks", "stage": stage},
            timeout_s=self.config.open_task_timeout_s,
        )
        task_ids = response.get("task_ids")
        if not isinstance(task_ids, list) or not all(isinstance(item, str) for item in task_ids):
            raise SandboxError("wsl worker list_tasks returned invalid task_ids")
        return list(task_ids)

    def _start(self) -> None:
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.config.log_dir / f"{_safe_label(self.task_id or 'preflight')}.{time.time_ns()}.stderr.log"
        self._stderr_handle = log_path.open("ab")
        self._proc = subprocess.Popen(
            list(_worker_argv(self.config)),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_handle,
            env=_worker_env(self.config),
            creationflags=_creation_flags(),
            start_new_session=sys.platform != "win32",
        )

    def _request(self, message: JsonObject, *, timeout_s: float) -> JsonObject:
        proc = self._require_proc()
        if proc.stdin is None or proc.stdout is None:
            raise SandboxError("wsl worker pipes are unavailable")
        try:
            try:
                proc.stdin.write(encode_worker_frame(message))
                proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise SandboxError(f"wsl worker pipe write failed: {exc}") from exc
            response = _read_response(proc.stdout, timeout_s)
        except SandboxError:
            # A transport-level failure (timeout, closed/garbled stdout, broken pipe) leaves the
            # NDJSON request/response stream in an unknown state: a late response could pair with
            # the NEXT request and desync every read after it. Fail closed — kill the worker tree
            # so the proxy is dead rather than subtly wrong. Well-formed error responses below do
            # NOT kill: for those the protocol is still in sync and close() stays graceful.
            self.force_kill()
            raise
        kind = response.get("kind")
        if kind == "ok":
            return response
        if kind in {"error", "protocol_error"}:
            raise SandboxError(f"wsl worker {kind}: {response.get('detail', '')}")
        raise SandboxError(f"wsl worker returned invalid response kind: {kind!r}")

    def _require_proc(self) -> subprocess.Popen[bytes]:
        proc = self._proc
        if proc is None:
            raise SandboxError("wsl worker is not started")
        if proc.poll() is not None:
            raise SandboxError(f"wsl worker exited with rc={proc.returncode}")
        return proc

    def _close_log(self) -> None:
        handle = self._stderr_handle
        self._stderr_handle = None
        if handle is not None:
            handle.close()


def wsl_sandbox_factory(
    repo_root_wsl_path: str,
    venv_python: str,
    appworld_root: str,
    *,
    log_dir: Path | None = None,
    worker_argv: tuple[str, ...] | None = None,
) -> Callable[[str], AbstractContextManager[SandboxLike]]:
    config = WslWorkerConfig(
        repo_root_wsl_path=repo_root_wsl_path,
        venv_python=venv_python,
        appworld_root=appworld_root,
        log_dir=log_dir or Path("runs") / "agentic-wsl",
        worker_argv=worker_argv,
    )

    def _factory(task_id: str) -> WslSandboxProxy:
        return WslSandboxProxy(task_id, config)

    return _factory


def wsl_list_scored_task_ids(config: WslWorkerConfig) -> list[str]:
    with WslSandboxProxy(None, config) as worker:
        return worker.list_tasks("scored")


def preflight_wsl_agentic(
    *,
    repo_root_wsl_path: str,
    venv_python: str,
    appworld_root: str,
    log_dir: Path,
    expected_git_commit: str | None = None,
    max_items: int | None = None,
) -> WslPreflightResult:
    config = WslWorkerConfig(
        repo_root_wsl_path=repo_root_wsl_path,
        venv_python=venv_python,
        appworld_root=appworld_root,
        log_dir=log_dir,
    )
    with WslSandboxProxy(None, config) as worker:
        identity = worker.identity
        if identity is None:
            raise SandboxError("wsl preflight did not collect worker identity")
        _assert_identity(identity, expected_git_commit)
        task_ids = tuple(worker.list_tasks("scored"))
    if not task_ids:
        raise SandboxError("wsl preflight list_tasks returned no scored tasks")
    selected = task_ids[:max_items] if max_items is not None else task_ids
    return WslPreflightResult(identity=identity, task_ids=tuple(selected))


def provenance_from_identity(identity: JsonObject) -> JsonObject:
    return {
        "topology": {
            "scorecard_assembly": "single-campaign-no-merge",
            "model_call_location": "windows_campaign_process",
        },
        "wsl_identity": dict(identity),
        "agentic_sandbox_identity": {
            "bubblewrap_path": _string(identity.get("bwrap_path")),
            "bubblewrap_version": _string(identity.get("bwrap_version")),
            "appworld_root": _string(identity.get("appworld_root")),
            "appworld_root_filesystem": _string(identity.get("appworld_root_filesystem")),
        },
        "single_campaign_integrity": {
            "merge_step_used": False,
        },
        # Run-level trust-tier note for the agentic harness: the verdict is host-derived over
        # the env-host stdin control channel; the untrusted runner is not in the verdict path.
        "agentic_verdict_channel": {
            **FINALIZATION_PROVENANCE,
            "trust_note": "host-derived+direct-finalize-v1",
        },
    }


def default_wsl_repo_path(windows_repo_root: Path) -> str:
    resolved = windows_repo_root.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[1].lstrip("/")
    return f"/mnt/{drive}/{rest}"


def _read_response(stdout: BinaryIO, timeout_s: float) -> JsonObject:
    result: list[bytes] = []
    errors: list[OSError | ValueError] = []

    def _reader() -> None:
        try:
            result.append(stdout.readline())
        except (OSError, ValueError) as exc:
            errors.append(exc)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        raise SandboxError(f"wsl worker timed out after {timeout_s}s")
    if errors:
        raise SandboxError(f"wsl worker stdout read failed: {errors[0]}")
    line = result[0] if result else b""
    if not line:
        raise SandboxError("wsl worker closed stdout")
    try:
        return decode_worker_frame(line)
    except (ValueError, OSError) as exc:
        raise SandboxError(f"wsl worker sent invalid frame: {exc}") from exc


def _assert_identity(identity: JsonObject, expected_git_commit: str | None) -> None:
    if identity.get("appworld_root_under_mnt") is True:
        raise SandboxError("wsl preflight failed: APPWORLD_ROOT is under /mnt")
    if not identity.get("bwrap_path"):
        raise SandboxError("wsl preflight failed: bwrap is missing")
    if expected_git_commit is not None and identity.get("worker_git_commit") != expected_git_commit:
        raise SandboxError(
            "wsl preflight failed: worker git commit "
            f"{identity.get('worker_git_commit')!r} != Windows HEAD {expected_git_commit!r}",
        )


def _worker_argv(config: WslWorkerConfig) -> tuple[str, ...]:
    if config.worker_argv is not None:
        return config.worker_argv
    command = " && ".join(
        [
            f"cd {shlex.quote(config.repo_root_wsl_path)}",
            f"export APPWORLD_ROOT={shlex.quote(config.appworld_root)}",
            "export PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8",
            'export PATH="$HOME/.local/bin:$PATH"',
            f"export PYTHONPATH={shlex.quote(config.repo_root_wsl_path + '/cli/src')}:$PYTHONPATH",
            (
                f"{_quote_wsl_executable(config.venv_python)} "
                "-m localbench.scoring.agentic_exec.wsl_worker"
            ),
        ],
    )
    return ("wsl.exe", "bash", "-lc", command)


def _quote_wsl_executable(path: str) -> str:
    # shlex.quote would wrap a leading ~ in single quotes, suppressing bash tilde
    # expansion — the default venv path relies on it. Expand it as $HOME instead.
    if path == "~" or path.startswith("~/"):
        return '"$HOME"' + shlex.quote(path[1:])
    return shlex.quote(path)


def _worker_env(config: WslWorkerConfig) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "APPWORLD_ROOT": config.appworld_root,
            "PYTHONHASHSEED": "0",
            "TZ": "UTC",
            "LC_ALL": "C.UTF-8",
        },
    )
    if config.worker_env is not None:
        env.update(dict(config.worker_env))
    return env


def _kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        return
    except (subprocess.TimeoutExpired, OSError):
        pass
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def _creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def _safe_label(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


def _int_field(value: JsonValue | None) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _string_tuple(value: JsonValue | None, *, fallback_count: int) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return tuple("" for _ in range(fallback_count))


def _string(value: JsonValue | None) -> str:
    return value if isinstance(value, str) else ""
