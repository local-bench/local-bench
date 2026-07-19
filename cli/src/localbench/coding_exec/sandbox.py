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
    ("--log-driver", "none"),                 # dockerd's own log file is NOT bounded by our stdout reader
    ("--ulimit", "core=0:0"),                 # no core dumps (large + leak in-memory data)
)


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """Resource caps for one sandboxed execution."""

    memory: str = "2g"
    cpus: str = "1.0"
    pids: int = 256
    tmpfs_size_mb: int = 64
    nofile: int = 1024  # max open file descriptors (FD-exhaustion DoS); generous so legit code doesn't false-fail
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
    fsize_bytes = limits.tmpfs_size_mb * 1024 * 1024
    argv: list[str] = [
        "docker", "run",
        "--rm",
        "--init",
        "--network", "none",
        "--read-only",
        "--ipc", "none",
        "--log-driver", "none",  # dockerd's own log file isn't bounded by our stdout reader
        "--user", limits.user,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(limits.pids),
        "--memory", limits.memory,
        "--memory-swap", limits.memory,  # equal to --memory disables swap (no host disk thrash)
        "--cpus", limits.cpus,
        "--tmpfs", f"/tmp:rw,size={limits.tmpfs_size_mb}m,mode=1777",
        # ulimits the cgroup caps don't cover (process count IS covered by --pids-limit, so no
        # --ulimit nproc here: RLIMIT_NPROC is per-host-uid and would false-fail legit code).
        "--ulimit", f"nofile={limits.nofile}:{limits.nofile}",  # FD-exhaustion DoS
        "--ulimit", f"fsize={fsize_bytes}:{fsize_bytes}",       # max single file = scratch size
        "--ulimit", "core=0:0",                                 # no core dumps
    ]
    if runtime:
        argv += ["--runtime", runtime]
    # Clear the image's own ENTRYPOINT so `command` runs verbatim. The bigcodebench-evaluate
    # image ships ENTRYPOINT=[python3 -m bigcodebench.evaluate]; without this override our
    # runner argv would be appended to THAT (running the image's evaluator on untrusted input,
    # not our hardened runner). We use the image only as a pinned Python+deps environment.
    argv += ["--entrypoint", ""]
    for host_src, container_dst in read_only_mounts:
        argv += ["--volume", f"{host_src}:{container_dst}:ro"]
    argv += [image_digest, *command]
    return argv


# runc below this floor is vulnerable to CVE-2024-21626 (host-fd leak → container escape).
# The 2025 runc advisories (CVE-2025-31133/-52565/-52881) want 1.2.8 / 1.3.3 / 1.4.0-rc.3;
# we encode the single hard floor here and warn to upgrade above it.
MIN_SAFE_RUNC: tuple[int, int, int] = (1, 1, 12)


@dataclass(frozen=True, slots=True)
class DockerEnv:
    """Host Docker facts the preflight needs. Gathered by `probe_docker_env` (which shells
    out to Docker) and injected, so the decision logic stays testable without Docker."""

    platform: str  # "linux" | "darwin" | "windows"
    desktop: bool  # Docker Desktop (Mac/Win/desktop-linux) → containers run in a Linux VM first
    rootless: bool  # rootless Docker or userns-remap active
    runsc_available: bool  # gVisor ("runsc") registered as a Docker runtime
    runc_version: tuple[int, int, int] | None  # None = couldn't determine
    available: bool = True


@dataclass(frozen=True, slots=True)
class PreflightResult:
    ok: bool
    runtime: str | None  # runtime to hand docker_run_argv ("runsc" or None)
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]  # non-empty iff not ok


def preflight_checks(env: DockerEnv, *, allow_unsafe: bool = False) -> PreflightResult:
    """Decide whether it is safe to execute untrusted model code, and pick the runtime.

    Posture locked after the dual security red-team (GPT-5.5 + Gemini 3.1 Pro, 2026-06-19):
    a SECOND isolation boundary is required on Linux because rootful Docker shares the host
    kernel — no combination of capability drops compensates for that. So we FAIL CLOSED on
    rootful bare-Linux Docker with neither gVisor nor rootless, unless the user passes an
    explicit override. Mac/Windows get the Docker Desktop VM boundary for free.
    """
    warnings: list[str] = []
    blockers: list[str] = []
    runtime: str | None = None
    if not env.available:
        return PreflightResult(
            ok=False,
            runtime=None,
            warnings=(),
            blockers=("Docker is unavailable; install and start Docker before benchmarking",),
        )
    native_linux = env.platform == "linux" and not env.desktop

    # 1. Second-boundary decision + runtime selection.
    if not native_linux:
        warnings.append("Docker Desktop / non-Linux VM boundary present (an escape lands in the VM first)")
    elif env.runsc_available:
        runtime = "runsc"
        warnings.append("gVisor (runsc) active — recommended second boundary")
    elif env.rootless:
        warnings.append("rootless Docker / userns-remap active (reduced kernel exposure; gVisor still preferred)")
    else:
        msg = (
            "rootful bare-Linux Docker shares the host kernel with no second isolation boundary; "
            "install gVisor (runsc) or use rootless Docker, or pass the explicit override to accept the risk"
        )
        (warnings if allow_unsafe else blockers).append(("OVERRIDE: " + msg) if allow_unsafe else msg)

    # 2. runc CVE floor — only bites where runc is the executing runtime sharing the HOST kernel:
    #    native Linux AND not gVisor. (gVisor replaces runc; Desktop runs runc inside the VM.)
    if (
        env.runc_version is not None
        and env.runc_version < MIN_SAFE_RUNC
        and native_linux
        and runtime != "runsc"
    ):
        msg = (
            f"runc {'.'.join(map(str, env.runc_version))} < safe floor "
            f"{'.'.join(map(str, MIN_SAFE_RUNC))} (CVE-2024-21626 host-fd-leak escape)"
        )
        (warnings if allow_unsafe else blockers).append(msg)

    return PreflightResult(ok=not blockers, runtime=runtime, warnings=tuple(warnings), blockers=tuple(blockers))


def probe_docker_env(run_text: Callable[[list[str]], str] | None = None) -> DockerEnv:
    """Best-effort gather of host Docker facts for `preflight_checks`. Shells out to
    `docker`/`runc`; NOT unit-tested (needs Docker) — the decision logic in
    `preflight_checks` is. Any probe failure degrades to the conservative value
    (unknown runc version, no gVisor) so preflight errs toward fail-closed.
    """
    import re
    import sys

    run = run_text or _probe_run_text
    raw = sys.platform
    platform = (
        "linux" if raw.startswith("linux")
        else "darwin" if raw == "darwin"
        else "windows" if raw.startswith("win")
        else raw
    )
    server_version = run(["docker", "version", "--format", "{{.Server.Version}}"])
    info = run(["docker", "info", "--format", "{{json .}}"])
    desktop = "Docker Desktop" in info or "desktop-linux" in info
    rootless = "rootless" in info.lower()
    runtimes = run(["docker", "info", "--format", "{{json .Runtimes}}"])
    runsc_available = "runsc" in runtimes
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", run(["runc", "--version"]))
    runc_version = (int(match[1]), int(match[2]), int(match[3])) if match else None
    return DockerEnv(
        platform=platform,
        desktop=desktop,
        rootless=rootless,
        runsc_available=runsc_available,
        runc_version=runc_version,
        available=re.fullmatch(r"\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?", server_version.strip()) is not None,
    )


def _probe_run_text(argv: list[str]) -> str:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=10)  # noqa: S603
        return (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


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
