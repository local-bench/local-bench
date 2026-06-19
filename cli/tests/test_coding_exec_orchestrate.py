from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from localbench._suite import read_json_object, render_benches
from localbench.coding_exec.orchestrate import CodingExecConfig, run_coding_exec
from localbench.coding_exec.sandbox import RawRunResult
from localbench.orchestrate import _exclude_exec_lane

_REPO = Path(__file__).resolve().parents[2]
_SUITE_V1 = _REPO / "suite" / "v1"


def _generation_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": "Here:\n```python\ndef task_func(*a, **k):\n    return None\n```"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def _fake_sandbox(_argv: list[str], _timeout: float, _max_bytes: int) -> RawRunResult:
    payload = {
        "schema": "localbench-coding-exec-runner-v1",
        "results": [
            {"id": "bcbh-001", "passed": True, "exit_code": 0, "timed_out": False, "stderr_tail": ""},
            {"id": "bcbh-002", "passed": False, "exit_code": 1, "timed_out": False, "stderr_tail": "AssertionError"},
        ],
    }
    return RawRunResult(exit_code=0, stdout=json.dumps(payload).encode(), stderr=b"", timed_out=False)


def test_run_coding_exec_generate_assemble_sandbox_score(tmp_path: Path) -> None:
    config = CodingExecConfig(
        endpoint="http://local/v1",
        model="demo-model",
        suite_dir=_SUITE_V1,
        max_items=2,
        out=tmp_path / "coding.json",
        provider="local",
        lane="capped-thinking",
    )

    async def scenario() -> dict:
        return await run_coding_exec(
            config, transport=httpx.MockTransport(_generation_handler), sandbox_runner=_fake_sandbox
        )

    run = asyncio.run(scenario())

    assert run["schema"] == "localbench-coding-exec-v1"
    assert run["score"]["bench"] == "bigcodebench_hard"
    assert run["score"]["n"] == 2
    assert run["score"]["n_passed"] == 1
    assert run["score"]["raw_accuracy"] == pytest.approx(0.5)
    assert run["manifest"]["lane"] == "exec"
    assert run["manifest"]["image_digest_pinned"] is False  # default tag, not a digest
    assert run["manifest"]["item_set_hashes"]["bigcodebench_hard.jsonl"]
    assert any("--init" in flag for flag in run["manifest"]["sandbox_hardening"])
    assert (tmp_path / "coding.json").exists()


def test_localbench_run_excludes_the_exec_lane_bench() -> None:
    suite = read_json_object(_SUITE_V1 / "suite.json")
    warnings: list[str] = []
    rendered = render_benches("bigcodebench_hard", "standard", 1, _SUITE_V1, suite, warnings)
    assert rendered, "exec bench should still render for `localbench code`"
    kept = _exclude_exec_lane(rendered, suite, warnings)
    assert kept == []  # ... but never via the normal `localbench run` path
    assert any("localbench code" in warning for warning in warnings)


def test_cli_code_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "localbench", "code", "--help"],
        cwd=_REPO / "cli",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--endpoint" in result.stdout
    assert "sandbox" in result.stdout.lower()
