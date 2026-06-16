"""End-to-end wiring test for the suite-v1 ToolHop agentic bench."""

from __future__ import annotations

import json
from pathlib import Path

from localbench._scoring import score_bench
from localbench._suite import RenderedBench, read_json_object, render_benches
from localbench._types import ItemResult, Usage
from localbench.scoring.metadata import domain_for_bench

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v1"


def test_v1_toolhop_bench_is_separate_agentic_line() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then ToolHop is its own Agentic bench, not merged into BFCL.
    assert "toolhop" in suite["benches"]
    assert "toolhop" in suite["axes"]["agentic"]["benches"]
    assert "bfcl_multi_turn" in suite["axes"]["agentic"]["benches"]
    assert domain_for_bench("toolhop") == "Agentic"


def test_v1_toolhop_prompt_is_built_programmatically() -> None:
    # Given the toolhop bench rendered from the suite-v1 manifest.
    bench = _render(max_items=1)

    # Then the prompt is non-empty and asks for a flat JSON tool-call trace.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    assert "Return only a JSON array" in prompt
    assert "Available tools" in prompt
    assert "gold_calls" not in prompt


def test_v1_toolhop_dispatch_routes_to_scorer_with_failure_kind() -> None:
    # Given a rendered item with a stored real-item golden trace.
    bench = _render(max_items=None)
    item_index = next(
        index for index, item in enumerate(bench.source_items) if item.get("gold_calls")
    )
    item = bench.source_items[item_index]
    item_id = bench.benchmark_items[item_index]["id"]
    correct = _result(item_id, json.dumps(item["gold_calls"]))
    wrong = _result(item_id, "not a trace")

    # When scored through the production dispatch.
    scored = score_bench(
        RenderedBench(
            name=bench.name,
            source_items=[item],
            benchmark_items=[bench.benchmark_items[item_index]],
            baseline=bench.baseline,
            decoding=bench.decoding,
            item_file=bench.item_file,
        ),
        [correct],
    )
    missed = score_bench(
        RenderedBench(
            name=bench.name,
            source_items=[item],
            benchmark_items=[bench.benchmark_items[item_index]],
            baseline=bench.baseline,
            decoding=bench.decoding,
            item_file=bench.item_file,
        ),
        [wrong],
    )

    # Then the separate bench routes to ToolHop and records the failure taxonomy.
    assert scored[0]["bench"] == "toolhop"
    assert scored[0]["correct"] is True
    assert scored[0]["failure_kind"] is None
    assert missed[0]["correct"] is False
    assert missed[0]["failure_kind"] == "malformed_call"


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


def _render(max_items: int | None) -> RenderedBench:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    benches = render_benches("toolhop", "standard", max_items, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    return benches[0]
