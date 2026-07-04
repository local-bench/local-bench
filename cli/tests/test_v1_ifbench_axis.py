"""End-to-end wiring test for the suite-v1 IFBench (instruction-following) axis (offline, no API)."""

from __future__ import annotations

from pathlib import Path

from localbench._scoring import _score_response
from localbench._suite import read_json_object, render_benches

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v1"


def test_v1_instruction_following_axis_is_declared_in_suite() -> None:
    # Given the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")

    # Then the instruction-following axis groups IFBench; axis weights live in the
    # code registry (localbench.scoring.axes), not suite.json (METHODOLOGY-v1.2 §8).
    axes = suite["axes"]
    assert axes["instruction_following"]["benches"] == ["ifbench"]
    assert "weight" not in axes["instruction_following"]


def test_v1_ifbench_prompt_renders_verbatim_prompt() -> None:
    # Given the ifbench bench rendered from the suite-v1 manifest.
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    benches = render_benches("ifbench", "standard", 1, _SUITE_DIR, suite, warnings)
    assert warnings == [], warnings
    assert len(benches) == 1
    bench = benches[0]

    # Then the rendered prompt is the item's instruction prompt verbatim.
    prompt = bench.benchmark_items[0]["messages"][0]["content"]
    assert prompt == str(bench.source_items[0]["prompt"])
    assert prompt.strip()


def test_v1_ifbench_dispatch_routes_to_score_ifbench() -> None:
    # Given a constructed IFBench item with a deterministic constraint.
    item = {
        "id": "ifbench-axis-001",
        "key": "fixture",
        "prompt": "Respond with no whitespace.",
        "instruction_id_list": ["format:no_whitespace"],
        "kwargs": [{}],
    }

    # When scoring a satisfying and a violating response through the production dispatch.
    passed = _score_response("ifbench", item, "NoSpaces", None)
    failed = _score_response("ifbench", item, "Has spaces here", None)

    # Then the ifbench arm routes to score_ifbench (no extraction; strict pass/fail).
    assert passed == (None, True)
    assert failed == (None, False)
