"""End-to-end wiring test for the suite-v1 LCB (coding) axis (offline, no API call)."""

from __future__ import annotations

from pathlib import Path

import pytest

from localbench._scoring import score_bench
from localbench._suite import RenderedBench, read_json_object, render_benches
from localbench._types import ItemResult, Usage

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v1"


def _usage() -> Usage:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _result(item_id: str, response_text: str) -> ItemResult:
    return {
        "id": item_id,
        "response_text": response_text,
        "reasoning_text": None,
        "finish_reason": "stop",
        "usage": _usage(),
        "latency_seconds": 0.0,
        "started_at": "2026-06-16T00:00:00+00:00",
        "finished_at": "2026-06-16T00:00:00+00:00",
        "attempts": 1,
        "error": None,
    }


def _render(max_items: int) -> RenderedBench:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    benches = render_benches("lcb", "standard", max_items, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    return benches[0]


def test_v1_coding_axis_is_declared_in_suite() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then the coding axis groups LCB; axis weights live in the code registry, not suite.json (METHODOLOGY-v1.2 §8).
    axes = suite["axes"]
    assert axes["coding"]["benches"] == ["lcb"]
    assert "weight" not in axes["coding"]


def test_v1_lcb_prompt_renders_prediction_task() -> None:
    # Given the lcb bench rendered from the suite-v1 manifest.
    bench = _render(max_items=1)

    # Then the prompt embeds the problem, function stub, testcase input, and output-only instruction.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    source = bench.source_items[0]
    assert str(source["question_content"])[:40] in prompt
    assert str(source["starter_code"]).splitlines()[0] in prompt
    assert str(source["input"]) in prompt
    assert "Only return the predicted output" in prompt


def test_v1_lcb_dispatch_routes_to_score_lcb() -> None:
    # Given a real lcb item answered with its expected output and a wrong output.
    bench = _render(max_items=1)
    item = bench.source_items[0]
    correct = _result(bench.benchmark_items[0]["id"], str(item["answer"]))
    wrong = _result(bench.benchmark_items[0]["id"], "__definitely_wrong__")

    # When scored through the production dispatch.
    scored = score_bench(bench, [correct])
    missed = score_bench(bench, [wrong])

    # Then the lcb arm routes to score_lcb.
    assert scored[0]["bench"] == "lcb"
    assert scored[0]["correct"] is True
    assert scored[0]["extracted"] is not None
    assert missed[0]["correct"] is False


def test_existing_four_axis_composite_is_unchanged_when_coding_domain_is_absent() -> None:
    # Given the four suite-v1 domains present before adding Coding.
    from localbench._scoring import BenchAggregate, composite

    benches: dict[str, BenchAggregate] = {
        "mmlu_pro": _aggregate(0.50),
        "ifbench": _aggregate(0.60),
        "bfcl": _aggregate(0.70),
        "amo": _aggregate(0.80),
    }

    # When computing the composite with Coding declared but absent from the run.
    result = composite(benches)

    # Then only the HEADLINE axes (knowledge=mmlu_pro + instruction=ifbench) enter
    # the composite; agentic (bfcl) + math (amo) are present but weight 0.0
    # (METHODOLOGY-v1.2 §3), so adding/removing them never moves the headline.
    assert result == pytest.approx(((0.15 * 0.50) + (0.15 * 0.60)) / 0.30)


def _aggregate(score: float) -> "BenchAggregate":
    from localbench._scoring import BenchAggregate

    return {
        "n": 10,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": score,
        "chance_corrected": score,
    }
