"""End-to-end wiring test for the suite-v1 math axis (offline, no API call)."""

from __future__ import annotations

from pathlib import Path

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
        "started_at": "2026-06-14T00:00:00+00:00",
        "finished_at": "2026-06-14T00:00:00+00:00",
        "attempts": 1,
        "error": None,
    }


def _render(bench_name: str, max_items: int) -> RenderedBench:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    benches = render_benches(bench_name, "standard", max_items, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    return benches[0]


def test_v1_math_axis_is_declared_in_suite() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then the math axis groups the two olympiad benches with the probe-determined equal weight (0.25).
    axes = suite["axes"]
    assert axes["math"]["benches"] == ["amo", "olymmath_hard"]
    assert axes["math"]["weight"] == 0.25


def test_v1_math_prompt_renders_statement_and_boxed_instruction() -> None:
    # Given the amo bench rendered from the suite-v1 manifest.
    bench = _render("amo", max_items=1)

    # Then the prompt embeds the problem statement and asks for a boxed final answer.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    statement = str(bench.source_items[0]["statement"])
    assert statement[:30] in prompt
    assert "boxed" in prompt


def test_v1_math_dispatch_scores_correct_and_wrong_via_symbolic_scorer() -> None:
    # Given two amo items, answered with a correct boxed gold and a clearly-wrong constant.
    bench = _render("amo", max_items=2)
    gold_0 = str(bench.source_items[0]["answer"])
    results = [
        _result(bench.benchmark_items[0]["id"], "After working it out, \\boxed{" + gold_0 + "}"),
        _result(bench.benchmark_items[1]["id"], "After working it out, \\boxed{999999983}"),
    ]

    # When the bench is scored through the production dispatch (routes to math_symbolic.verify_math).
    scored = score_bench(bench, results)

    # Then the correct boxed answer is accepted and the wrong one rejected.
    assert scored[0]["correct"] is True
    assert scored[0]["extracted"] is not None
    assert scored[1]["correct"] is False
