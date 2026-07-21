from __future__ import annotations

import json
import sys
from collections.abc import Sequence

import pytest

import localbench.coding_exec.sandbox as sandbox_mod
from localbench._types import JsonValue
from localbench.coding_exec import (
    MANDATORY_SECURITY_FLAGS,
    DockerEnv,
    RawRunResult,
    SandboxLimits,
    default_runner,
    docker_run_argv,
    preflight_checks,
    probe_docker_env,
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
    available: bool = True,
) -> DockerEnv:
    return DockerEnv(
        platform=platform,
        desktop=desktop,
        rootless=rootless,
        runsc_available=runsc_available,
        runc_version=runc_version,
        available=available,
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


def test_docker_run_argv_rejects_unpinned_images() -> None:
    with pytest.raises(ValueError, match="digest-pinned"):
        docker_run_argv("ghcr.io/bigcode-project/evaluation-harness:latest", ["true"])


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


def test_preflight_blocks_when_docker_is_unavailable() -> None:
    result = preflight_checks(_env(platform="windows", available=False))

    assert result.ok is False
    assert result.blockers == ("Docker is unavailable; install and start Docker before benchmarking",)


def test_probe_marks_docker_unavailable_when_server_version_is_empty() -> None:
    env = probe_docker_env(lambda _argv: "")

    assert env.available is False


def test_probe_does_not_treat_docker_daemon_error_as_a_server_version() -> None:
    env = probe_docker_env(lambda _argv: "error during connect: Docker daemon is not running")

    assert env.available is False


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


def test_active_preflight_observes_every_container_control() -> None:
    report = _enforced_control_report()

    def runner(
        _argv: list[str],
        _timeout_seconds: float,
        _max_output_bytes: int,
        _stdin_bytes: bytes = b"",
    ) -> RawRunResult:
        return RawRunResult(
            exit_code=0,
            stdout=json.dumps(report).encode(),
            stderr=b"",
            timed_out=False,
        )

    result = sandbox_mod.preflight_sandbox_controls(
        _IMAGE,
        _env(platform="windows", desktop=True),
        runner=runner,
    )

    assert result.ok is True
    assert result.blockers == ()


def test_preflight_pulls_missing_image_before_running_tight_control_probe() -> None:
    # Given: the pinned evaluation image is absent from the Docker daemon.
    image_calls: list[tuple[list[str], float, bool]] = []
    probe_calls: list[tuple[list[str], float]] = []

    def image_runner(argv: list[str], timeout_seconds: float, passthrough: bool) -> RawRunResult:
        image_calls.append((argv, timeout_seconds, passthrough))
        return RawRunResult(
            exit_code=1 if argv[1:3] == ["image", "inspect"] else 0,
            stdout=b"",
            stderr=b"",
            timed_out=False,
        )

    def probe_runner(
        argv: list[str],
        timeout_seconds: float,
        _max_output_bytes: int,
        _stdin_bytes: bytes = b"",
    ) -> RawRunResult:
        probe_calls.append((argv, timeout_seconds))
        return RawRunResult(
            exit_code=0,
            stdout=json.dumps(_enforced_control_report()).encode(),
            stderr=b"",
            timed_out=False,
        )

    # When: sandbox controls are preflighted.
    result = sandbox_mod.preflight_sandbox_controls(
        _IMAGE,
        _env(platform="windows", desktop=True),
        runner=probe_runner,
        image_runner=image_runner,
    )

    # Then: inspect precedes a progress-passthrough pull, and only the probe gets the tight timeout.
    assert result.ok is True
    assert image_calls == [
        (["docker", "image", "inspect", _IMAGE], 10.0, False),
        (["docker", "pull", _IMAGE], 3600.0, True),
    ]
    assert len(probe_calls) == 1
    assert probe_calls[0][0][:2] == ["docker", "run"]
    assert probe_calls[0][1] == 10.0


def test_preflight_reports_image_pull_failure_separately_from_control_probe() -> None:
    # Given: image inspection misses and the explicit pull fails.
    def image_runner(argv: list[str], timeout_seconds: float, passthrough: bool) -> RawRunResult:
        return RawRunResult(
            exit_code=1,
            stdout=b"",
            stderr=b"registry unavailable",
            timed_out=False,
        )

    # When: sandbox controls are preflighted.
    result = sandbox_mod.preflight_sandbox_controls(
        _IMAGE,
        _env(platform="windows", desktop=True),
        runner=_fake(stdout=json.dumps(_enforced_control_report()).encode()),
        image_runner=image_runner,
    )

    # Then: the blocker identifies acquisition rather than misdiagnosing the control probe.
    assert result.ok is False
    assert result.blockers == (
        "sandbox image pull failed (exit=1, timed_out=False): registry unavailable",
    )
    assert "control probe" not in result.blockers[0]


def test_preflight_diagnoses_wsl2_localhost_attach_output_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a Windows client reaches Docker through the WSL2 localhost TCP relay.
    monkeypatch.setenv("DOCKER_HOST", "tcp://localhost:2375")

    # When: the control probe exits successfully but its attach stdout is empty.
    result = sandbox_mod.preflight_sandbox_controls(
        _IMAGE,
        _env(platform="windows", desktop=True),
        runner=_fake(stdout=b"", exit_code=0),
        image_runner=lambda argv, timeout_seconds, passthrough: RawRunResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            timed_out=False,
        ),
    )

    # Then: the diagnostic names the relay failure and the WSL adapter-IP remedy.
    assert result.ok is False
    assert result.blockers == (
        "sandbox control probe output-loss detected: Docker exited 0 with empty stdout; "
        "on Windows, the WSL2 localhost relay drops attach streams. Set DOCKER_HOST to the "
        "WSL adapter IP from `wsl hostname -I` instead of tcp://localhost or tcp://127.0.0.1",
    )


def test_preflight_uses_generic_attach_output_loss_diagnostic_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the control probe is not using the Windows-to-WSL localhost relay.
    monkeypatch.setenv("DOCKER_HOST", "tcp://172.24.64.1:2375")

    # When: Docker exits successfully without delivering probe stdout.
    result = sandbox_mod.preflight_sandbox_controls(
        _IMAGE,
        _env(platform="windows", desktop=True),
        runner=_fake(stdout=b"", exit_code=0),
        image_runner=lambda argv, timeout_seconds, passthrough: RawRunResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            timed_out=False,
        ),
    )

    # Then: the diagnostic remains transport-focused without blaming the localhost relay.
    assert result.blockers == (
        "sandbox control probe output-loss detected: Docker exited 0 with empty stdout; "
        "Docker attach output was not delivered; verify that the daemon transport carries attach streams",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uid", 0),
        ("rootfs_read_only", False),
        ("tmpfs", False),
        ("interfaces", ["eth0", "lo"]),
        ("cap_eff", 1),
        ("no_new_privs", 0),
        ("seccomp", 0),
        ("pids_max", 512),
        ("memory_max", None),
        ("cpu_quota", None),
    ],
)
def test_active_preflight_fails_closed_when_a_control_is_not_enforced(
    field: str,
    value: JsonValue,
) -> None:
    report = _enforced_control_report()
    report[field] = value

    def runner(
        _argv: list[str],
        _timeout_seconds: float,
        _max_output_bytes: int,
        _stdin_bytes: bytes = b"",
    ) -> RawRunResult:
        return RawRunResult(
            exit_code=0,
            stdout=json.dumps(report).encode(),
            stderr=b"",
            timed_out=False,
        )

    result = sandbox_mod.preflight_sandbox_controls(
        _IMAGE,
        _env(platform="windows", desktop=True),
        runner=runner,
    )

    assert result.ok is False
    assert any(field in blocker for blocker in result.blockers)


def test_preflight_has_no_unsafe_override() -> None:
    with pytest.raises(TypeError):
        preflight_checks(_env(runsc_available=False, rootless=False), allow_unsafe=True)


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


def test_docker_run_argv_rejects_all_host_mounts() -> None:
    with pytest.raises(ValueError, match="host mounts"):
        docker_run_argv(
            _IMAGE,
            ["python", "/work/run.py"],
            read_only_mounts=[("/host/gen.py", "/work/run.py")],
        )


def test_docker_run_argv_overrides_image_entrypoint() -> None:
    # The evaluation image ships its own ENTRYPOINT; without --entrypoint "" our runner argv
    # would be appended to it (running the image's evaluator on untrusted code, not ours).
    argv = docker_run_argv(_IMAGE, ["python", "/work/run.py"])
    assert _contains(argv, ["--entrypoint", ""])
    # The override sits in the docker-run flags, before the image digest.
    assert argv.index("--entrypoint") < argv.index(_IMAGE)


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


def test_default_runner_streams_stdin_without_a_host_mount() -> None:
    raw = default_runner(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        2.0,
        1024,
        b"task-json-over-stdin",
    )

    assert raw.exit_code == 0
    assert raw.stdout == b"task-json-over-stdin"
    assert raw.timed_out is False
    assert raw.truncated is False


def test_default_runner_force_kills_on_output_and_runtime_limits() -> None:
    output_limited = default_runner(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 10000); sys.stdout.flush()"],
        2.0,
        32,
    )
    timed = default_runner(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        0.05,
        1024,
    )

    assert output_limited.truncated is True
    assert len(output_limited.stdout) == 32
    assert output_limited.exit_code != 0
    assert timed.timed_out is True
    assert timed.exit_code != 0


def _fake(*, stdout: bytes = b"", stderr: bytes = b"", exit_code: int = 0, timed_out: bool = False, truncated: bool = False):
    def runner(
        argv: list[str],
        timeout_seconds: float,
        max_output_bytes: int,
        stdin_bytes: bytes,
    ) -> RawRunResult:
        return RawRunResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr, timed_out=timed_out, truncated=truncated
        )

    return runner


def _enforced_control_report() -> dict[str, JsonValue]:
    return {
        "uid": 65534,
        "rootfs_read_only": True,
        "tmpfs": True,
        "tmpfs_bytes": 64 * 1024 * 1024,
        "interfaces": ["lo"],
        "cap_eff": 0,
        "no_new_privs": 1,
        "seccomp": 2,
        "pids_max": 256,
        "memory_max": 2 * 1024 * 1024 * 1024,
        "cpu_quota": 100000,
        "cpu_period": 100000,
    }
