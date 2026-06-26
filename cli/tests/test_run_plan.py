from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from localbench._scoring import composite
from localbench._suite import read_json_object, render_benches
from localbench.orchestrate import OrchestrateConfig, run_localbench
from localbench.run_plan import SCORED_DEFAULT_BENCHES, resolve_run_benches

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v1"
_OPT_IN_BENCHES = {
    "amo",
    "olymmath_hard",
    "bfcl",
    "bfcl_multi_turn",
    "lcb",
    "ruler_32k",
    "bigcodebench_hard",
}
_IFBENCH_PASSING_RESPONSE = (
    "kaleidoscope nebula nebula whisper whisper whisper "
    "labyrinth labyrinth labyrinth labyrinth labyrinth "
    "paradox paradox paradox paradox paradox paradox paradox"
)


def test_resolve_run_benches_when_all_uses_scored_default() -> None:
    # Given the v1 suite containing scored defaults and opt-in lanes.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # When resolving the run-level "all" choice.
    benches = resolve_run_benches("all", suite)

    # Then the scored default endpoint axes include the zero-weight Tool-calling axis.
    assert benches == ["mmlu_pro", "ifbench", "tc_json_v1"]
    assert tuple(benches) == SCORED_DEFAULT_BENCHES
    assert not _OPT_IN_BENCHES.intersection(benches)


def test_resolve_run_benches_when_explicit_list_preserves_opt_in_choices() -> None:
    # Given the v1 suite.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # When resolving an explicit opt-in list.
    benches = resolve_run_benches("mmlu_pro,amo", suite)

    # Then the caller's exact requested benches are preserved.
    assert benches == ["mmlu_pro", "amo"]


def test_render_benches_all_still_expands_full_suite() -> None:
    # Given the v1 suite and the low-level renderer.
    suite = read_json_object(_SUITE_DIR / "suite.json")
    suite_benches = suite["benches"]
    assert isinstance(suite_benches, dict)
    warnings: list[str] = []

    # When render_benches receives its historical "all" choice directly.
    rendered = render_benches("all", "standard", 1, _SUITE_DIR, suite, warnings)

    # Then it still expands to every suite.json bench for non-run callers.
    assert warnings == []
    assert [bench.name for bench in rendered] == list(suite_benches)
    assert _OPT_IN_BENCHES.issubset({bench.name for bench in rendered})


def test_run_localbench_when_bench_all_measures_tool_calling_without_changing_composite(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given the v1 suite and a handler that can answer the scored default benches.
        output_path = tmp_path / "default-run.json"

        # When running the default bench choice through the orchestrator.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=_SUITE_DIR,
                tier="standard",
                out=output_path,
                max_items=1,
            ),
            transport=httpx.MockTransport(_v1_scored_default_handler),
        )

        # Then knowledge, instruction-following, and Tool-calling are measured.
        assert list(record["benches"]) == ["mmlu_pro", "ifbench", "tc_json_v1"]
        assert [item["bench"] for item in record["items"]] == [
            "mmlu_pro",
            "ifbench",
            "tc_json_v1",
        ]
        axes = record["axis_status"]["axes"]
        assert axes["knowledge"] == {
            "axis": "knowledge",
            "status": "measured",
            "reason": "ok",
        }
        assert axes["instruction_following"] == {
            "axis": "instruction_following",
            "status": "measured",
            "reason": "ok",
        }
        assert axes["tool_calling"] == {
            "axis": "tool_calling",
            "status": "measured",
            "reason": "ok",
        }
        for axis in ("math", "agentic", "coding", "long_context"):
            assert axes[axis] == {
                "axis": axis,
                "status": "not_measured",
                "reason": "not_run",
            }
        assert record["benches"]["tc_json_v1"]["chance_corrected"] == pytest.approx(1.0)
        ki_only = {
            "mmlu_pro": record["benches"]["mmlu_pro"],
            "ifbench": record["benches"]["ifbench"],
        }
        assert record["composite"] == pytest.approx(composite(ki_only))
        assert record["composite"] == pytest.approx(1.0)

    asyncio.run(scenario())


def test_run_localbench_zero_scoring_tool_calling_does_not_move_composite(tmp_path: Path) -> None:
    # Load-bearing leak guard for the "candidate weight 0 -> excluded from the Index"
    # invariant. Here Tool-calling RUNS but scores 0 (wrong tool name) while Knowledge +
    # Instruction pass. The composite must still equal the K+I-only composite (== 1.0):
    # if tool_calling ever carried a positive weight, a 0-scoring tool axis would pull the
    # composite below 1.0 and fail these assertions. (The sibling test above only proves
    # invariance when the tool axis also scores 1.0, which a leak could not move.)
    async def scenario() -> None:
        output_path = tmp_path / "tool-fail-run.json"
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=_SUITE_DIR,
                tier="standard",
                out=output_path,
                max_items=1,
            ),
            transport=httpx.MockTransport(_v1_tool_failing_handler),
        )

        # Tool-calling still RAN to completion (measured), it just scored 0.
        axes = record["axis_status"]["axes"]
        assert axes["tool_calling"] == {
            "axis": "tool_calling",
            "status": "measured",
            "reason": "ok",
        }
        assert record["benches"]["tc_json_v1"]["chance_corrected"] == pytest.approx(0.0, abs=1e-9)

        # Knowledge + Instruction still pass, so the composite is UNCHANGED by the failing
        # tool axis -> proves weight-0 candidate exclusion.
        ki_only = {
            "mmlu_pro": record["benches"]["mmlu_pro"],
            "ifbench": record["benches"]["ifbench"],
        }
        assert record["composite"] == pytest.approx(composite(ki_only))
        assert record["composite"] == pytest.approx(1.0)

    asyncio.run(scenario())


def _v1_scored_default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    payload = json.loads(request.content)
    prompt = payload["messages"][0]["content"]
    if "specific entropy" in prompt:
        return _completion("Answer: H", 1, 1)
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


def _v1_tool_failing_handler(request: httpx.Request) -> httpx.Response:
    # Identical to _v1_scored_default_handler except the tool-calling answer names the
    # WRONG tool, so tc_json_v1 parses + is measured yet scores 0 (canonical mismatch).
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
    payload = json.loads(request.content)
    prompt = payload["messages"][0]["content"]
    if "specific entropy" in prompt:
        return _completion("Answer: H", 1, 1)
    if "kaleidoscope" in prompt:
        return _completion(_IFBENCH_PASSING_RESPONSE, 1, 1)
    if "calculate_triangle_area" in prompt:
        return _completion(
            json.dumps(
                {
                    "schema_version": "localbench.tc.v1",
                    "calls": [
                        {
                            "name": "not_the_expected_tool",
                            "arguments": {"base": 10, "height": 5},
                        },
                    ],
                },
            ),
            1,
            1,
        )
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
