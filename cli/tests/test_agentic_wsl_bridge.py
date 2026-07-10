from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path, PurePosixPath
from typing import cast

import pytest

from localbench.scoring.agentic_exec import benchmark as appworld_bench
from localbench.scoring.agentic_exec.loop_types import FailureClass
from localbench.scoring.agentic_exec.sandbox import (
    SandboxError,
    SandboxTimeoutError,
    WorkerSetupError,
)
from localbench.scoring.agentic_exec.wsl_bridge import (
    WslSandboxProxy,
    WslWorkerConfig,
    _assert_identity,
    default_wsl_repo_path,
    provenance_from_identity,
    wsl_list_scored_task_ids,
    wsl_sandbox_factory,
)
from localbench.scoring.agentic_exec.wsl_process import worker_argv
from localbench.scoring.agentic_exec.worker_identity import worker_implementation_identity
from localbench.scoring.agentic_exec.wsl_worker import (
    FrameTooLargeError,
    decode_worker_frame,
    encode_worker_frame,
    handle_worker_message,
)


def test_worker_frame_round_trip_and_oversized_rejection() -> None:
    # Given: a small worker protocol message.
    message = {"op": "run_block", "code": "print(1)"}

    # When: encoding and decoding the NDJSON frame.
    frame = encode_worker_frame(message)
    decoded = decode_worker_frame(frame)

    # Then: the message round-trips as one newline-terminated frame and oversized frames fail closed.
    assert frame.endswith(b"\n")
    assert decoded == message
    with pytest.raises(FrameTooLargeError):
        encode_worker_frame({"op": "run_block", "code": "x" * (9 * 1024 * 1024)})


def test_local_worker_implementation_identity_hashes_installed_sources() -> None:
    identity = worker_implementation_identity()

    assert identity["localbench_distribution_version"] == "0.3.1"
    assert len(identity["worker_content_sha256"]) == 64
    module_hashes = identity["worker_module_sha256"]
    assert isinstance(module_hashes, dict)
    assert "localbench.scoring.agentic_exec.wsl_worker" in module_hashes
    assert "localbench.scoring.agentic_exec.sandbox" in module_hashes
    assert "localbench.scoring.agentic_exec.worker_identity" in module_hashes
    assert "localbench.scoring.agentic_exec.runner_bootstrap" in module_hashes
    assert "localbench.scoring.agentic_exec.task_pool" in module_hashes
    assert "localbench.scoring.agentic_exec.funnel" in module_hashes


def test_per_task_worker_identity_must_match_preflight(tmp_path: Path) -> None:
    script = _write_fake_worker(tmp_path)
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/private/source",
        venv_python="/managed/venv/bin/python3",
        appworld_root="/managed/appworld",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        op_timeout_s=2.0,
    )

    with pytest.raises(WorkerSetupError, match="per-task distribution version mismatch"):
        with WslSandboxProxy(
            "fac291d_1",
            config,
            expected_identity={
                "localbench_distribution_version": "0.3.1",
                "worker_content_sha256": "a" * 64,
            },
        ):
            pass


def test_worker_malformed_op_returns_protocol_error() -> None:
    # Given / When: a malformed request reaches the worker dispatcher.
    response, should_exit = handle_worker_message("not-a-json-object")

    # Then: the worker reports a protocol error instead of crashing.
    assert should_exit is False
    assert response["kind"] == "protocol_error"

    # Given / When: an unknown op reaches the worker dispatcher.
    response, should_exit = handle_worker_message({"op": "bogus"})

    # Then: unknown operations are rejected as protocol errors.
    assert should_exit is False
    assert response["kind"] == "protocol_error"
    assert "unknown op" in str(response["detail"])


def test_proxy_round_trip_and_list_tasks_through_fake_worker(tmp_path: Path) -> None:
    # Given: a fake worker subprocess speaking the same NDJSON protocol as the WSL worker.
    script = _write_fake_worker(tmp_path)
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/Users/Michael/local-bench-wt-agentic",
        venv_python="/home/michael/appworld-harness/venv/bin/python3",
        appworld_root="/home/michael/appworld-data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        op_timeout_s=2.0,
    )

    # When: the proxy opens a task, runs a block, finalizes, and asks for scored tasks.
    with WslSandboxProxy("fac291d_1", config) as sandbox:
        obs = sandbox.run_block("print(1)")
        verdict = sandbox.finalize({"answer": 1})
    task_ids = wsl_list_scored_task_ids(config)

    # Then: the proxy exposes the SandboxLike surface and captures stderr to a log file.
    assert obs.stdout == "ran: print(1)"
    assert obs.error is None
    assert verdict.success is True
    assert verdict.collateral_damage is False
    assert task_ids == ["fac291d_1", "50e1ac9_1"]
    assert any(path.name.endswith(".stderr.log") for path in tmp_path.iterdir())


def test_proxy_timeout_maps_to_infra_timeout(tmp_path: Path) -> None:
    # Given: a fake worker that accepts the task but hangs on one run_block request.
    script = _write_fake_worker(tmp_path)
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/Users/Michael/local-bench-wt-agentic",
        venv_python="/home/michael/appworld-harness/venv/bin/python3",
        appworld_root="/home/michael/appworld-data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        op_timeout_s=1.0,
    )

    # When: the proxy op times out.
    with WslSandboxProxy("fac291d_1", config) as sandbox:
        with pytest.raises(SandboxTimeoutError) as error:
            sandbox.run_block("hang")

    # Then: benchmark classification exposes the timeout through infra_timeout_rate diagnostics.
    assert appworld_bench._classify_harness_exception(error.value) is FailureClass.INFRA_TIMEOUT


def test_proxy_close_timeout_is_recorded_without_discarding_task_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _write_fake_worker(tmp_path)
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/repo",
        venv_python="/managed/venv/bin/python3",
        appworld_root="/managed/appworld",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        op_timeout_s=2.0,
    )
    proxy = WslSandboxProxy("fac291d_1", config)
    proxy.__enter__()

    def timeout_close(message, *, timeout_s: float):
        raise SandboxTimeoutError(f"close timed out after {timeout_s}s")

    monkeypatch.setattr(proxy, "_request", timeout_close)

    proxy.close()

    assert "close timed out" in (proxy.teardown_failure or "")


def test_proxy_close_process_exit_timeout_is_recorded_additively(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StuckProcess:
        def poll(self) -> None:
            return None

        def wait(self, timeout: float) -> None:
            raise subprocess.TimeoutExpired(cmd="wsl-worker", timeout=timeout)

    proxy = WslSandboxProxy(
        "fac291d_1",
        WslWorkerConfig(
            repo_root_wsl_path="/mnt/c/repo",
            venv_python="/managed/venv/bin/python3",
            appworld_root="/managed/appworld",
            log_dir=tmp_path,
        ),
    )
    proxy._proc = cast(subprocess.Popen[bytes], _StuckProcess())
    killed = False

    def acknowledge_close(message, *, timeout_s: float) -> dict[str, str]:
        return {"kind": "ok"}

    def record_kill() -> None:
        nonlocal killed
        killed = True

    monkeypatch.setattr(proxy, "_request", acknowledge_close)
    monkeypatch.setattr(proxy, "force_kill", record_kill)

    proxy.close()

    assert killed is True
    assert "did not exit" in (proxy.teardown_failure or "")


@pytest.mark.skipif(sys.platform != "win32", reason="taskkill process-tree assertion is Windows-only")
def test_proxy_force_kill_terminates_fake_worker_child(tmp_path: Path) -> None:
    # Given: a fake worker that starts a long-lived child process.
    script = _write_fake_worker(tmp_path)
    child_pid_file = tmp_path / "child.pid"
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/Users/Michael/local-bench-wt-agentic",
        venv_python="/home/michael/appworld-harness/venv/bin/python3",
        appworld_root="/home/michael/appworld-data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        worker_env={"LB_FAKE_CHILD_PID_FILE": str(child_pid_file)},
        op_timeout_s=2.0,
    )
    proxy = WslSandboxProxy("fac291d_1", config)

    # When: the proxy is entered and force-killed.
    proxy.__enter__()
    child_pid = _read_pid(child_pid_file)
    proxy.force_kill()

    # Then: the worker child is also gone.
    assert _eventually_dead(child_pid)


def test_proxy_enter_time_failure_raises_and_tears_down(tmp_path: Path) -> None:
    # Given: a worker that exits immediately, so the hello handshake in __enter__ fails.
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/x",
        venv_python="/x/py",
        appworld_root="/x/data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, "-c", "import sys; sys.exit(0)"),
        op_timeout_s=2.0,
    )
    proxy = WslSandboxProxy("fac291d_1", config)

    # When / Then: __enter__ fails closed (no hang) and cleans up rather than leaking the worker.
    # (Previously an enter-time hello/open_task failure skipped force_kill entirely, since __exit__
    # never runs when __enter__ raises.)
    with pytest.raises(SandboxError):
        proxy.__enter__()
    assert proxy._proc is None or proxy._proc.poll() is not None


def test_wsl_sandbox_factory_builds_proxy_context(tmp_path: Path) -> None:
    # Given: WSL bridge defaults plus a test launch argv.
    script = _write_fake_worker(tmp_path)

    # When: building the sandbox factory.
    factory = wsl_sandbox_factory(
        "/mnt/c/Users/Michael/local-bench-wt-agentic",
        "/home/michael/appworld-harness/venv/bin/python3",
        "/home/michael/appworld-data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
    )

    # Then: it yields a WslSandboxProxy context manager compatible with the benchmark seam.
    with factory("fac291d_1") as sandbox:
        assert sandbox.run_block("print(2)").stdout == "ran: print(2)"


def _write_fake_worker(tmp_path: Path) -> Path:
    script = tmp_path / "fake_worker.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import subprocess
            import sys
            import time

            child = None
            child_pid_file = os.environ.get("LB_FAKE_CHILD_PID_FILE")
            if child_pid_file:
                child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
                with open(child_pid_file, "w", encoding="utf-8") as handle:
                    handle.write(str(child.pid))

            def emit(payload):
                print(json.dumps(payload, separators=(",", ":")), flush=True)

            for raw in sys.stdin:
                req = json.loads(raw)
                op = req.get("op")
                if op == "hello":
                    print("fake stderr", file=sys.stderr, flush=True)
                    emit({
                        "kind": "ok",
                        "identity": {
                            "localbench_distribution_version": "0.3.0",
                            "worker_content_sha256": "f" * 64,
                            "worker_git_commit": "abc123",
                            "worker_dirty_tree": False,
                            "appworld_root": "/home/michael/appworld-data",
                            "appworld_root_under_mnt": False,
                            "bwrap_path": "/home/michael/.local/bin/bwrap",
                            "bwrap_version": "bwrap 0.9.0",
                        },
                    })
                elif op == "open_task":
                    emit({"kind": "ok"})
                elif op == "list_tasks":
                    emit({"kind": "ok", "task_ids": ["fac291d_1", "50e1ac9_1"]})
                elif op == "run_block":
                    if req.get("code") == "hang":
                        time.sleep(120)
                    emit({"kind": "ok", "stdout": f"ran: {req.get('code')}", "error": None})
                elif op == "finalize":
                    emit({
                        "kind": "ok",
                        "verdict": {
                            "success": True,
                            "collateral_damage": False,
                            "num_passes": 1,
                            "num_failures": 0,
                        },
                    })
                elif op == "close":
                    emit({"kind": "ok"})
                    break
                else:
                    emit({"kind": "protocol_error", "detail": "unknown op"})
            if child is not None and child.poll() is None:
                child.terminate()
            """
        ),
        encoding="utf-8",
    )
    return script


def _read_pid(path: Path) -> int:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if path.exists():
            return int(path.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError(f"pid file was not written: {path}")


def _eventually_dead(pid: int) -> bool:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.05)
    return not _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_request_timeout_kills_worker_fail_closed(tmp_path: Path) -> None:
    # Given: a fake worker that hangs on one run_block request.
    script = _write_fake_worker(tmp_path)
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/Users/Michael/local-bench-wt-agentic",
        venv_python="/home/michael/appworld-harness/venv/bin/python3",
        appworld_root="/home/michael/appworld-data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        op_timeout_s=0.1,
    )
    proxy = WslSandboxProxy("fac291d_1", config)
    proxy.__enter__()
    try:
        # When: the op times out.
        with pytest.raises(SandboxError):
            proxy.run_block("hang")
        # Then: the worker is killed immediately (fail closed). A late response from a
        # still-alive worker could pair with the NEXT request and desync every later read.
        assert proxy._proc is not None
        assert proxy._proc.poll() is not None
    finally:
        proxy.close()


def test_well_formed_error_response_keeps_worker_alive(tmp_path: Path) -> None:
    # Given: a live fake worker (its unknown-op branch answers protocol_error and keeps serving).
    script = _write_fake_worker(tmp_path)
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/Users/Michael/local-bench-wt-agentic",
        venv_python="/home/michael/appworld-harness/venv/bin/python3",
        appworld_root="/home/michael/appworld-data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        op_timeout_s=2.0,
    )
    with WslSandboxProxy("fac291d_1", config) as sandbox:
        # When: the worker answers a well-formed protocol_error.
        with pytest.raises(SandboxError):
            sandbox._request({"op": "bogus"}, timeout_s=2.0)
        # Then: the protocol is still in sync — worker alive, next request round-trips fine.
        assert sandbox._proc is not None
        assert sandbox._proc.poll() is None
        assert sandbox.run_block("print(3)").stdout == "ran: print(3)"


def test_proxy_finalization_provenance_is_the_shared_direct_finalize_descriptor(
    tmp_path: Path,
) -> None:
    # Given: a proxy (never entered — the descriptor is static).
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/x",
        venv_python="/x/py",
        appworld_root="/x/data",
        log_dir=tmp_path,
    )
    proxy = WslSandboxProxy("fac291d_1", config)

    # When / Then: it advertises the same descriptor as the WSL-side AppWorldSandbox.
    descriptor = proxy.finalization_provenance()
    assert descriptor["path"] == "orchestrator-direct-envhost-stdin-v1"
    assert descriptor["runner_in_verdict_path"] is False
    assert descriptor["finalize_correlation"] == "finalize_id+pinned_task+one_shot"


def test_provenance_from_identity_carries_direct_finalize_trust_note() -> None:
    # Given / When: run-level provenance built from a worker identity.
    prov = provenance_from_identity({
        "venv_path": "/x/venv",
        "venv_path_sha256": "1" * 64,
        "bwrap_path": "/x/bwrap",
        "bwrap_sha256": "2" * 64,
        "bwrap_version": "bwrap 0.9.0",
        "appworld_root": "/x/appworld",
        "appworld_root_path_sha256": "3" * 64,
        "localbench_distribution_version": "0.3.1",
        "worker_content_sha256": "4" * 64,
    })

    # Then: the agentic verdict-channel trust note is present and host-derived.
    channel = prov["agentic_verdict_channel"]
    assert channel["path"] == "orchestrator-direct-envhost-stdin-v1"
    assert channel["runner_in_verdict_path"] is False
    assert channel["trust_note"] == "host-derived+direct-finalize-v1"
    assert "venv_path" not in prov["wsl_identity"]
    assert "bwrap_path" not in prov["wsl_identity"]
    assert "appworld_root" not in prov["wsl_identity"]
    assert prov["agentic_sandbox_identity"]["bubblewrap_sha256"] == "2" * 64
    assert prov["agentic_sandbox_identity"]["appworld_root_path_sha256"] == "3" * 64
    assert prov["wsl_identity"]["localbench_distribution_version"] == "0.3.1"
    assert prov["wsl_identity"]["worker_content_sha256"] == "4" * 64


def test_worker_identity_gate_compares_distribution_version_and_content_digest() -> None:
    expected = {
        "localbench_distribution_version": "0.3.1",
        "worker_content_sha256": "a" * 64,
    }
    base = {
        "appworld_root_under_mnt": False,
        "bwrap_path": "/managed/bwrap",
        **expected,
    }

    _assert_identity(base, expected)
    with pytest.raises(SandboxError, match="distribution version mismatch"):
        _assert_identity({**base, "localbench_distribution_version": "0.3.0"}, expected)
    with pytest.raises(SandboxError, match="worker content digest mismatch"):
        _assert_identity({**base, "worker_content_sha256": "b" * 64}, expected)


def test_managed_worker_argv_uses_installed_package_without_source_checkout() -> None:
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/private/source-checkout",
        venv_python="/managed/venv/bin/python3",
        appworld_root="/managed/appworld",
    )

    command = worker_argv(config)[-1]

    assert "/mnt/c/private/source-checkout" not in command
    assert "PYTHONPATH=" not in command
    assert "-m localbench.scoring.agentic_exec.wsl_worker" in command


def test_default_wsl_repo_path_rejects_non_drive_colon_paths() -> None:
    class _NonDrivePath:
        def resolve(self) -> PurePosixPath:
            return PurePosixPath("/srv/localbench")

    with pytest.raises(SandboxError, match="non-drive-colon"):
        default_wsl_repo_path(cast(Path, _NonDrivePath()))
