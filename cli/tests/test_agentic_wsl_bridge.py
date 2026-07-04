from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from localbench.scoring.agentic_exec import benchmark as appworld_bench
from localbench.scoring.agentic_exec.loop_types import FailureClass
from localbench.scoring.agentic_exec.sandbox import SandboxError
from localbench.scoring.agentic_exec.wsl_bridge import (
    WslSandboxProxy,
    WslWorkerConfig,
    provenance_from_identity,
    wsl_list_scored_task_ids,
    wsl_sandbox_factory,
)
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


def test_proxy_timeout_maps_to_infra_sandbox(tmp_path: Path) -> None:
    # Given: a fake worker that accepts the task but hangs on one run_block request.
    script = _write_fake_worker(tmp_path)
    config = WslWorkerConfig(
        repo_root_wsl_path="/mnt/c/Users/Michael/local-bench-wt-agentic",
        venv_python="/home/michael/appworld-harness/venv/bin/python3",
        appworld_root="/home/michael/appworld-data",
        log_dir=tmp_path,
        worker_argv=(sys.executable, str(script)),
        op_timeout_s=0.1,
    )

    # When: the proxy op times out.
    with WslSandboxProxy("fac291d_1", config) as sandbox:
        with pytest.raises(SandboxError) as error:
            sandbox.run_block("hang")

    # Then: benchmark classification sees an INFRA_SANDBOX harness failure, not model failure.
    assert appworld_bench._classify_harness_exception(error.value) is FailureClass.INFRA_SANDBOX


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
    prov = provenance_from_identity({"bwrap_path": "/x/bwrap", "bwrap_version": "bwrap 0.9.0"})

    # Then: the agentic verdict-channel trust note is present and host-derived.
    channel = prov["agentic_verdict_channel"]
    assert channel["path"] == "orchestrator-direct-envhost-stdin-v1"
    assert channel["runner_in_verdict_path"] is False
    assert channel["trust_note"] == "host-derived+direct-finalize-v1"
