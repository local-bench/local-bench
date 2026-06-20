"""Tests for the localbench benchmark orchestrator."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from localbench.orchestrate import OrchestrateConfig, run_localbench


FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_run_localbench_when_fixture_suite_scores_and_writes_json(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a fixture suite and an OpenAI-compatible endpoint with mixed outcomes.
        output_path = tmp_path / "run.json"
        transport = httpx.MockTransport(_mixed_handler)

        # When running all benches through the orchestrator.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                out=output_path,
                price_in=1.0,
                price_out=2.0,
            ),
            transport=transport,
        )

        # Then the JSON contract, aggregates, manifest, and pricing are written.
        assert record["schema"] == "localbench-run-v0"
        assert json.loads(output_path.read_text(encoding="utf-8")) == record
        assert len(record["items"]) == 7
        assert record["benches"]["mmlu_pro"] == {
            "n": 3,
            "n_errors": 0,
            "n_extraction_failures": 1,
            "raw_accuracy": pytest.approx(1 / 3),
            "chance_corrected": pytest.approx(1 / 9),
            "termination_rate": 1.0,
            "conditional_accuracy": pytest.approx(1 / 3),
        }
        assert record["benches"]["ifeval"] == {
            "n": 2,
            "n_errors": 1,
            "n_extraction_failures": 0,
            "raw_accuracy": 0.5,
            "chance_corrected": 0.5,
            "termination_rate": 0.5,
            "conditional_accuracy": 1.0,
        }
        assert record["benches"]["genmath"] == {
            "n": 2,
            "n_errors": 0,
            "n_extraction_failures": 0,
            "raw_accuracy": 0.5,
            "chance_corrected": 0.5,
            "termination_rate": 1.0,
            "conditional_accuracy": 0.5,
        }
        # Composite is HEADLINE-only: knowledge (mmlu_pro) + instruction (ifeval).
        # genmath -> Math carries weight 0.0, so it is excluded (METHODOLOGY-v1.2 §3).
        assert record["composite"] == pytest.approx((1 / 9 + 0.5) / 2)
        assert record["totals"]["prompt_tokens"] == 50
        assert record["totals"]["completion_tokens"] == 14
        assert record["totals"]["total_tokens"] == 64
        assert record["estimated_cost_usd"] == pytest.approx(0.000078)
        assert record["manifest"]["endpoint"]["runtime_reported_model"] == "runtime-demo"
        assert record["manifest"]["suite"]["item_set_hashes"] == {
            "genmath_quick.jsonl": "fixture-genmath-quick",
            "ifeval_quick.jsonl": "fixture-ifeval-quick",
            "mmlu_pro_quick.jsonl": "fixture-mmlu-quick",
        }
        assert record["manifest"]["integrity"]["canonical"] is False

    asyncio.run(scenario())


def test_run_localbench_when_max_items_truncates_each_bench(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a fixture suite with multiple items in each bench.
        output_path = tmp_path / "run.json"

        # When limiting each bench to one item.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                out=output_path,
                max_items=1,
            ),
            transport=httpx.MockTransport(_all_correct_handler),
        )

        # Then each bench contributes only its first item.
        assert [item["id"] for item in record["items"]] == ["1", "11", "math-1"]
        assert record["benches"]["mmlu_pro"]["n"] == 1
        assert record["benches"]["ifeval"]["n"] == 1
        assert record["benches"]["genmath"]["n"] == 1

    asyncio.run(scenario())


def test_run_localbench_when_item_file_is_missing_skips_bench(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a suite entry whose item file does not exist.
        suite_dir = tmp_path / "suite"
        suite_dir.mkdir()
        (suite_dir / "suite.json").write_text(
            json.dumps(
                {
                    "version": "suite-fixture-v0",
                    "benches": {
                        "genmath": {
                            "chance_correction_baseline": 0.0,
                            "decoding": {"max_tokens": 8, "temperature": 0},
                            "itemsets": {"quick": {"file": "missing.jsonl"}},
                            "template": "templates/genmath.txt",
                        },
                    },
                },
            ),
            encoding="utf-8",
        )
        (suite_dir / "itemsets.lock.json").write_text('{"files": {}}', encoding="utf-8")
        (suite_dir / "templates").mkdir()
        (suite_dir / "templates" / "genmath.txt").write_text("{statement}", encoding="utf-8")

        # When running the suite.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=suite_dir,
                out=tmp_path / "run.json",
            ),
            transport=httpx.MockTransport(_all_correct_handler),
        )

        # Then the missing bench is skipped with a warning in the run record.
        assert record["benches"] == {}
        assert record["items"] == []
        assert record["composite"] == 0.0
        assert record["warnings"] == [
            "Skipping genmath: item file is missing: missing.jsonl",
        ]

    asyncio.run(scenario())


def test_cli_run_help_exits_zero() -> None:
    # Given the module CLI entry point.
    # When requesting run help.
    result = subprocess.run(
        [sys.executable, "-m", "localbench", "run", "--help"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    # Then argparse exits successfully and shows run options.
    assert result.returncode == 0
    assert "--endpoint" in result.stdout
    assert "--provider" in result.stdout
    assert "--reasoning-effort" in result.stdout


def test_cli_run_when_endpoint_is_missing_exits_two() -> None:
    # Given the module CLI entry point.
    # When running without the required endpoint.
    result = subprocess.run(
        [sys.executable, "-m", "localbench", "run", "--model", "demo-model"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    # Then the parser returns a clean usage error.
    assert result.returncode == 2
    assert "--endpoint" in result.stderr


def test_run_localbench_lane_controls_thinking_toggle(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given a handler that captures every chat-completion request body.
        captured: list[dict] = []

        def capturing_handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/models"):
                captured.append(json.loads(request.content))
            return _all_correct_handler(request)

        # When running in the default answer-only lane.
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                out=tmp_path / "answer_only.json",
            ),
            transport=httpx.MockTransport(capturing_handler),
        )

        # Then every request disables Qwen3-family thinking.
        assert captured
        assert all(
            payload["chat_template_kwargs"] == {"enable_thinking": False}
            for payload in captured
        )

        # When running in the api-uncapped lane.
        captured.clear()
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                out=tmp_path / "uncapped.json",
                lane="api-uncapped",
            ),
            transport=httpx.MockTransport(capturing_handler),
        )

        # Then the local-only field is never sent to API-style endpoints.
        assert captured
        assert all("chat_template_kwargs" not in payload for payload in captured)

    asyncio.run(scenario())


def _mixed_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    payload = json.loads(request.content)
    prompt = payload["messages"][0]["content"]
    if "Choose the first letter" in prompt:
        return _completion("Reasoning. Answer: A", 10, 2)
    if "Choose B" in prompt:
        return _completion("Final answer: C", 10, 2)
    if "Choose D" in prompt:
        return _completion("I cannot tell.", 10, 2)
    if "JSON object with key ok" in prompt:
        return _completion('{"ok": true}', 8, 4)
    if "exactly two words" in prompt:
        return httpx.Response(400, text="bad request")
    if "Compute 2 + 2" in prompt:
        return _completion("The answer is 4.", 6, 2)
    if "Compute 10 / 2" in prompt:
        return _completion("The answer is 6.", 6, 2)
    return httpx.Response(500, text="unexpected prompt")


def _all_correct_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    payload = json.loads(request.content)
    prompt = payload["messages"][0]["content"]
    if "Choose the first letter" in prompt:
        return _completion("Answer: A", 1, 1)
    if "JSON object with key ok" in prompt:
        return _completion('{"ok": true}', 1, 1)
    if "Compute 2 + 2" in prompt:
        return _completion("4", 1, 1)
    return httpx.Response(500, text="unexpected prompt")


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
