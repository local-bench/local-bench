"""End-to-end wiring test for the suite-v1 BFCL (agentic) axis (offline, no API call)."""

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
    benches = render_benches("bfcl", "standard", max_items, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    return benches[0]


def test_v1_agentic_axis_is_declared_in_suite() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then the agentic axis groups BFCL with the probe-determined equal weight (0.25).
    axes = suite["axes"]
    assert axes["agentic"]["benches"] == ["bfcl"]
    assert axes["agentic"]["weight"] == 0.25


def test_v1_bfcl_prompt_is_built_programmatically() -> None:
    # Given the bfcl bench rendered from the suite-v1 manifest.
    bench = _render(max_items=1)

    # Then the function-calling prompt (built by build_bfcl_prompt) is non-empty.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    assert prompt.strip()


def test_v1_bfcl_dispatch_routes_to_score_bfcl() -> None:
    # Given a real bfcl item answered with no function call (a clear miss).
    bench = _render(max_items=1)
    results = [_result(bench.benchmark_items[0]["id"], "I cannot help with that.")]

    # When scored through the production dispatch.
    scored = score_bench(bench, results)

    # Then the bfcl arm routes to score_bfcl (per-item correctness is covered exhaustively by the gate).
    assert scored[0]["bench"] == "bfcl"
    assert scored[0]["correct"] is False
