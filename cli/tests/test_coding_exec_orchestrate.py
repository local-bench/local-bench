from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from localbench._suite import read_json_object, render_benches
from localbench._types import JsonObject
from localbench.cli import main
from localbench.coding_exec.orchestrate import (
    CodingExecConfig,
    CodingExecError,
    execute_pending_artifacts,
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


def _fake_sandbox(
    argv: list[str],
    _timeout: float,
    _max_bytes: int,
    stdin_bytes: bytes,
) -> RawRunResult:
    assert "--volume" not in argv
    assert "/var/run/docker.sock" not in argv
    if not stdin_bytes:
        payload = {
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
    else:
        payload = {
            "schema": "localbench-coding-exec-runner-v2",
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
        allow_untrusted_code=True,
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
    assert run["manifest"]["image_digest_pinned"] is True
    assert run["manifest"]["ranked_eligible"] is True
    assert run["manifest"]["ranked_ineligible_reasons"] == []
    assert len(run["manifest"]["runner_sha256"]) == 64  # harness provenance recorded
    assert run["manifest"]["runtime"] == "runsc"  # preflight auto-selected gVisor
    assert run["manifest"]["item_set_hashes"]["bigcodebench_hard.jsonl"]
    assert any("--init" in flag for flag in run["manifest"]["sandbox_hardening"])
    assert (tmp_path / "coding.json").exists()


def test_run_coding_exec_refuses_unsafe_host(tmp_path: Path) -> None:
    # The fail-closed gate: a rootful bare-Linux host with no second boundary must abort
    # BEFORE any generation, not silently run untrusted code.
    config = CodingExecConfig(
        endpoint="http://local/v1",
        model="demo-model",
        suite_dir=_SUITE_V1,
        max_items=2,
        out=tmp_path / "c.json",
        allow_untrusted_code=True,
    )

    async def scenario() -> dict:
        return await run_coding_exec(
            config, transport=httpx.MockTransport(_generation_handler), sandbox_runner=_fake_sandbox, docker_env=_UNSAFE_HOST
        )

    with pytest.raises(CodingExecError, match="preflight failed"):
        asyncio.run(scenario())
    assert not (tmp_path / "c.json").exists()


def test_run_coding_exec_requires_explicit_untrusted_code_consent(tmp_path: Path) -> None:
    config = CodingExecConfig(
        endpoint="http://local/v1",
        model="demo-model",
        suite_dir=_SUITE_V1,
        max_items=2,
        out=tmp_path / "c.json",
    )

    async def scenario() -> dict:
        return await run_coding_exec(
            config,
            transport=httpx.MockTransport(_generation_handler),
            sandbox_runner=_fake_sandbox,
            docker_env=_GVISOR_HOST,
        )

    with pytest.raises(CodingExecError, match="--allow-untrusted-code"):
        asyncio.run(scenario())
    assert not (tmp_path / "c.json").exists()


def test_ranked_eligibility_defaults_to_pinned_image() -> None:
    default = CodingExecConfig(endpoint="x", model="m", suite_dir=_SUITE_V1)

    assert default.image == (
        "bigcodebench/bigcodebench-evaluate@sha256:"
        "a3cd34ec3840a49d6b7afb240f4bdd47c350bc5991043fd0a91773830f7cd405"
    )
    assert ranked_eligibility(default) == (True, [])


def test_ranked_eligibility_rejects_unpinned_image() -> None:
    tagged = CodingExecConfig(
        endpoint="x",
        model="m",
        suite_dir=_SUITE_V1,
        image="bigcodebench/bigcodebench-evaluate:latest",
    )
    eligible, reasons = ranked_eligibility(tagged)
    assert eligible is False
    assert any("digest" in reason for reason in reasons)

    pinned = CodingExecConfig(endpoint="x", model="m", suite_dir=_SUITE_V1, image="repo@sha256:" + "a" * 64)
    assert ranked_eligibility(pinned) == (True, [])


def test_grade_coding_finalize_stamps_mixed_terminal_items_complete(tmp_path: Path) -> None:
    run = _full_run_with_coding_items(
        [
            {
                "id": "bcbh-001",
                "bench": "bigcodebench_hard",
                "correct": True,
                "code_artifact": {
                    "verdict_source": "verifier",
                    "image_digest": "image@sha256:" + "a" * 64,
                    "verdict": {"passed": True},
                },
            },
            {
                "id": "bcbh-002",
                "bench": "bigcodebench_hard",
                "correct": False,
                "failure_kind": "coding_ast_rejected",
                "code_artifact": {
                    "verdict": None,
                    "verdict_source": None,
                    "conformance_status": {
                        "status": "failed",
                        "failure": "coding_ast_rejected",
                    },
                },
            },
            {
                "id": "bcbh-119",
                "bench": "bigcodebench_hard",
                "correct": False,
                "failure_kind": "ambiguous_extraction:truncated_fence",
                "code_artifact": {
                    "extraction_status": {
                        "status": "ambiguous",
                        "failure": "truncated_fence",
                    },
                    "verdict": None,
                    "verdict_source": None,
                },
            },
        ],
    )
    run_path = tmp_path / "mixed-terminal.json"
    run_path.write_text(json.dumps(run) + "\n", encoding="utf-8")

    graded = execute_pending_artifacts(
        run_path,
        CodingExecConfig(
            endpoint="",
            model="",
            suite_dir=_SUITE_V1,
            out=tmp_path / "graded.json",
            allow_untrusted_code=True,
        ),
        sandbox_runner=_fake_sandbox,
        docker_env=_GVISOR_HOST,
    )

    assert graded["axis_status"]["axes"]["coding"]["status"] == "measured"
    assert graded["headline_complete"] is True
    assert graded["scores"]["headline_score"] == pytest.approx(0.7625)


def test_grade_coding_finalize_keeps_ungraded_pending_item_incomplete(tmp_path: Path) -> None:
    run = _full_run_with_coding_items(
        [
            {
                "id": "bcbh-001",
                "bench": "bigcodebench_hard",
                "correct": False,
                "code_artifact": {
                    "verdict": None,
                    "verdict_source": None,
                },
            },
        ],
    )
    run_path = tmp_path / "pending.json"
    run_path.write_text(json.dumps(run) + "\n", encoding="utf-8")

    graded = execute_pending_artifacts(
        run_path,
        CodingExecConfig(
            endpoint="",
            model="",
            suite_dir=_SUITE_V1,
            out=tmp_path / "graded.json",
            allow_untrusted_code=True,
        ),
        sandbox_runner=_fake_sandbox,
        docker_env=_GVISOR_HOST,
    )

    assert graded["axis_status"]["axes"]["coding"]["status"] == "generated_unverified"
    assert graded["headline_complete"] is False


def test_execute_pending_artifacts_accepts_run_directory(tmp_path: Path) -> None:
    # Given: a campaign directory contains the canonical localbench run document.
    run_dir = tmp_path / "campaign"
    run_dir.mkdir()
    run_path = run_dir / "localbench-run.json"
    run_path.write_text(
        json.dumps(
            _full_run_with_coding_items(
                [
                    {
                        "id": "bcbh-001",
                        "bench": "bigcodebench_hard",
                        "correct": False,
                        "code_artifact": {
                            "sanitized_code": "def task_func():\n    return 1",
                            "verdict": None,
                            "verdict_source": None,
                        },
                    },
                ],
            ),
        )
        + "\n",
        encoding="utf-8",
    )

    # When: the verifier receives the campaign directory instead of the JSON file.
    graded = execute_pending_artifacts(
        run_dir,
        CodingExecConfig(
            endpoint="",
            model="pending-artifact-verifier",
            suite_dir=_SUITE_V1,
            allow_untrusted_code=True,
        ),
        sandbox_runner=_fake_sandbox,
        docker_env=_GVISOR_HOST,
    )

    # Then: it resolves and updates <directory>/localbench-run.json.
    assert graded["axis_status"]["axes"]["coding"]["status"] == "measured"
    persisted = json.loads(run_path.read_text(encoding="utf-8"))
    assert persisted["axis_status"]["axes"]["coding"]["status"] == "measured"


def _full_run_with_coding_items(items: list[JsonObject]) -> JsonObject:
    benches = {
        "mmlu_pro": _bench_aggregate(1.0),
        "ifbench": _bench_aggregate(1.0),
        "tc_json_v1": _bench_aggregate(1.0),
        "bigcodebench_hard": _bench_aggregate(0.5),
        "olymmath_hard": _bench_aggregate(1.0),
        "amo": _bench_aggregate(1.0),
        "appworld_c": _bench_aggregate(0.5),
    }
    return {
        "manifest": {
            "suite": {
                "axis_membership": {
                    "knowledge": ["mmlu_pro"],
                    "instruction_following": ["ifbench"],
                    "math": ["olymmath_hard", "amo"],
                    "agentic": ["appworld_c"],
                    "tool_calling": ["tc_json_v1"],
                    "coding": ["bigcodebench_hard"],
                },
            },
        },
        "items": items,
        "benches": benches,
        "axis_status": {
            "schema_version": "localbench.axis-status.v1",
            "axes": {
                "knowledge": {"axis": "knowledge", "status": "measured", "reason": "ok"},
                "instruction_following": {
                    "axis": "instruction_following",
                    "status": "measured",
                    "reason": "ok",
                },
                "math": {"axis": "math", "status": "measured", "reason": "ok"},
                "agentic": {"axis": "agentic", "status": "measured", "reason": "ok"},
                "tool_calling": {"axis": "tool_calling", "status": "measured", "reason": "ok"},
                "coding": {
                    "axis": "coding",
                    "status": "generated_unverified",
                    "reason": "verdict_pending",
                },
            },
        },
        "headline_complete": False,
    }


def _bench_aggregate(score: float) -> dict[str, float | int]:
    return {
        "n": 1,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": score,
        "chance_corrected": score,
        "termination_rate": 1.0,
        "conditional_accuracy": score,
    }


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
    assert "--allow-untrusted-code" in result.stdout
    assert "sandbox" in result.stdout.lower()


def test_grade_coding_existing_run_uses_pinned_image_without_real_docker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_path = tmp_path / "localbench-run.json"
    run_path.write_text("{}\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_grade(path: Path, config: CodingExecConfig) -> JsonObject:
        captured["path"] = path
        captured["config"] = config
        return {"headline_complete": True}

    monkeypatch.setattr("localbench.cli.execute_pending_artifacts", fake_grade)

    exit_code = main(
        [
            "grade-coding",
            "--run",
            str(run_path),
            "--suite-dir",
            str(_SUITE_V1),
            "--allow-untrusted-code",
        ],
    )

    assert exit_code == 0
    assert captured["path"] == run_path
    assert isinstance(captured["config"], CodingExecConfig)
    assert captured["config"].image == CodingExecConfig(endpoint="", model="", suite_dir=_SUITE_V1).image
    assert f"output     {run_path}" in capsys.readouterr().out


def test_grade_coding_parser_requires_exactly_one_input() -> None:
    with pytest.raises(SystemExit):
        main(["grade-coding", "--suite-dir", str(_SUITE_V1)])


def test_grade_coding_result_bundle_writes_separate_graded_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path = tmp_path / "result-bundle.json"
    bundle_path.write_text("{}\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_grade(path: Path, config: CodingExecConfig) -> JsonObject:
        captured["source"] = path
        captured["out"] = config.out
        return {}

    monkeypatch.setattr("localbench.cli.execute_pending_artifacts", fake_grade)

    exit_code = main(
        [
            "grade-coding",
            "--bundle",
            str(bundle_path),
            "--suite-dir",
            str(_SUITE_V1),
            "--allow-untrusted-code",
        ],
    )

    assert exit_code == 0
    assert captured["source"] != bundle_path
    assert captured["out"] == tmp_path / "result-bundle.coding-graded.json"
