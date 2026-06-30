"""End-to-end wiring test for the suite-v1 BFCL multi-turn agentic bench."""

from __future__ import annotations

import json
from pathlib import Path

from localbench._scoring import score_bench
from localbench._suite import RenderedBench, read_json_object, render_benches
from localbench._types import ItemResult, Usage

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v1"


def test_v1_bfcl_multi_turn_bench_is_retained_but_not_agentic_membership() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then BFCL multi-turn content remains available, while Agentic membership follows axes.py.
    assert "bfcl_multi_turn" in suite["benches"]
    assert suite["axes"]["agentic"]["benches"] == ["appworld_c"]


def test_v1_bfcl_multi_turn_prompt_is_built_programmatically() -> None:
    # Given the bfcl_multi_turn bench rendered from the suite-v1 manifest.
    bench = _render(max_items=1)

    # Then the multi-turn action-trace prompt is non-empty and asks for JSON.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    assert "Return only a JSON array" in prompt
    assert "Turn 1" in prompt


def test_v1_bfcl_multi_turn_dispatch_routes_to_scorer_with_failure_kind() -> None:
    # Given a real bfcl_multi_turn item answered with its stored trace and a wrong trace.
    bench = _render(max_items=1)
    item = bench.source_items[0]
    correct = _result(bench.benchmark_items[0]["id"], json.dumps(item["ground_truth"]))
    wrong = _result(bench.benchmark_items[0]["id"], "not a trace")

    # When scored through the production dispatch.
    scored = score_bench(bench, [correct])
    missed = score_bench(bench, [wrong])

    # Then the separate bench routes to the multi-turn scorer and records failure taxonomy.
    assert scored[0]["bench"] == "bfcl_multi_turn"
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
        "started_at": "2026-06-14T00:00:00+00:00",
        "finished_at": "2026-06-14T00:00:00+00:00",
        "attempts": 1,
        "error": None,
    }


def _render(max_items: int) -> RenderedBench:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    benches = render_benches("bfcl_multi_turn", "standard", max_items, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    return benches[0]
