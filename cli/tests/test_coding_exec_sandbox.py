from __future__ import annotations

from collections.abc import Sequence

from localbench.coding_exec import (
    MANDATORY_SECURITY_FLAGS,
    DockerEnv,
    RawRunResult,
    SandboxLimits,
    docker_run_argv,
    preflight_checks,
    run_sandboxed,
)

_IMAGE = "ghcr.io/bigcode-project/evaluation-harness@sha256:" + "a" * 64


def _env(
    *,
    platform: str = "linux",
    desktop: bool = False,
    rootless: bool = False,
    runsc_available: bool = False,
    runc_version: tuple[int, int, int] | None = (1, 2, 0),
) -> DockerEnv:
    return DockerEnv(
        platform=platform,
        desktop=desktop,
        rootless=rootless,
        runsc_available=runsc_available,
        runc_version=runc_version,
    )


def _contains(argv: Sequence[str], seq: Sequence[str]) -> bool:
    n = len(seq)
    return any(tuple(argv[i : i + n]) == tuple(seq) for i in range(len(argv) - n + 1))


def test_docker_run_argv_includes_every_mandatory_security_flag() -> None:
    # The regression guard: the locked hardening (security red-team, 2026-06-19) must
    # appear on every sandbox run, so it can't silently weaken.
    argv = docker_run_argv(_IMAGE, ["python", "-c", "print(1)"])
    for flag in MANDATORY_SECURITY_FLAGS:
        assert _contains(argv, flag), f"missing mandatory hardening flag: {flag}"


def test_docker_run_argv_disables_swap_and_bounds_tmpfs() -> None:
    argv = docker_run_argv(_IMAGE, ["true"], limits=SandboxLimits(memory="1g", tmpfs_size_mb=32))
    # --memory-swap == --memory disables swap (no host disk thrash from a generation).
    assert _contains(argv, ["--memory", "1g"])
    assert _contains(argv, ["--memory-swap", "1g"])
    # tmpfs scratch is size-bounded (unbounded tmpfs can eat 50% of host RAM).
    assert _contains(argv, ["--tmpfs", "/tmp:rw,size=32m,mode=1777"])


def test_docker_run_argv_caps_resources_and_runs_nonroot() -> None:
    argv = docker_run_argv(_IMAGE, ["true"], limits=SandboxLimits(cpus="0.5", pids=128, user="65534:65534"))
    assert _contains(argv, ["--cpus", "0.5"])
    assert _contains(argv, ["--pids-limit", "128"])
    assert _contains(argv, ["--user", "65534:65534"])


def test_docker_run_argv_sets_ulimits_and_disables_logging() -> None:
    # GPT-5.5 review additions: cgroup caps don't cover FD-exhaustion, core dumps, or
    # dockerd's own log growth — these ulimits + log-driver close those gaps.
    argv = docker_run_argv(_IMAGE, ["true"], limits=SandboxLimits(nofile=512, tmpfs_size_mb=32))
    assert _contains(argv, ["--log-driver", "none"])
    assert _contains(argv, ["--ulimit", "nofile=512:512"])
    assert _contains(argv, ["--ulimit", "core=0:0"])
    # fsize ulimit (bytes) is pinned to the tmpfs scratch size (32 MiB here).
    assert _contains(argv, ["--ulimit", f"fsize={32 * 1024 * 1024}:{32 * 1024 * 1024}"])


def test_docker_run_argv_never_allocates_a_tty() -> None:
    # A TTY/console widens runtime attack surface (e.g. CVE-2025-52565 /dev/console handling).
    argv = docker_run_argv(_IMAGE, ["true"])
    assert "-t" not in argv
    assert "--tty" not in argv


def test_preflight_blocks_rootful_bare_linux_without_a_second_boundary() -> None:
    # The single biggest red-team finding: rootful Docker shares the host kernel, so with
    # neither gVisor nor rootless we must FAIL CLOSED rather than run untrusted code.
    result = preflight_checks(_env(runsc_available=False, rootless=False))
    assert result.ok is False
    assert result.runtime is None
    assert any("rootful" in b for b in result.blockers)


def test_preflight_selects_gvisor_runtime_when_available() -> None:
    result = preflight_checks(_env(runsc_available=True))
    assert result.ok is True
    assert result.runtime == "runsc"


def test_preflight_allows_rootless_linux_without_gvisor() -> None:
    result = preflight_checks(_env(rootless=True))
    assert result.ok is True
    assert result.runtime is None
    assert result.blockers == ()


def test_preflight_passes_on_docker_desktop_vm_boundary() -> None:
    for env in (_env(platform="darwin"), _env(platform="windows"), _env(desktop=True)):
        result = preflight_checks(env)
        assert result.ok is True
        assert result.runtime is None


def test_preflight_override_downgrades_blocker_to_warning() -> None:
    result = preflight_checks(_env(runsc_available=False, rootless=False), allow_unsafe=True)
    assert result.ok is True
    assert any("OVERRIDE" in w for w in result.warnings)


def test_preflight_blocks_vulnerable_runc_on_native_linux() -> None:
    # runc below the CVE-2024-21626 floor is a host escape when runc is the executing runtime.
    result = preflight_checks(_env(rootless=True, runc_version=(1, 1, 0)))
    assert result.ok is False
    assert any("runc" in b for b in result.blockers)


def test_preflight_does_not_block_vulnerable_runc_under_gvisor() -> None:
    # gVisor replaces runc, so a stale runc is not the executing runtime → not a blocker.
    result = preflight_checks(_env(runsc_available=True, runc_version=(1, 1, 0)))
    assert result.ok is True
    assert result.runtime == "runsc"


def test_docker_run_argv_adds_gvisor_runtime_when_requested() -> None:
    argv = docker_run_argv(_IMAGE, ["true"], runtime="runsc")
    assert _contains(argv, ["--runtime", "runsc"])
    # Default (no runtime) must NOT carry a runtime flag.
    assert "--runtime" not in docker_run_argv(_IMAGE, ["true"])


def test_docker_run_argv_mounts_are_read_only_and_image_command_last() -> None:
    argv = docker_run_argv(
        _IMAGE,
        ["python", "/work/run.py"],
        read_only_mounts=[("/host/gen.py", "/work/run.py")],
    )
    assert _contains(argv, ["--volume", "/host/gen.py:/work/run.py:ro"])
    # The image digest then the command come last (nothing executes before the sandbox flags).
    assert argv[-3:] == [_IMAGE, "python", "/work/run.py"]
    assert all(not part.endswith(":rw") for part in argv)


def test_run_sandboxed_truncates_oversized_output_against_the_scream_attack() -> None:
    limits = SandboxLimits(max_output_bytes=10)
    runner = _fake(stdout=b"x" * 5000)
    result = run_sandboxed(["docker", "run"], limits=limits, runner=runner)
    assert len(result["stdout"]) == 10
    assert result["output_truncated"] is True


def test_run_sandboxed_honors_runner_truncation_flag_even_under_cap() -> None:
    # The real runner caps its buffer AT the limit and signals overflow separately.
    runner = _fake(stdout=b"x" * 3, truncated=True)
    result = run_sandboxed(["docker", "run"], limits=SandboxLimits(max_output_bytes=10), runner=runner)
    assert result["output_truncated"] is True


def test_run_sandboxed_maps_timeout_and_exit_code() -> None:
    runner = _fake(stdout=b"boom", exit_code=137, timed_out=True)
    result = run_sandboxed(["docker", "run"], runner=runner)
    assert result["timed_out"] is True
    assert result["exit_code"] == 137
    assert result["stdout"] == "boom"
    assert result["output_truncated"] is False


def _fake(*, stdout: bytes = b"", stderr: bytes = b"", exit_code: int = 0, timed_out: bool = False, truncated: bool = False):
    def runner(argv: list[str], timeout_seconds: float, max_output_bytes: int) -> RawRunResult:
        return RawRunResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr, timed_out=timed_out, truncated=truncated
        )

    return runner
