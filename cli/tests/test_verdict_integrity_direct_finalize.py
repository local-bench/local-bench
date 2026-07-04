"""Unit tests for orchestrator-direct AppWorld finalization.

These tests are intentionally host-agnostic: no AppWorld import, no bwrap, no WSL.
They exercise the trusted-channel contracts with fake env-host worlds and fake subprocess pipes.
"""

from __future__ import annotations

import io
import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))

from localbench.scoring.agentic_exec import env_host  # noqa: E402
from localbench.scoring.agentic_exec import runner_bootstrap as rb  # noqa: E402
from localbench.scoring.agentic_exec import sandbox as sandbox_mod  # noqa: E402
from localbench.scoring.agentic_exec.sandbox import SandboxConfig, SandboxError  # noqa: E402


class _FakeEvaluation:
    def to_dict(self) -> dict[str, Any]:
        return {
            "success": True,
            "passes": [{"requirement": "answer accepted"}],
            "failures": [],
        }


class _FakeWorld:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, code: str) -> str:
        self.executed.append(code)
        return ""

    def evaluate(self) -> _FakeEvaluation:
        return _FakeEvaluation()

    def close(self) -> None:
        return None


class _RunnerRpc:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, message: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(message)
        return {"kind": rb.KIND_OK, "result": {"success": False}}


class _LiveProcess:
    returncode = None

    def __init__(self, stdout: io.StringIO) -> None:
        self.stdin = io.StringIO()
        self.stdout = stdout

    def poll(self) -> None:
        return None


class _BlockingStdout:
    def readline(self) -> str:
        threading.Event().wait()
        return ""


def test_env_host_rejects_runner_socket_finalize() -> None:
    # Given: a trusted host already pinned to a fake task world.
    host = _fake_host()

    # When: the untrusted runner attempts OP_FINALIZE over the socket surface.
    response = host.handle({"op": env_host.OP_FINALIZE, "answer": "runner-forged"})

    # Then: finalize is refused on the runner surface and the task is not finalized.
    assert response["kind"] == env_host.KIND_PROTOCOL_ERROR
    assert "runner surface" in str(response["message"])
    assert host._world.executed == []


def test_env_host_control_finalize_emits_one_authoritative_verdict() -> None:
    # Given: a trusted control message with a caller-supplied correlation id.
    host = _fake_host(task_id="fac291d_1")
    stdout = io.StringIO()

    # When: env-host processes the finalize control message from stdin.
    env_host._handle_control_message(
        host,
        {"op": "finalize", "answer": {"value": 5}, "finalize_id": "attempt-1:1"},
        stdout,
    )

    # Then: exactly one stdout verdict line is emitted with the echoed finalize_id.
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload == {
        "type": "authoritative_verdict",
        "finalize_id": "attempt-1:1",
        "task_id": "fac291d_1",
        "result": {
            "success": True,
            "passed": True,
            "collateral_damage": False,
            "passes": ["answer accepted"],
            "failures": [],
            "num_passes": 1,
            "num_failures": 0,
        },
    }


def test_env_host_second_control_finalize_is_refused_by_one_shot_guard() -> None:
    # Given: a host that has already accepted one trusted finalize control message.
    host = _fake_host()
    stdout = io.StringIO()
    env_host._handle_control_message(
        host,
        {"op": "finalize", "answer": "first", "finalize_id": "attempt-1:1"},
        stdout,
    )

    # When: a second finalize arrives on the trusted control channel.
    env_host._handle_control_message(
        host,
        {"op": "finalize", "answer": "second", "finalize_id": "attempt-1:2"},
        stdout,
    )

    # Then: the second line is non-scoreable protocol error telemetry, not another result.
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert len(lines) == 2
    assert "result" in lines[0]
    assert lines[1]["type"] == "authoritative_verdict"
    assert lines[1]["finalize_id"] == "attempt-1:2"
    assert lines[1]["error"]["kind"] == env_host.KIND_PROTOCOL_ERROR
    assert "result" not in lines[1]
    assert len(host._world.executed) == 1


def test_runner_finalize_command_is_non_scoreable_telemetry() -> None:
    # Given: the untrusted runner has an RPC client but finalize must not use it.
    rpc = _RunnerRpc()
    namespace = rb._build_namespace(rb.ApisProxy(rpc))

    # When: a legacy finalize command reaches the runner stdin loop.
    event, should_exit = rb._handle_command(
        namespace,
        {"cmd": "finalize", "answer": "runner-supplied"},
    )

    # Then: the runner emits only an explicit non-scoreable ack and makes no env-host RPC.
    assert should_exit is False
    assert event["event"] == "final_ack"
    assert event["scoreable"] is False
    assert rpc.calls == []


def test_sandbox_finalize_scores_only_matching_authoritative_env_host_verdict() -> None:
    # Given: env-host stdout says failure while runner stdout carries a forged success.
    sandbox = _sandbox_with_pipes(
        env_stdout_lines=[
            {
                "type": "authoritative_verdict",
                "finalize_id": "attempt-A:fac291d_1:finalize:1",
                "task_id": "fac291d_1",
                "result": {
                    "success": False,
                    "collateral_damage": True,
                    "passes": [],
                    "failures": ["wrong answer"],
                },
            }
        ],
        runner_stdout_lines=[
            {
                "event": "final_result",
                "verdict": {
                    "success": True,
                    "collateral_damage": False,
                    "passes": ["forged"],
                    "failures": [],
                },
            }
        ],
    )

    # When: the orchestrator finalizes with its own read-back answer.
    verdict = sandbox.finalize({"value": 5})

    # Then: scoring follows only the authoritative env-host line, and the control id is deterministic.
    assert verdict.success is False
    assert verdict.collateral_damage is True
    assert verdict.failures == ("wrong answer",)
    control = json.loads(sandbox._env_proc.stdin.getvalue().strip())
    assert control == {
        "op": "finalize",
        "answer": {"value": 5},
        "finalize_id": "attempt-A:fac291d_1:finalize:1",
    }


def test_sandbox_finalize_skips_benign_stdout_noise_before_verdict() -> None:
    # Given: the env-host control stdout carries benign noise (a plain log line and a non-verdict
    # JSON object, e.g. from AppWorld/library prints during evaluate) BEFORE the real verdict.
    sandbox = sandbox_mod.AppWorldSandbox(
        "fac291d_1",
        SandboxConfig(experiment_name="attempt-A", finalize_timeout_s=0.1),
    )
    env_stdout = io.StringIO(
        "AppWorld: evaluating task fac291d_1 ...\n"
        + json.dumps({"log": "world step", "level": "info"}, separators=(",", ":")) + "\n"
        + json.dumps(
            {
                "type": "authoritative_verdict",
                "finalize_id": "attempt-A:fac291d_1:finalize:1",
                "task_id": "fac291d_1",
                "result": {"success": True, "collateral_damage": False, "passes": ["ok"], "failures": []},
            },
            separators=(",", ":"),
        ) + "\n"
    )
    sandbox._env_proc = _LiveProcess(env_stdout)  # type: ignore[assignment]
    sandbox._runner_proc = _LiveProcess(io.StringIO(""))  # type: ignore[assignment]

    # When: the orchestrator finalizes.
    verdict = sandbox.finalize("answer")

    # Then: the noise is skipped and the correlated verdict is scored (no false failure).
    assert verdict.success is True
    assert verdict.passes == ("ok",)


def test_sandbox_finalize_id_mismatch_fails_task() -> None:
    # Given: env-host returns an authoritative verdict for the wrong finalize_id.
    sandbox = _sandbox_with_pipes(
        env_stdout_lines=[
            {
                "type": "authoritative_verdict",
                "finalize_id": "other-attempt:1",
                "task_id": "fac291d_1",
                "result": {"success": True, "collateral_damage": False},
            }
        ],
        runner_stdout_lines=[
            {"event": "final_result", "verdict": {"success": True, "collateral_damage": False}}
        ],
    )

    # When / Then: the task fails instead of accepting or falling back to runner output.
    with pytest.raises(SandboxError, match="finalize_id mismatch"):
        sandbox.finalize("answer")


def test_sandbox_finalize_timeout_has_no_runner_fallback() -> None:
    # Given: env-host stdout never produces the correlated verdict, but runner stdout has success.
    sandbox = sandbox_mod.AppWorldSandbox(
        "fac291d_1",
        SandboxConfig(experiment_name="attempt-A", finalize_timeout_s=0.02),
    )
    sandbox._env_proc = _LiveProcess(_BlockingStdout())  # type: ignore[arg-type]
    sandbox._runner_proc = _LiveProcess(
        io.StringIO(
            json.dumps(
                {"event": "final_result", "verdict": {"success": True, "collateral_damage": False}}
            )
            + "\n"
        )
    )

    # When / Then: timeout is fatal and the forged runner value is not used.
    with pytest.raises(SandboxError, match="timed out"):
        sandbox.finalize("answer")


def _fake_host(task_id: str = "task-1") -> env_host._RealEnvHost:
    host = env_host._RealEnvHost.__new__(env_host._RealEnvHost)
    host._task_id = task_id
    host._world = _FakeWorld()
    host._finalized = False
    host._valid_apps = frozenset()
    return host


def _sandbox_with_pipes(
    *,
    env_stdout_lines: list[dict[str, Any]],
    runner_stdout_lines: list[dict[str, Any]],
) -> sandbox_mod.AppWorldSandbox:
    sandbox = sandbox_mod.AppWorldSandbox(
        "fac291d_1",
        SandboxConfig(experiment_name="attempt-A", finalize_timeout_s=0.1),
    )
    env_stdout = io.StringIO(
        "".join(json.dumps(line, separators=(",", ":")) + "\n" for line in env_stdout_lines)
    )
    runner_stdout = io.StringIO(
        "".join(json.dumps(line, separators=(",", ":")) + "\n" for line in runner_stdout_lines)
    )
    sandbox._env_proc = _LiveProcess(env_stdout)  # type: ignore[assignment]
    sandbox._runner_proc = _LiveProcess(runner_stdout)  # type: ignore[assignment]
    return sandbox
