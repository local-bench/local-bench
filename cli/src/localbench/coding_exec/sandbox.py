"""Hardened Docker sandbox for running untrusted, model-generated code.

Security model LOCKED after the dual security red-team (GPT-5.5 + Gemini 3.1 Pro,
2026-06-19). Posture: USER-SIDE, opt-in, default-deny container; we never execute
untrusted code on our own infra in v1. Every mandatory hardening flag is built into
`docker_run_argv` and asserted by tests (`MANDATORY_SECURITY_FLAGS`) so it cannot
silently regress. See docs/foundations/methodology-lock/CODING-EXEC-MODULE-SPEC.md.

`run_sandboxed` enforces the host-side "scream attack" defense: a generation that
spews endless output is bounded + killed so it cannot OOM the host harness process
even though the container's own memory is capped.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypedDict

OPT_IN_WARNING = (
    "coding-exec runs MODEL-GENERATED code inside a hardened, network-isolated Docker "
    "container on THIS machine. It is opt-in. See CODING-EXEC-MODULE-SPEC.md."
)

# Flags that MUST appear on every sandbox `docker run`. A test asserts each one is
# present so the hardening from the security red-team can never silently weaken.
MANDATORY_SECURITY_FLAGS: tuple[tuple[str, ...], ...] = (
    ("--rm",),
    ("--init",),                              # reap zombies + propagate SIGKILL on timeout
    ("--network", "none"),                    # no network from the executor
    ("--read-only",),                         # immutable rootfs
    ("--cap-drop", "ALL"),                    # drop every Linux capability
    ("--security-opt", "no-new-privileges"),  # block setuid escalation
    ("--ipc", "none"),                        # no shared IPC namespace
)


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """Resource caps for one sandboxed execution."""

    memory: str = "2g"
    cpus: str = "1.0"
    pids: int = 256
    tmpfs_size_mb: int = 64
    wall_clock_seconds: int = 30
    max_output_bytes: int = 5 * 1024 * 1024  # host-side truncation (the "scream" attack)
    user: str = "65534:65534"  # nobody:nogroup


def docker_run_argv(
    image_digest: str,
    command: Sequence[str],
    *,
    limits: SandboxLimits | None = None,
    read_only_mounts: Sequence[tuple[str, str]] = (),
    runtime: str | None = None,
) -> list[str]:
    """Build the hardened `docker run` argv. ALL hardening is default-on.

    `image_digest` must be a digest-pinned reference (`repo@sha256:...`).
    `read_only_mounts` are (host_src, container_dst) pairs mounted READ-ONLY — the only
    bind-mounts permitted; results leave via (bounded) stdout, never a writable mount.
    `runtime` optionally selects an extra-isolation runtime (e.g. "runsc"/gVisor on Linux).
    """
    limits = limits or SandboxLimits()
    argv: list[str] = [
        "docker", "run",
        "--rm",
        "--init",
        "--network", "none",
        "--read-only",
        "--ipc", "none",
        "--user", limits.user,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(limits.pids),
        "--memory", limits.memory,
        "--memory-swap", limits.memory,  # equal to --memory disables swap (no host disk thrash)
        "--cpus", limits.cpus,
        "--tmpfs", f"/tmp:rw,size={limits.tmpfs_size_mb}m,mode=1777",
    ]
    if runtime:
        argv += ["--runtime", runtime]
    for host_src, container_dst in read_only_mounts:
        argv += ["--volume", f"{host_src}:{container_dst}:ro"]
    argv += [image_digest, *command]
    return argv


@dataclass(frozen=True, slots=True)
class RawRunResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    truncated: bool = False


Runner = Callable[[list[str], float, int], RawRunResult]


class SandboxResult(TypedDict):
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool


def run_sandboxed(
    argv: list[str],
    *,
    limits: SandboxLimits | None = None,
    runner: Runner | None = None,
) -> SandboxResult:
    """Run a sandbox argv with a wall-clock timeout and BOUNDED output capture.

    The runner is injected so the orchestration is testable without Docker. Output is
    truncated to `limits.max_output_bytes` (defense-in-depth alongside the runner's own
    bounded read) and flagged, so a 'scream' generation can never OOM the host harness.
    """
    limits = limits or SandboxLimits()
    run = runner or default_runner
    raw = run(argv, float(limits.wall_clock_seconds), limits.max_output_bytes)
    cap = limits.max_output_bytes
    truncated = raw.truncated or len(raw.stdout) > cap or len(raw.stderr) > cap
    return {
        "exit_code": raw.exit_code,
        "stdout": raw.stdout[:cap].decode("utf-8", "replace"),
        "stderr": raw.stderr[:cap].decode("utf-8", "replace"),
        "timed_out": raw.timed_out,
        "output_truncated": truncated,
    }


def default_runner(argv: list[str], timeout_seconds: float, max_output_bytes: int) -> RawRunResult:
    """Real subprocess runner with a bounded streaming read + timeout kill.

    stderr is merged into stdout and read in a thread that stops + kills the process once
    `max_output_bytes` is reached, so endless output can't exhaust host memory. The main
    thread enforces the wall-clock timeout. Not unit-tested (needs Docker); exercised in
    the gated integration run.
    """
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buffer = bytearray()
    overflowed = threading.Event()

    def reader() -> None:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                return
            if len(buffer) < max_output_bytes:
                buffer.extend(chunk[: max_output_bytes - len(buffer)])
            else:
                overflowed.set()
                proc.kill()
                return

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        timed_out = True
    thread.join(timeout=5)
    exit_code = proc.returncode if proc.returncode is not None else -9
    return RawRunResult(
        exit_code=exit_code,
        stdout=bytes(buffer),
        stderr=b"",
        timed_out=timed_out,
        truncated=overflowed.is_set(),
    )
