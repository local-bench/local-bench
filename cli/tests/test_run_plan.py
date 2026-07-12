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
    "bfcl",
    "bfcl_multi_turn",
    "ruler_32k",
    "lcb",
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

    # Then the scored default endpoint axes include math, tool-calling, coding generation, and the Agentic inline attempt.
    assert benches == ["mmlu_pro", "ifbench", "olymmath_hard", "amo", "tc_json_v1", "bigcodebench_hard", "appworld_c"]
    assert tuple(benches) != SCORED_DEFAULT_BENCHES
    assert "bfcl_multi_turn_base" in SCORED_DEFAULT_BENCHES
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


def test_run_localbench_when_bench_all_marks_agentic_unavailable_without_crashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        # Given the v1 suite and a handler that can answer the scored default benches.
        output_path = tmp_path / "default-run.json"
        monkeypatch.delenv("APPWORLD_ROOT", raising=False)

        # When running the default bench choice through the orchestrator without agentic seams.
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

        # Then appworld_c is attempted outside the HTTP/render path and degrades honestly.
        assert list(record["benches"]) == ["mmlu_pro", "ifbench", "olymmath_hard", "amo", "tc_json_v1", "bigcodebench_hard"]
        assert [item["bench"] for item in record["items"]] == [
            "mmlu_pro",
            "ifbench",
            "olymmath_hard",
            "amo",
            "tc_json_v1",
            "bigcodebench_hard",
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
        assert axes["coding"]["axis"] == "coding"
        assert axes["coding"]["status"] == "generated_unverified"
        assert axes["coding"]["reason"] == "verdict_pending"
        assert "verifier verdict pending" in axes["coding"]["detail"]
        assert axes["agentic"]["axis"] == "agentic"
        assert axes["agentic"]["status"] == "not_measured"
        assert axes["agentic"]["reason"] == "sandbox_unavailable"
        assert "appworld sandbox unavailable:" in axes["agentic"]["detail"]
        assert axes["math"] == {"axis": "math", "status": "measured", "reason": "ok"}
        assert axes["long_context"] == {"axis": "long_context", "status": "not_measured", "reason": "not_run"}
        assert record["benches"]["tc_json_v1"]["chance_corrected"] == pytest.approx(1.0)
        measured_without_agentic = {
            "mmlu_pro": record["benches"]["mmlu_pro"],
            "ifbench": record["benches"]["ifbench"],
            "olymmath_hard": record["benches"]["olymmath_hard"],
            "amo": record["benches"]["amo"],
            "tc_json_v1": record["benches"]["tc_json_v1"],
        }
        assert record["scores"]["partial_composite"] == pytest.approx(round(composite(measured_without_agentic), 4))
        assert record["scores"]["partial_composite"] == pytest.approx(0.8571)
        assert record["headline_complete"] is False

    asyncio.run(scenario())


def test_run_localbench_partial_tool_use_does_not_enter_composite(tmp_path: Path) -> None:
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

        measured_without_agentic = {
            "mmlu_pro": record["benches"]["mmlu_pro"],
            "ifbench": record["benches"]["ifbench"],
            "olymmath_hard": record["benches"]["olymmath_hard"],
            "amo": record["benches"]["amo"],
            "tc_json_v1": record["benches"]["tc_json_v1"],
        }
        assert record["scores"]["partial_composite"] == pytest.approx(round(composite(measured_without_agentic), 4))
        assert record["scores"]["partial_composite"] == pytest.approx(0.8571)

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
    if "findPeaks" in prompt:
        return _completion("[]", 1, 1)
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
    if "findPeaks" in prompt:
        return _completion("[]", 1, 1)
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
