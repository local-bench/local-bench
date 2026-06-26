from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from localbench._scoring import aggregate, composite
from localbench._suite import read_json_object
from localbench.orchestrate import (
    OrchestrateConfig,
    _appworld_report_to_aggregate,
    _appworld_report_to_items,
    run_localbench,
)
from localbench.scoring.agentic_exec import benchmark as appworld_bench
from localbench.scoring.agentic_exec import scripted_agent as sa
from localbench.scoring.agentic_exec.loop_types import (
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
)
from test_appworld_protocol_c_units import FakeSandbox

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v1"
_IFBENCH_PASSING_RESPONSE = (
    "kaleidoscope nebula nebula whisper whisper whisper "
    "labyrinth labyrinth labyrinth labyrinth labyrinth "
    "paradox paradox paradox paradox paradox paradox paradox"
)


def test_run_localbench_when_agentic_seams_succeed_includes_headline_axis(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given scored defaults plus injected AppWorld-C task/model/sandbox seams.
        output_path = tmp_path / "agentic-inline-run.json"

        # When running the one-command default path.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=_SUITE_DIR,
                tier="standard",
                out=output_path,
                max_items=1,
            ),
            transport=httpx.MockTransport(_v1_agentic_weight_handler),
            agentic_sandbox_factory=_fake_appworld_sandbox_factory,
            agentic_model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
            agentic_task_ids=["fac291d_1", "50e1ac9_1"],
        )

        # Then appworld_c is measured and participates as the 0.60 headline axis.
        assert list(record["benches"]) == ["mmlu_pro", "ifbench", "tc_json_v1", "appworld_c"]
        assert [item["bench"] for item in record["items"]] == [
            "mmlu_pro",
            "ifbench",
            "tc_json_v1",
            "appworld_c",
            "appworld_c",
        ]
        assert record["benches"]["appworld_c"] == {
            "n": 2,
            "n_errors": 0,
            "n_extraction_failures": 0,
            "raw_accuracy": 1.0,
            "chance_corrected": 1.0,
            "conditional_accuracy": 1.0,
            "termination_rate": 1.0,
        }
        assert record["benches"]["appworld_c"]["raw_accuracy"] == pytest.approx(
            record["agentic_run"]["mean_asr"],
        )
        assert record["axis_status"]["axes"]["agentic"] == {
            "axis": "agentic",
            "status": "measured",
            "reason": "ok",
        }
        assert record["headline_complete"] is True
        agentic_run = record["agentic_run"]
        assert agentic_run["campaign"] is True
        assert agentic_run["single_pass"] is False
        assert agentic_run["asr_series"] == [1.0, 1.0]
        assert agentic_run["mean_asr"] == pytest.approx(1.0)
        assert agentic_run["max_abs_delta_pp"] == pytest.approx(0.0)
        assert agentic_run["triggered_third_run"] is False
        assert agentic_run["subset_size"] == 2
        assert isinstance(agentic_run["subset_hash"], str)
        assert agentic_run["subset_hash"]
        assert agentic_run["stage"] == "injected"
        ki_only = {
            "mmlu_pro": record["benches"]["mmlu_pro"],
            "ifbench": record["benches"]["ifbench"],
        }
        assert record["composite"] != pytest.approx(composite(ki_only))
        suite = read_json_object(_SUITE_DIR / "suite.json")
        suite_axes = suite["axes"]
        assert isinstance(suite_axes, dict)
        assert record["composite"] == pytest.approx(
            composite(record["benches"], record["axis_status"], suite_axes),
        )

    asyncio.run(scenario())


def test_appworld_report_conversion_matches_run_aggregate() -> None:
    # Given a Protocol-C report with a known success pattern.
    report = appworld_bench.aggregate(
        [
            _task_result("fac291d_1", success=True),
            _task_result("50e1ac9_1", success=False),
            _task_result("calendar_17", success=True),
        ],
    )

    # When converting it into the localbench run-record aggregate/items shape.
    bench_aggregate = _appworld_report_to_aggregate(report)
    items = _appworld_report_to_items(report)

    # Then the board-compatible ASR aggregate and item-derived aggregate agree.
    assert bench_aggregate == {
        "n": 3,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": pytest.approx(2 / 3),
        "chance_corrected": pytest.approx(2 / 3),
        "conditional_accuracy": pytest.approx(2 / 3),
        "termination_rate": 1.0,
    }
    assert aggregate("appworld_c", items, baseline=0.0) == bench_aggregate


def test_orchestrate_import_is_appworld_optional() -> None:
    # Given / When / Then: importing the orchestrator does not import the real AppWorld backend.
    import localbench.orchestrate as orchestrate

    assert orchestrate.OrchestrateConfig.__name__ == "OrchestrateConfig"


def _v1_agentic_weight_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    payload = json.loads(request.content)
    prompt = payload["messages"][0]["content"]
    if "specific entropy" in prompt:
        return _completion("Answer: A", 1, 1)
    if "kaleidoscope" in prompt:
        return _completion(_IFBENCH_PASSING_RESPONSE, 1, 1)
    if "calculate_triangle_area" in prompt:
        return _completion(
            json.dumps(
                {
                    "schema_version": "localbench.tc.v1",
                    "calls": [
                        {
                            "name": "calculate_triangle_area",
                            "arguments": {"base": 10, "height": 5},
                        },
                    ],
                },
            ),
            1,
            1,
        )
    return httpx.Response(500, text="unexpected prompt")


def _fake_appworld_sandbox_factory(task_id: str) -> FakeSandbox:
    golds = {
        "fac291d_1": (
            5,
            "How many unique songs are in my library across songs, albums and playlists?",
        ),
        "50e1ac9_1": (
            "Bravo, Delta, Alpha",
            "What are the titles of the top 3 most played R&B songs in my library?",
        ),
    }
    gold, instruction = golds[task_id]
    return FakeSandbox(gold_answer=gold, instruction=instruction, supervisor_email="b@x.com")


def _task_result(task_id: str, *, success: bool) -> TaskRunResult:
    outcome = TaskOutcome.SUCCESS if success else TaskOutcome.FAILURE
    diagnostics = TaskDiagnostics(
        task_id=task_id,
        outcome=outcome,
        success=success,
        collateral_damage=False,
        turns_used=1,
        blocks_run=1,
        format_failures=0,
        syntax_errors=0,
        runtime_errors=0,
        cap_exceeded=False,
        total_api_calls=0,
        api_docs_uses=0,
        observation_truncations=0,
        total_output_tokens=1,
        failure_class=FailureClass.NONE,
    )
    return TaskRunResult(
        task_id=task_id,
        success=success,
        outcome=outcome,
        collateral_damage=False,
        diagnostics=diagnostics,
    )


def _completion(text: str, prompt_tokens: int, completion_tokens: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": text},
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )
