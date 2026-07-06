from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from localbench._suite import read_json_object, render_benches
from localbench.coding_exec.orchestrate import (
    CodingExecConfig,
    CodingExecError,
    ranked_eligibility,
    run_coding_exec,
)
from localbench.coding_exec.sandbox import DockerEnv, RawRunResult

_REPO = Path(__file__).resolve().parents[2]
_SUITE_V1 = _REPO / "suite" / "v1"

# A host with gVisor — passes preflight and exercises runtime auto-selection. Injected so
# the orchestrator never shells out to a real Docker during unit tests.
_GVISOR_HOST = DockerEnv(
    platform="linux", desktop=False, rootless=False, runsc_available=True, runc_version=(1, 2, 0)
)
_UNSAFE_HOST = DockerEnv(
    platform="linux", desktop=False, rootless=False, runsc_available=False, runc_version=(1, 2, 0)
)


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
            config,
            transport=httpx.MockTransport(_generation_handler),
            sandbox_runner=_fake_sandbox,
            docker_env=_GVISOR_HOST,
        )

    run = asyncio.run(scenario())

    assert run["schema"] == "localbench-coding-exec-v1"
    assert run["score"]["bench"] == "bigcodebench_hard"
    assert run["score"]["n"] == 2
    assert run["score"]["n_passed"] == 1
    assert run["score"]["raw_accuracy"] == pytest.approx(0.5)
    assert run["manifest"]["lane"] == "exec"
    assert run["manifest"]["image_digest_pinned"] is False  # default tag, not a digest
    assert run["manifest"]["ranked_eligible"] is False  # ...so the run is not ranked-eligible
    assert any("digest" in reason for reason in run["manifest"]["ranked_ineligible_reasons"])
    assert len(run["manifest"]["runner_sha256"]) == 64  # harness provenance recorded
    assert run["manifest"]["runtime"] == "runsc"  # preflight auto-selected gVisor
    assert run["manifest"]["item_set_hashes"]["bigcodebench_hard.jsonl"]
    assert any("--init" in flag for flag in run["manifest"]["sandbox_hardening"])
    assert (tmp_path / "coding.json").exists()


def test_run_coding_exec_refuses_unsafe_host(tmp_path: Path) -> None:
    # The fail-closed gate: a rootful bare-Linux host with no second boundary must abort
    # BEFORE any generation, not silently run untrusted code.
    config = CodingExecConfig(
        endpoint="http://local/v1", model="demo-model", suite_dir=_SUITE_V1, max_items=2, out=tmp_path / "c.json"
    )

    async def scenario() -> dict:
        return await run_coding_exec(
            config, transport=httpx.MockTransport(_generation_handler), sandbox_runner=_fake_sandbox, docker_env=_UNSAFE_HOST
        )

    with pytest.raises(CodingExecError, match="preflight failed"):
        asyncio.run(scenario())
    assert not (tmp_path / "c.json").exists()


def test_run_coding_exec_override_runs_on_unsafe_host(tmp_path: Path) -> None:
    config = CodingExecConfig(
        endpoint="http://local/v1",
        model="demo-model",
        suite_dir=_SUITE_V1,
        max_items=2,
        out=tmp_path / "c.json",
        allow_unsafe_sandbox=True,
    )

    async def scenario() -> dict:
        return await run_coding_exec(
            config, transport=httpx.MockTransport(_generation_handler), sandbox_runner=_fake_sandbox, docker_env=_UNSAFE_HOST
        )

    run = asyncio.run(scenario())
    assert run["manifest"]["allow_unsafe_sandbox"] is True
    assert any("OVERRIDE" in warning for warning in run["warnings"])


def test_ranked_eligibility_requires_digest_pin_and_no_unsafe_override() -> None:
    # A default tag image is not digest-pinned -> not ranked-eligible.
    tagged = CodingExecConfig(endpoint="x", model="m", suite_dir=_SUITE_V1)
    eligible, reasons = ranked_eligibility(tagged)
    assert eligible is False
    assert any("digest" in reason for reason in reasons)

    # Digest-pinned + sandbox not overridden -> ranked-eligible.
    pinned = CodingExecConfig(endpoint="x", model="m", suite_dir=_SUITE_V1, image="repo@sha256:" + "a" * 64)
    assert ranked_eligibility(pinned) == (True, [])

    # Digest-pinned but the unsafe-sandbox override was used -> ineligible.
    unsafe = CodingExecConfig(
        endpoint="x", model="m", suite_dir=_SUITE_V1, image="repo@sha256:" + "a" * 64, allow_unsafe_sandbox=True
    )
    ok, unsafe_reasons = ranked_eligibility(unsafe)
    assert ok is False
    assert any("unsafe" in reason for reason in unsafe_reasons)


def test_bigcodebench_renders_for_deferred_artifact_generation() -> None:
    suite = read_json_object(_SUITE_V1 / "suite.json")
    warnings: list[str] = []
    rendered = render_benches("bigcodebench_hard", "standard", 1, _SUITE_V1, suite, warnings)

    assert len(rendered) == 1
    item = rendered[0].benchmark_items[0]
    source = rendered[0].source_items[0]
    assert str(source["instruct_prompt"]) in item["messages"][0]["content"]
    assert "complete_prompt" not in item["messages"][0]["content"]
    assert item["max_tokens"] == 16_384
    assert item["sampling_params"] == {"temperature": 0}
    assert item["answer_reserve"] == 4_096


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
