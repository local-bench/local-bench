"""``AppWorldSandbox`` — process + filesystem isolation orchestrator for AppWorld-C.

Public interface (what the future Protocol C agent loop sits on top of)::

    with AppWorldSandbox(task_id) as sb:
        obs = sb.run_block(code)        # -> BlockObservation(stdout, error)
        ...                             # incremental blocks; state persists across blocks
        verdict = sb.finalize(answer)   # -> Verdict(success, collateral_damage, passes, failures)

Boundary (proven end-to-end against the canary suite):

  * TRUSTED env-host process (``env_host``) runs in the WSL appworld venv WITH ``APPWORLD_ROOT``,
    owns the real ``world`` + data + ``requester`` + evaluator, serves API calls over a narrow
    unix-socket RPC, and accepts finalization only over its trusted stdin control channel. It is
    the only process that imports AppWorld.
  * UNTRUSTED code-runner (``runner_bootstrap``) runs under **bubblewrap** with ``--unshare-all``
    (incl. network), NO bind-mount of the data tree, empty tmpfs ``/tmp`` + ``/home``, a scrubbed
    env (no ``APPWORLD_ROOT``), dropped caps, ``no_new_privs``, and CPU/mem/wall limits. Its ONLY
    window onto AppWorld is the bind-mounted unix socket at ``/rpc/rpc.sock``; the ``apis`` proxy
    it hands model code carries no requester/world/client. An in-process allow-list is a belt only.

The orchestrator brokers JSON commands to the runner over the bwrap stdio pipe, while API calls
go from the runner to the env host over the socket. Finalization goes directly from the
orchestrator to the env host over stdin/stdout. The sandbox never lets the runner talk to the
env host's *constructor* — only the already-bound, single-task RPC surface.

This module is import-safe on Windows (no Linux-only imports at module load); ``__enter__`` is
what requires bwrap + the appworld venv and therefore only runs under WSL.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Path, inside the jail, where the RPC socket directory is bind-mounted.
_JAIL_RPC_DIR = "/rpc"
_JAIL_RPC_SOCKET = "/rpc/rpc.sock"
_JAIL_RUN_DIR = "/lbrun"  # where the runner bootstrap is mounted read-only

_DEFAULT_READY_TIMEOUT_S = 120.0   # world construction + DB reset can take a little time
_DEFAULT_BLOCK_WALL_TIMEOUT_S = 300.0
_DEFAULT_FINALIZE_TIMEOUT_S = 120.0

# Additive per-task finalization provenance (docs/benchmark-build/
# direct-finalize-provenance-trust-tier-note-2026-07-03.md). Constant because this module has
# exactly one finalize path: the orchestrator-held env-host stdin control channel, correlated by
# finalize_id against the task pinned at env-host spawn, one-shot. The untrusted runner cannot
# reach the verdict path. The loop stamps answer_hash on top of this descriptor per task.
FINALIZATION_PROVENANCE: dict[str, Any] = {
    "path": "orchestrator-direct-envhost-stdin-v1",
    "runner_in_verdict_path": False,
    "finalize_correlation": "finalize_id+pinned_task+one_shot",
}


class SandboxError(RuntimeError):
    """Raised when the sandbox cannot be constructed or a broker step fails irrecoverably."""


class SandboxTimeoutError(SandboxError):
    """Raised only when the per-block wall-clock infrastructure safety net fires."""


@dataclass(frozen=True, slots=True)
class BlockObservation:
    """Result of executing one model code block through the sandbox."""

    stdout: str
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class Verdict:
    """Final-state evaluation result (from the harness-owned finalize seam)."""

    success: bool
    collateral_damage: bool
    passes: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Resource + path knobs. Defaults match the WSL appworld-harness layout."""

    # Interpreter for the UNTRUSTED runner inside the jail. Must be self-contained against the
    # mounted /usr stdlib only (no venv site-packages mounted) — the system python is ideal.
    runner_python_exe: str = "/usr/bin/python3"
    # Interpreter for the TRUSTED env host. Must have appworld + localbench importable; defaults
    # to the current interpreter (when the orchestrator runs in the appworld venv, this is it).
    host_python_exe: str = ""  # empty -> sys.executable
    bwrap_path: str = ""  # resolved in __post_init__-ish via _resolve_bwrap if empty
    appworld_root: str = ""  # taken from env if empty
    cpu_seconds: int = 60
    address_space_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB
    tmpfs_size_bytes: int = 256 * 1024 * 1024  # 256 MiB scratch
    ready_timeout_s: float = _DEFAULT_READY_TIMEOUT_S
    # Backward-compatible legacy alias. Prefer ``block_wall_timeout_s`` for new code.
    block_timeout_s: float = _DEFAULT_BLOCK_WALL_TIMEOUT_S
    finalize_timeout_s: float = _DEFAULT_FINALIZE_TIMEOUT_S
    # This is NOT a compute budget. CPU is gated by RLIMIT_CPU via ``cpu_seconds``; this larger
    # wall-clock net only catches infrastructure hangs/deadlocks and is classified separately.
    block_wall_timeout_s: float = _DEFAULT_BLOCK_WALL_TIMEOUT_S
    experiment_name: str = "lb_agentic_sandbox"


@dataclass(frozen=True, slots=True)
class _RunnerEventRead:
    event: dict[str, Any] | None
    timed_out: bool


def resolve_host_python(explicit: str = "") -> str:
    """Pick an interpreter that can import ``appworld`` for the trusted env host.

    The orchestrator is meant to run inside the appworld venv, but in some WSL setups the venv's
    ``activate`` does not shadow ``python3`` (so ``sys.executable`` may be the system python that
    lacks appworld). We therefore probe candidates and return the first that imports appworld.
    """
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_hint = os.environ.get("LB_APPWORLD_PYTHON", "")
    if env_hint:
        candidates.append(env_hint)
    candidates.append(sys.executable)
    venv = os.environ.get("VIRTUAL_ENV", "")
    if venv:
        candidates.append(os.path.join(venv, "bin", "python3"))
    candidates.append(os.path.expanduser("~/appworld-harness/venv/bin/python3"))
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        if not os.path.exists(cand):
            continue
        try:
            probe = subprocess.run(
                [cand, "-c", "import appworld"],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return cand
    # Nothing imported appworld; return the best guess so the caller gets a clear downstream error.
    return explicit or sys.executable


def resolve_bwrap(explicit: str = "") -> str | None:
    """Find a usable ``bwrap`` (explicit path, PATH, or the user-local extracted copy)."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    found = shutil.which("bwrap")
    if found:
        candidates.append(found)
    candidates.append(os.path.expanduser("~/.local/bin/bwrap"))
    for cand in candidates:
        if cand and os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return None


class AppWorldSandbox:
    """Two-process, FS-isolated executor for one AppWorld task."""

    def __init__(self, task_id: str, config: SandboxConfig | None = None) -> None:
        self.task_id = task_id
        self.config = config or SandboxConfig()
        self._workdir: str | None = None
        self._sock_dir: str | None = None
        self._socket_path: str | None = None
        self._env_proc: subprocess.Popen[str] | None = None
        self._runner_proc: subprocess.Popen[str] | None = None
        self._closed = False
        self._finalized = False
        self._finalize_counter = 0
        # captured stderr from children (for diagnostics on failure)
        self._env_stderr: list[str] = []
        self._runner_stderr: list[str] = []

    # -- context management ---------------------------------------------------------------------

    def __enter__(self) -> AppWorldSandbox:
        try:
            self._start()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- lifecycle ------------------------------------------------------------------------------

    def _start(self) -> None:
        bwrap = resolve_bwrap(self.config.bwrap_path)
        if not bwrap:
            raise SandboxError(
                "bubblewrap (bwrap) not found. Install it or place it at ~/.local/bin/bwrap. "
                "A namespace-only fallback is intentionally NOT provided — the canary suite "
                "would defeat it (see appworld-sandbox-build-spec.md)."
            )
        appworld_root = self.config.appworld_root or os.environ.get("APPWORLD_ROOT", "")
        if not appworld_root:
            raise SandboxError("APPWORLD_ROOT is not set (the env host needs it).")

        self._workdir = tempfile.mkdtemp(prefix="lb_sandbox_")
        # Socket dir is created 0700 so only this user can reach the RPC endpoint.
        self._sock_dir = tempfile.mkdtemp(prefix="lb_rpc_")
        os.chmod(self._sock_dir, 0o700)
        self._socket_path = os.path.join(self._sock_dir, "rpc.sock")

        self._start_env_host(appworld_root)
        self._wait_for_socket()
        self._start_runner(bwrap)
        self._wait_for_runner_ready()

    def _start_env_host(self, appworld_root: str) -> None:
        """Spawn the trusted env host in the appworld venv WITH APPWORLD_ROOT."""
        env = dict(os.environ)
        env["APPWORLD_ROOT"] = appworld_root
        env.setdefault("PYTHONHASHSEED", "0")
        env.setdefault("TZ", "UTC")
        env.setdefault("LC_ALL", "C.UTF-8")
        # Ensure the env host can import localbench: run with the repo src on PYTHONPATH.
        env["PYTHONPATH"] = _repo_src_path() + os.pathsep + env.get("PYTHONPATH", "")
        host_python = resolve_host_python(self.config.host_python_exe)
        argv = [
            host_python,
            "-m",
            "localbench.scoring.agentic_exec.env_host",
            self.task_id,
            self._socket_path,
            self.config.experiment_name,
        ]
        self._env_proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
            preexec_fn=_make_pdeathsig_preexec(),  # noqa: PLW1509 — POSIX-only, intended.
        )
        threading.Thread(target=self._drain, args=(self._env_proc.stderr, self._env_stderr),
                         daemon=True).start()

    def _wait_for_socket(self) -> None:
        """Block until the env host prints READY (world built + socket listening)."""
        assert self._env_proc is not None and self._env_proc.stdout is not None
        deadline = time.monotonic() + self.config.ready_timeout_s
        while True:
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                break
            if self._env_proc.poll() is not None:
                raise SandboxError(
                    "env host exited before READY (rc="
                    f"{self._env_proc.returncode}). stderr:\n{''.join(self._env_stderr)[-2000:]}"
                )
            line = self._read_env_host_line(remaining_s)
            if line is None:
                break
            if line.strip() == "READY":
                return
            if not line:
                raise SandboxError(
                    "env host stdout closed before READY. "
                    f"stderr:\n{''.join(self._env_stderr)[-2000:]}"
                )
            if line:  # unexpected stdout from the host before READY
                self._env_stderr.append("[host-stdout] " + line)
        raise SandboxError(
            f"env host did not become READY within {self.config.ready_timeout_s}s. "
            f"stderr:\n{''.join(self._env_stderr)[-2000:]}"
        )

    def _read_env_host_line(self, timeout_s: float) -> str | None:
        assert self._env_proc is not None and self._env_proc.stdout is not None
        result: list[str] = []
        errors: list[OSError | ValueError] = []

        def _reader() -> None:
            try:
                result.append(self._env_proc.stdout.readline())  # type: ignore[union-attr]
            except (OSError, ValueError) as exc:
                errors.append(exc)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout_s)
        if t.is_alive():
            return None
        if errors:
            raise SandboxError(f"env host stdout read failed: {errors[0]}")
        return result[0] if result else ""

    def _start_runner(self, bwrap: str) -> None:
        """Spawn the untrusted runner under bwrap with full isolation."""
        # Stage the two import-safe files the runner needs into a read-only mount dir.
        run_src_dir = os.path.join(self._workdir, "runsrc")  # type: ignore[arg-type]
        os.makedirs(run_src_dir, exist_ok=True)
        pkg_dir = Path(__file__).resolve().parent
        shutil.copy2(pkg_dir / "runner_bootstrap.py", os.path.join(run_src_dir, "runner_bootstrap.py"))

        bwrap_argv = [
            bwrap,
            "--unshare-all",            # new user/ipc/pid/uts/cgroup/mount/NET namespaces
            "--die-with-parent",        # SIGKILL the jail if the orchestrator dies
            "--new-session",            # detach controlling terminal (anti-TIOCSTI)
            "--cap-drop", "ALL",        # drop every capability (belt; userns already empties them)
            "--hostname", "sandbox",
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64",
            "--symlink", "usr/sbin", "/sbin",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--tmpfs", "/home",
            "--size", str(self.config.tmpfs_size_bytes), "--tmpfs", "/lbscratch",
            "--ro-bind", run_src_dir, _JAIL_RUN_DIR,
            "--bind", self._sock_dir, _JAIL_RPC_DIR,   # the ONLY window to the env host
            "--chdir", "/lbscratch",
            "--clearenv",
            "--setenv", "HOME", "/lbscratch",
            "--setenv", "PATH", "/usr/bin:/bin",
            "--setenv", "PYTHONHASHSEED", "0",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--setenv", "TZ", "UTC",
            "--setenv", "LC_ALL", "C.UTF-8",
            "--setenv", "PYTHONPATH", _JAIL_RUN_DIR,
            self.config.runner_python_exe,
            "-I",                        # isolated mode: ignore env/user site, no implicit cwd
            os.path.join(_JAIL_RUN_DIR, "runner_bootstrap.py"),
        ]
        self._runner_proc = subprocess.Popen(
            bwrap_argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=_make_rlimit_preexec(self.config),  # noqa: PLW1509 — POSIX-only, intended.
        )
        threading.Thread(target=self._drain, args=(self._runner_proc.stderr, self._runner_stderr),
                         daemon=True).start()

    def _wait_for_runner_ready(self) -> None:
        event = self._read_runner_event(self.config.ready_timeout_s).event
        if not event or event.get("event") != "ready":
            raise SandboxError(
                f"runner did not signal ready (got {event!r}). "
                f"stderr:\n{''.join(self._runner_stderr)[-2000:]}"
            )

    # -- brokered operations --------------------------------------------------------------------

    def run_block(self, code: str) -> BlockObservation:
        """Execute one model code block in the jail; return its captured stdout + any error."""
        self._ensure_live()
        self._send_runner({"cmd": "run_block", "code": code})
        read = self._read_runner_event(_effective_block_wall_timeout_s(self.config))
        event = read.event
        if read.timed_out:
            self.close()
            raise SandboxTimeoutError(
                "runner exceeded the per-block wall-clock infrastructure safety net. "
                f"cpu_seconds={self.config.cpu_seconds}, "
                f"block_wall_timeout_s={_effective_block_wall_timeout_s(self.config)}. "
                f"stderr:\n{''.join(self._runner_stderr)[-2000:]}"
            )
        if event is None:
            raise SandboxError(
                "runner timed out / died during run_block. "
                f"stderr:\n{''.join(self._runner_stderr)[-2000:]}"
            )
        if event.get("event") == "fatal":
            raise SandboxError("runner fatal: " + str(event.get("message")))
        if event.get("event") != "block_result":
            raise SandboxError(f"unexpected runner event: {event!r}")
        return BlockObservation(stdout=event.get("stdout", ""), error=event.get("error"))

    def finalize(self, answer: Any) -> Verdict:
        """Finalize the task (complete_task + evaluate) via the trusted env-host control seam."""
        self._ensure_live()
        if self._finalized:
            raise SandboxError("finalize already called for this task")
        self._finalized = True
        finalize_id = self._next_finalize_id()
        self._send_env_control({"op": "finalize", "answer": answer, "finalize_id": finalize_id})
        event = self._read_authoritative_verdict(finalize_id, self.config.finalize_timeout_s)
        result = event.get("result")
        if not isinstance(result, dict):
            error = event.get("error")
            raise SandboxError(
                f"env host finalize failed (event={event!r}, error={error!r}). "
                f"env-stderr:\n{''.join(self._env_stderr)[-1500:]}"
            )
        return Verdict(
            success=bool(result.get("success", False)),
            collateral_damage=bool(result.get("collateral_damage", False)),
            passes=tuple(result.get("passes", [])),
            failures=tuple(result.get("failures", [])),
        )

    def finalization_provenance(self) -> dict[str, Any]:
        """Descriptor of the verdict channel this sandbox uses (additive per-task provenance)."""
        return dict(FINALIZATION_PROVENANCE)

    # -- internals ------------------------------------------------------------------------------

    def _next_finalize_id(self) -> str:
        # A deterministic id is intentional and safe: security rests on channel separation — the
        # untrusted runner cannot write the env-host's stdin (finalize in) or stdout (verdict out),
        # both of which are private orchestrator<->env-host pipes. The id only CORRELATES the
        # verdict to the pending finalization; it is not a secret capability.
        self._finalize_counter += 1
        return f"{self.config.experiment_name}:{self.task_id}:finalize:{self._finalize_counter}"

    def _send_env_control(self, message: dict[str, Any]) -> None:
        assert self._env_proc is not None and self._env_proc.stdin is not None
        try:
            self._env_proc.stdin.write(json.dumps(message, ensure_ascii=True) + "\n")
            self._env_proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            raise SandboxError(f"env host control pipe broken: {exc}") from exc

    def _read_authoritative_verdict(
        self,
        finalize_id: str,
        timeout_s: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while True:
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                raise SandboxError(
                    f"authoritative finalize timed out waiting for finalize_id={finalize_id!r}"
                )
            line = self._read_env_host_line(remaining_s)
            if line is None:
                raise SandboxError(
                    f"authoritative finalize timed out waiting for finalize_id={finalize_id!r}"
                )
            if not line:
                raise SandboxError("env host stdout closed before authoritative verdict")
            # The env-host control stdout may also carry benign noise (AppWorld/library prints
            # during complete_task/evaluate). Only the trusted env-host writes here — the runner
            # cannot reach this fd — so skipping non-verdict lines is safe and prevents a stray
            # log line from failing an otherwise-valid task. Keep waiting for the correlated line.
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "authoritative_verdict":
                continue
            echoed_id = event.get("finalize_id")
            if echoed_id != finalize_id:
                # A genuine authoritative_verdict for the wrong finalization is anomalous (only one
                # finalize is ever armed, one-shot). Fail closed rather than skip — never "latest wins".
                raise SandboxError(
                    f"authoritative verdict finalize_id mismatch: {echoed_id!r} != {finalize_id!r}"
                )
            return event

    def _send_runner(self, command: dict[str, Any]) -> None:
        assert self._runner_proc is not None and self._runner_proc.stdin is not None
        try:
            self._runner_proc.stdin.write(json.dumps(command, ensure_ascii=True) + "\n")
            self._runner_proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise SandboxError(f"runner pipe broken: {exc}") from exc

    def _read_runner_event(self, timeout_s: float) -> _RunnerEventRead:
        """Read one JSON event line from the runner with a wall-clock timeout."""
        assert self._runner_proc is not None and self._runner_proc.stdout is not None
        result: dict[str, list[str]] = {"line": []}

        def _reader() -> None:
            line = self._runner_proc.stdout.readline()  # type: ignore[union-attr]
            result["line"].append(line)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout_s)
        if t.is_alive():
            return _RunnerEventRead(event=None, timed_out=True)
        line = result["line"][0] if result["line"] else ""
        if not line:
            return _RunnerEventRead(event=None, timed_out=False)
        try:
            return _RunnerEventRead(event=json.loads(line), timed_out=False)
        except json.JSONDecodeError:
            return _RunnerEventRead(
                event={"event": "fatal", "message": "non-json from runner: " + line[:200]},
                timed_out=False,
            )

    def _ensure_live(self) -> None:
        if self._closed:
            raise SandboxError("sandbox is closed")
        if self._runner_proc is not None and self._runner_proc.poll() is not None:
            raise SandboxError(
                f"runner process exited (rc={self._runner_proc.returncode}). "
                f"stderr:\n{''.join(self._runner_stderr)[-2000:]}"
            )

    @staticmethod
    def _drain(stream: Any, sink: list[str]) -> None:
        try:
            for line in stream:
                sink.append(line)
        except (ValueError, OSError):
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._runner_proc is not None and self._runner_proc.poll() is None:
                try:
                    if self._runner_proc.stdin is not None:
                        self._runner_proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                        self._runner_proc.stdin.flush()
                except (BrokenPipeError, OSError, ValueError):
                    pass
                _terminate(self._runner_proc)
            if self._env_proc is not None and self._env_proc.poll() is None:
                _terminate(self._env_proc)
        finally:
            self._cleanup_paths()

    def force_kill(self) -> None:
        self._closed = True
        try:
            _kill_process_group(self._runner_proc)
            _kill_process_group(self._env_proc)
            _wait_for_process_exit(self._runner_proc)
            _wait_for_process_exit(self._env_proc)
        finally:
            self._cleanup_paths()

    def _cleanup_paths(self) -> None:
        for path in (self._sock_dir, self._workdir):
            if path and os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)


# ----------------------------------------------------------------------------------------------
# helpers (module-level so they stay import-safe on non-POSIX hosts)
# ----------------------------------------------------------------------------------------------
def _repo_src_path() -> str:
    """Absolute path to ``cli/src`` so the env host can import localbench under WSL."""
    # this file: cli/src/localbench/scoring/agentic_exec/sandbox.py  ->  cli/src
    return str(Path(__file__).resolve().parents[3])


def _effective_block_wall_timeout_s(config: SandboxConfig) -> float:
    legacy_override = (
        config.block_timeout_s != _DEFAULT_BLOCK_WALL_TIMEOUT_S
        and config.block_wall_timeout_s == _DEFAULT_BLOCK_WALL_TIMEOUT_S
    )
    if legacy_override:
        return config.block_timeout_s
    return config.block_wall_timeout_s


def _terminate(proc: subprocess.Popen[Any]) -> None:
    try:
        proc.terminate()
    except OSError:
        _kill_process_group(proc)
        _wait_for_process_exit(proc)
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        _wait_for_process_exit(proc)
    except OSError:
        _kill_process_group(proc)
        _wait_for_process_exit(proc)


def _kill_process_group(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None:
        return
    getpgid = getattr(os, "getpgid", None)
    killpg = getattr(os, "killpg", None)
    if getpgid is None or killpg is None:
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        pgid = getpgid(proc.pid)
    except ProcessLookupError:
        return
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        killpg(pgid, getattr(signal, "SIGKILL", 9))
    except ProcessLookupError:
        pass
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def _wait_for_process_exit(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None:
        return
    try:
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _make_pdeathsig_preexec() -> Any:
    """Return a preexec_fn that tethers the child to its parent's death (Linux only).

    The env host runs in its own session (``start_new_session=True``) so group-kill
    teardown works — but that also means it survives a hard kill of its parent (e.g.
    the WSL bridge worker dying mid-task) and orphans the AppWorld world. PDEATHSIG
    persists across exec and makes the kernel deliver SIGKILL the moment the parent
    dies; lifecycle-only, no change to the sandbox security semantics.
    """
    if not sys.platform.startswith("linux"):
        return None

    def _preexec() -> None:  # pragma: no cover - exercised only under WSL/Linux at runtime.
        try:
            import ctypes
            import signal as _signal

            PR_SET_PDEATHSIG = 1
            ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, _signal.SIGKILL, 0, 0, 0)
        except Exception:  # noqa: BLE001 — best effort; close()/force_kill remain the primary path.
            pass

    return _preexec


def _make_rlimit_preexec(config: SandboxConfig) -> Any:
    """Return a preexec_fn that sets CPU + address-space rlimits on the bwrap child (POSIX only).

    bwrap itself does not set rlimits; we apply them in the forked child before exec so they are
    inherited by the runner inside the jail. ``no_new_privs`` is also set here as a syscall belt
    (bwrap sets it too with --unshare-all, but we make it explicit).
    """
    if not sys.platform.startswith("linux"):
        return None

    def _preexec() -> None:  # pragma: no cover - exercised only under WSL/Linux at runtime.
        import resource

        cpu = config.cpu_seconds
        mem = config.address_space_bytes
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 2))
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        try:
            import ctypes

            PR_SET_NO_NEW_PRIVS = 38
            ctypes.CDLL(None, use_errno=True).prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
        except Exception:  # noqa: BLE001 — best effort; bwrap also sets no_new_privs.
            pass

    return _preexec
