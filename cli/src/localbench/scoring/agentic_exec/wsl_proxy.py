from __future__ import annotations

import subprocess
import sys
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import BinaryIO

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.protocol_c_loop import SandboxLike
from localbench.scoring.agentic_exec.sandbox import (
    BlockObservation,
    FINALIZATION_PROVENANCE,
    SandboxError,
    SandboxTimeoutError,
    WorkerSetupError,
)
from localbench.scoring.agentic_exec.wsl_process import (
    WslWorkerConfig,
    creation_flags,
    kill_process_tree,
    safe_label,
    worker_argv,
    worker_env,
)
from localbench.scoring.agentic_exec.wsl_worker import (
    decode_worker_frame,
    encode_worker_frame,
)


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


class WslSandboxProxy(AbstractContextManager[SandboxLike]):
    def __init__(
        self,
        task_id: str | None,
        config: WslWorkerConfig,
        *,
        expected_identity: JsonObject | None = None,
    ) -> None:
        self.task_id = task_id
        self.config = config
        self.expected_identity = expected_identity
        self.identity: JsonObject | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._stderr_handle: BinaryIO | None = None
        self._closed = False
        self._teardown_failure: str | None = None

    @property
    def teardown_failure(self) -> str | None:
        return self._teardown_failure

    def __enter__(self) -> WslSandboxProxy:
        self._start()
        try:
            hello = self._request({"op": "hello"}, timeout_s=self.config.op_timeout_s)
            identity = hello.get("identity")
            if not isinstance(identity, dict):
                raise SandboxError("wsl worker hello returned no identity")
            self.identity = identity
            if self.expected_identity is not None:
                _assert_preflight_identity(identity, self.expected_identity)
            if self.task_id is not None:
                self._request(
                    {"op": "open_task", "task_id": self.task_id},
                    timeout_s=self.config.open_task_timeout_s,
                )
        except BaseException:
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
            passes=_string_tuple(
                verdict.get("passes"),
                fallback_count=_int_field(verdict.get("num_passes")),
            ),
            failures=_string_tuple(
                verdict.get("failures"),
                fallback_count=_int_field(verdict.get("num_failures")),
            ),
        )

    def finalization_provenance(self) -> JsonObject:
        return dict(FINALIZATION_PROVENANCE)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        try:
            if proc is not None and proc.poll() is None:
                try:
                    self._request(
                        {"op": "close"}, timeout_s=self.config.close_timeout_s
                    )
                    proc.wait(timeout=self.config.close_timeout_s)
                except SandboxTimeoutError:
                    self.force_kill()
                    self._teardown_failure = (
                        f"wsl worker close timed out after {self.config.close_timeout_s}s"
                    )
                except subprocess.TimeoutExpired:
                    self.force_kill()
                    self._teardown_failure = str(SandboxTimeoutError(
                        f"wsl worker did not exit within {self.config.close_timeout_s}s after close",
                    ))
                except SandboxError as error:
                    self.force_kill()
                    self._teardown_failure = f"{type(error).__name__}: {error}"
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
        kill_process_tree(proc)
        try:
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
        self._close_log()

    def list_tasks(self, stage: str = "scored", *, max_items: int | None = None) -> list[str]:
        request: JsonObject = {"op": "list_tasks", "stage": stage}
        if max_items is not None:
            request["max_items"] = max_items
        response = self._request(
            request,
            timeout_s=self.config.open_task_timeout_s,
        )
        task_ids = response.get("task_ids")
        if not isinstance(task_ids, list) or not all(
            isinstance(item, str) for item in task_ids
        ):
            raise SandboxError("wsl worker list_tasks returned invalid task_ids")
        return list(task_ids)

    def _start(self) -> None:
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = (
            self.config.log_dir
            / f"{safe_label(self.task_id or 'preflight')}.{time.time_ns()}.stderr.log"
        )
        self._stderr_handle = log_path.open("ab")
        self._proc = subprocess.Popen(
            list(worker_argv(self.config)),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_handle,
            env=worker_env(self.config),
            creationflags=creation_flags(),
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
            response = read_response(proc.stdout, timeout_s)
        except SandboxError:
            self.force_kill()
            raise
        kind = response.get("kind")
        if kind == "ok":
            return response
        if kind in {"error", "protocol_error"}:
            detail = f"wsl worker {kind}: {response.get('detail', '')}"
            if response.get("error_type") in {
                "ExecutionContractDriftError",
                "RuntimeIdentityDriftError",
                "TaskIdentityDriftError",
                "WorkerPreflightError",
            }:
                raise WorkerSetupError(detail)
            raise SandboxError(detail)
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


def read_response(stdout: BinaryIO, timeout_s: float) -> JsonObject:
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
        raise SandboxTimeoutError(f"wsl worker timed out after {timeout_s}s")
    if errors:
        raise SandboxError(f"wsl worker stdout read failed: {errors[0]}")
    line = result[0] if result else b""
    if not line:
        raise SandboxError("wsl worker closed stdout")
    try:
        return decode_worker_frame(line)
    except (ValueError, OSError) as exc:
        raise SandboxError(f"wsl worker sent invalid frame: {exc}") from exc


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


def _assert_preflight_identity(actual: JsonObject, expected: JsonObject) -> None:
    for field, label in (
        ("localbench_distribution_version", "distribution version"),
        ("worker_content_sha256", "worker content digest"),
    ):
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if not isinstance(expected_value, str) or not expected_value:
            raise WorkerSetupError(f"wsl worker setup failed: preflight {label} is unavailable")
        if actual_value != expected_value:
            raise WorkerSetupError(
                f"wsl worker setup failed: per-task {label} mismatch: "
                f"worker={actual_value!r} preflight={expected_value!r}",
            )
    if actual != expected:
        differing = sorted(
            key for key in set(actual) | set(expected) if actual.get(key) != expected.get(key)
        )
        raise WorkerSetupError(
            "wsl worker setup failed: per-task identity differs from preflight: "
            f"fields={differing}",
        )
