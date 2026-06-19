from __future__ import annotations

from collections.abc import Sequence

from localbench.coding_exec import (
    MANDATORY_SECURITY_FLAGS,
    RawRunResult,
    SandboxLimits,
    docker_run_argv,
    run_sandboxed,
)

_IMAGE = "ghcr.io/bigcode-project/evaluation-harness@sha256:" + "a" * 64


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
