"""End-to-end wiring test for the suite-v1 SuperGPQA (knowledge) axis (offline, no API call)."""

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


def _render(max_items: int) -> RenderedBench:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    benches = render_benches("supergpqa", "standard", max_items, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    return benches[0]


def test_v1_knowledge_axis_is_declared_in_suite() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then the knowledge axis groups SuperGPQA with a probe-determined (unset) weight.
    axes = suite["axes"]
    assert axes["knowledge"]["benches"] == ["supergpqa"]
    assert axes["knowledge"]["weight"] is None


def test_v1_supergpqa_prompt_renders_question_and_answer_instruction() -> None:
    # Given the SuperGPQA bench rendered from the suite-v1 manifest.
    bench = _render(max_items=1)

    # Then the prompt embeds the question and asks for a single-letter answer.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    question = str(bench.source_items[0]["question"])
    assert question[:30] in prompt
    assert "Answer:" in prompt


def test_v1_supergpqa_dispatch_scores_correct_and_wrong_via_mcq_scorer() -> None:
    # Given two SuperGPQA items answered with the gold letter and a different (wrong) letter.
    bench = _render(max_items=2)
    gold_0 = str(bench.source_items[0]["answer"])
    gold_1 = str(bench.source_items[1]["answer"])
    wrong_1 = "A" if gold_1 != "A" else "B"
    results = [
        _result(bench.benchmark_items[0]["id"], f"Reasoning... Answer: {gold_0}"),
        _result(bench.benchmark_items[1]["id"], f"Reasoning... Answer: {wrong_1}"),
    ]

    # When the bench is scored through the production dispatch (routes to mcq.score_mcq_detailed).
    scored = score_bench(bench, results)

    # Then the gold letter is accepted and the wrong letter rejected.
    assert scored[0]["correct"] is True
    assert scored[0]["extracted"] == gold_0
    assert scored[1]["correct"] is False
