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

import json
import re
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Final, TypedDict

from localbench._types import JsonObject, JsonValue

OPT_IN_WARNING = (
    "This benchmark executes model-generated code on this machine inside a restricted "
    "Docker container. The container blocks network access and limits privileges, files, "
    "processes, memory, CPU, runtime, and output, but generated code still carries risk."
)

# Flags that MUST appear on every sandbox `docker run`. A test asserts each one is
# present so the hardening from the security red-team can never silently weaken.
MANDATORY_SECURITY_FLAGS: tuple[tuple[str, ...], ...] = (
    ("--rm",),
    ("--init",),                              # reap zombies + propagate SIGKILL on timeout
    ("--interactive",),                       # task JSON enters over stdin; no host bind mount
    ("--network", "none"),                    # no network from the executor
    ("--read-only",),                         # immutable rootfs
    ("--cap-drop", "ALL"),                    # drop every Linux capability
    ("--security-opt", "no-new-privileges"),  # block setuid escalation
    ("--ipc", "none"),                        # no shared IPC namespace
    ("--log-driver", "none"),                 # dockerd's own log file is NOT bounded by our stdout reader
    ("--ulimit", "core=0:0"),                 # no core dumps (large + leak in-memory data)
)

_IMAGE_DIGEST_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}")
_CONTROL_PROBE: Final = r"""
import json
import os
import socket

def read_first(paths):
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            pass
    return None

def number(value):
    try:
        return int(value) if value not in (None, "max") else None
    except ValueError:
        return None

def mount(path):
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as handle:
            for line in handle:
                before, after = line.split(" - ", 1)
                fields = before.split()
                if fields[4] == path:
                    return fields[5].split(","), after.split()[0]
    except OSError:
        pass
    return [], None

status = {}
try:
    with open("/proc/self/status", encoding="utf-8") as handle:
        for line in handle:
            key, _, value = line.partition(":")
            status[key] = value.strip()
except OSError:
    pass

root_options, _ = mount("/")
_, tmp_type = mount("/tmp")
cpu_max = read_first(["/sys/fs/cgroup/cpu.max"])
if cpu_max:
    quota_text, period_text = cpu_max.split()
else:
    quota_text = read_first(["/sys/fs/cgroup/cpu/cpu.cfs_quota_us"])
    period_text = read_first(["/sys/fs/cgroup/cpu/cpu.cfs_period_us"])
tmp_stat = os.statvfs("/tmp")
print(json.dumps({
    "uid": os.geteuid(),
    "rootfs_read_only": "ro" in root_options,
    "tmpfs": tmp_type == "tmpfs",
    "tmpfs_bytes": tmp_stat.f_frsize * tmp_stat.f_blocks,
    "interfaces": sorted(name for _, name in socket.if_nameindex()),
    "cap_eff": int(status.get("CapEff", "-1"), 16),
    "no_new_privs": number(status.get("NoNewPrivs")),
    "seccomp": number(status.get("Seccomp")),
    "pids_max": number(read_first(["/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max"])),
    "memory_max": number(read_first(["/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"])),
    "cpu_quota": number(quota_text),
    "cpu_period": number(period_text),
}))
"""


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
    `read_only_mounts` is retained only to reject legacy callers; host bind mounts are
    forbidden. Task data enters over stdin and results leave via bounded stdout.
    `runtime` optionally selects an extra-isolation runtime (e.g. "runsc"/gVisor on Linux).
    """
    limits = limits or SandboxLimits()
    if _IMAGE_DIGEST_RE.fullmatch(image_digest) is None:
        raise ValueError("sandbox image must be digest-pinned as repo@sha256:<64 lowercase hex>")
    if read_only_mounts:
        raise ValueError("sandbox host mounts are forbidden, including the Docker socket")
    uid = limits.user.split(":", 1)[0]
    if not uid.isdigit() or uid == "0":
        raise ValueError("sandbox user must be a non-root numeric uid")
    fsize_bytes = limits.tmpfs_size_mb * 1024 * 1024
    argv: list[str] = [
        "docker", "run",
        "--rm",
        "--init",
        "--interactive",
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


def preflight_checks(env: DockerEnv) -> PreflightResult:
    """Decide whether it is safe to execute untrusted model code, and pick the runtime.

    Posture locked after the dual security red-team (GPT-5.5 + Gemini 3.1 Pro, 2026-06-19):
    a SECOND isolation boundary is required on Linux because rootful Docker shares the host
    kernel — no combination of capability drops compensates for that. So we FAIL CLOSED on
    rootful bare-Linux Docker with neither gVisor nor rootless. Mac/Windows get the Docker
    Desktop VM boundary for free.
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
        blockers.append(
            "rootful bare-Linux Docker shares the host kernel with no second isolation boundary; "
            "install gVisor (runsc) or use rootless Docker"
        )

    # 2. runc CVE floor — only bites where runc is the executing runtime sharing the HOST kernel:
    #    native Linux AND not gVisor. (gVisor replaces runc; Desktop runs runc inside the VM.)
    if (
        env.runc_version is not None
        and env.runc_version < MIN_SAFE_RUNC
        and native_linux
        and runtime != "runsc"
    ):
        blockers.append(
            f"runc {'.'.join(map(str, env.runc_version))} < safe floor "
            f"{'.'.join(map(str, MIN_SAFE_RUNC))} (CVE-2024-21626 host-fd-leak escape)"
        )

    return PreflightResult(ok=not blockers, runtime=runtime, warnings=tuple(warnings), blockers=tuple(blockers))


def preflight_sandbox_controls(
    image_digest: str,
    env: DockerEnv,
    *,
    limits: SandboxLimits | None = None,
    runtime: str | None = None,
    runner: Runner | None = None,
) -> PreflightResult:
    """Launch a constrained container and verify the kernel-enforced sandbox controls."""
    host = preflight_checks(env)
    if not host.ok:
        return host
    active_limits = limits or SandboxLimits()
    selected_runtime = runtime or host.runtime
    probe_limits = replace(
        active_limits,
        wall_clock_seconds=min(active_limits.wall_clock_seconds, 10),
        max_output_bytes=min(active_limits.max_output_bytes, 65_536),
    )
    try:
        argv = docker_run_argv(
            image_digest,
            ["python", "-c", _CONTROL_PROBE],
            limits=probe_limits,
            runtime=selected_runtime,
        )
        result = run_sandboxed(argv, limits=probe_limits, runner=runner)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return PreflightResult(
            ok=False,
            runtime=selected_runtime,
            warnings=host.warnings,
            blockers=(f"sandbox control probe could not start: {error}",),
        )
    if result["timed_out"] or result["output_truncated"] or result["exit_code"] != 0:
        return PreflightResult(
            ok=False,
            runtime=selected_runtime,
            warnings=host.warnings,
            blockers=(
                "sandbox control probe failed "
                f"(exit={result['exit_code']}, timed_out={result['timed_out']}, "
                f"output_truncated={result['output_truncated']}): "
                f"{result['stderr'][:300] or result['stdout'][:300]}",
            ),
        )
    try:
        parsed: JsonValue = json.loads(result["stdout"])
    except json.JSONDecodeError as error:
        return PreflightResult(
            ok=False,
            runtime=selected_runtime,
            warnings=host.warnings,
            blockers=(f"sandbox control probe returned invalid JSON: {error}",),
        )
    if not isinstance(parsed, dict):
        return PreflightResult(
            ok=False,
            runtime=selected_runtime,
            warnings=host.warnings,
            blockers=("sandbox control probe returned a non-object report",),
        )
    blockers = _control_report_blockers(dict(parsed), active_limits)
    return PreflightResult(
        ok=not blockers,
        runtime=selected_runtime,
        warnings=host.warnings,
        blockers=tuple(blockers),
    )


def _control_report_blockers(report: JsonObject, limits: SandboxLimits) -> list[str]:
    blockers: list[str] = []
    expected_uid = int(limits.user.split(":", 1)[0])
    expected_memory = _docker_memory_bytes(limits.memory)
    expected_cpu = _positive_float(limits.cpus)
    checks = (
        ("uid", report.get("uid") == expected_uid),
        ("rootfs_read_only", report.get("rootfs_read_only") is True),
        ("tmpfs", report.get("tmpfs") is True),
        (
            "tmpfs_bytes",
            _bounded_positive_int(report.get("tmpfs_bytes"), limits.tmpfs_size_mb * 1024 * 1024),
        ),
        ("interfaces", report.get("interfaces") == ["lo"]),
        ("cap_eff", report.get("cap_eff") == 0),
        ("no_new_privs", report.get("no_new_privs") == 1),
        ("seccomp", report.get("seccomp") == 2),
        ("pids_max", _bounded_positive_int(report.get("pids_max"), limits.pids)),
        (
            "memory_max",
            expected_memory is not None
            and _bounded_positive_int(report.get("memory_max"), expected_memory),
        ),
        ("cpu_quota", _cpu_is_bounded(report, expected_cpu)),
    )
    blockers.extend(
        f"sandbox control not enforced: {field}={report.get(field)!r}"
        for field, enforced in checks
        if not enforced
    )
    return blockers


def _bounded_positive_int(value: JsonValue | None, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= maximum


def _docker_memory_bytes(value: str) -> int | None:
    match = re.fullmatch(r"([1-9][0-9]*)([bkmg])?", value.lower())
    if match is None:
        return None
    units = {None: 1, "b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
    return int(match[1]) * units[match[2]]


def _positive_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _cpu_is_bounded(report: JsonObject, maximum: float | None) -> bool:
    quota = report.get("cpu_quota")
    period = report.get("cpu_period")
    if (
        maximum is None
        or not isinstance(quota, int)
        or isinstance(quota, bool)
        or not isinstance(period, int)
        or isinstance(period, bool)
        or quota <= 0
        or period <= 0
    ):
        return False
    return quota / period <= maximum


def probe_docker_env(run_text: Callable[[list[str]], str] | None = None) -> DockerEnv:
    """Best-effort gather of host Docker facts for `preflight_checks`. Shells out to
    `docker`/`runc`; NOT unit-tested (needs Docker) — the decision logic in
    `preflight_checks` is. Any probe failure degrades to the conservative value
    (unknown runc version, no gVisor) so preflight errs toward fail-closed.
    """
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


Runner = Callable[[list[str], float, int, bytes], RawRunResult]


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
    stdin_bytes: bytes = b"",
) -> SandboxResult:
    """Run a sandbox argv with a wall-clock timeout and BOUNDED output capture.

    The runner is injected so the orchestration is testable without Docker. Output is
    truncated to `limits.max_output_bytes` (defense-in-depth alongside the runner's own
    bounded read) and flagged, so a 'scream' generation can never OOM the host harness.
    """
    limits = limits or SandboxLimits()
    run = runner or default_runner
    raw = run(argv, float(limits.wall_clock_seconds), limits.max_output_bytes, stdin_bytes)
    cap = limits.max_output_bytes
    truncated = raw.truncated or len(raw.stdout) > cap or len(raw.stderr) > cap
    return {
        "exit_code": raw.exit_code,
        "stdout": raw.stdout[:cap].decode("utf-8", "replace"),
        "stderr": raw.stderr[:cap].decode("utf-8", "replace"),
        "timed_out": raw.timed_out,
        "output_truncated": truncated,
    }


def default_runner(
    argv: list[str],
    timeout_seconds: float,
    max_output_bytes: int,
    stdin_bytes: bytes = b"",
) -> RawRunResult:
    """Real subprocess runner with a bounded streaming read + timeout kill.

    stderr is merged into stdout and read in a thread that stops + kills the process once
    `max_output_bytes` is reached, so endless output can't exhaust host memory. The main
    thread enforces the wall-clock timeout. Unit tests exercise the process boundary with
    harmless local subprocesses; Docker itself stays outside the automated test suite.
    """
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    buffer = bytearray()
    overflowed = threading.Event()

    def reader() -> None:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                return
            remaining = max_output_bytes - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
            if len(chunk) > remaining or remaining <= 0:
                overflowed.set()
                proc.kill()
                return

    def writer() -> None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(stdin_bytes)
            proc.stdin.close()
        except BrokenPipeError:
            return

    reader_thread = threading.Thread(target=reader, daemon=True)
    writer_thread = threading.Thread(target=writer, daemon=True)
    reader_thread.start()
    writer_thread.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        timed_out = True
    reader_thread.join(timeout=5)
    writer_thread.join(timeout=5)
    exit_code = -9 if overflowed.is_set() else (proc.returncode if proc.returncode is not None else -9)
    return RawRunResult(
        exit_code=exit_code,
        stdout=bytes(buffer),
        stderr=b"",
        timed_out=timed_out,
        truncated=overflowed.is_set(),
    )
