from __future__ import annotations

import json

from localbench.lane_conformance import (
    assess_conformance,
    assess_run_conformance,
    has_leaked_reasoning,
)


def _item(
    *,
    response_text: str | None = "The answer is A.",
    reasoning_text: str | None = None,
    finish_reason: str | None = "stop",
    error: str | None = None,
) -> dict:
    item = {
        "id": "x",
        "response_text": response_text,
        "reasoning_text": reasoning_text,
        "finish_reason": finish_reason,
    }
    if error is not None:
        item["error"] = error
    return item


def test_clean_run_is_headline_comparable() -> None:
    report = assess_conformance([_item() for _ in range(50)])
    assert report.status == "headline-comparable"
    assert report.n_scored == 50
    assert report.reasons == ()


def test_leaked_reasoning_excludes_a_bench_from_the_headline() -> None:
    leaked = [_item(response_text="<think>let me see</think> The answer is A.") for _ in range(5)]
    report = assess_conformance(leaked + [_item() for _ in range(95)])
    assert report.status == "nonconformant"
    assert report.leaked_reasoning_rate == 0.05
    assert any("leaked" in reason for reason in report.reasons)


def test_pervasive_leaked_reasoning_is_diagnostic_only() -> None:
    leaked = [_item(response_text="<thinking>...</thinking> A") for _ in range(30)]
    report = assess_conformance(leaked + [_item() for _ in range(70)])
    assert report.status == "diagnostic-only"


def test_truncation_excludes_a_bench_from_the_headline() -> None:
    truncated = [_item(finish_reason="length") for _ in range(15)]
    report = assess_conformance(truncated + [_item() for _ in range(85)])
    assert report.status == "nonconformant"
    assert report.truncation_rate == 0.15
    assert any("token cap" in reason for reason in report.reasons)


def test_reasoning_fallback_counts_as_no_final_answer() -> None:
    # _response.py falls back to reasoning_content when content is empty: response_text ends
    # up == reasoning_text. That's a no-final-answer case the empty check alone would miss.
    fallback = [_item(response_text="my chain of thought", reasoning_text="my chain of thought") for _ in range(30)]
    report = assess_conformance(fallback + [_item() for _ in range(70)])
    assert report.no_final_answer_rate == 0.30
    assert report.status == "diagnostic-only"


def test_empty_content_counts_as_no_final_answer() -> None:
    report = assess_conformance([_item(response_text="") for _ in range(12)] + [_item() for _ in range(88)])
    assert report.status == "nonconformant"
    assert report.no_final_answer_rate == 0.12


def test_errored_items_are_excluded_from_conformance_rates() -> None:
    errors = [_item(response_text=None, finish_reason=None, error="timeout") for _ in range(40)]
    report = assess_conformance(errors + [_item() for _ in range(10)])
    assert report.status == "headline-comparable"
    assert report.n_scored == 10


def test_no_scored_items_is_diagnostic_only() -> None:
    report = assess_conformance([_item(error="boom") for _ in range(5)])
    assert report.status == "diagnostic-only"
    assert report.n_scored == 0


def test_has_leaked_reasoning_matches_fence_variants_but_not_the_bare_word() -> None:
    for leaked in ("<think>x</think> a", "<thought>y</thought> a", "◁think▷ z", "<|think|> w", "<|begin_of_thought|> v"):
        assert has_leaked_reasoning(leaked) is True, leaked
    # The bare word "think" in a normal answer is NOT a leak (delimiter required).
    assert has_leaked_reasoning("I think the answer is 42.") is False
    assert has_leaked_reasoning("The answer is 42.") is False
    assert has_leaked_reasoning(None) is False


def test_report_as_dict_is_json_serializable() -> None:
    payload = assess_conformance([_item() for _ in range(3)]).as_dict()
    assert isinstance(payload["reasons"], list)
    json.dumps(payload)


def test_run_conformance_takes_the_worst_bench_and_does_not_dilute() -> None:
    # The autoreview blocker: a bench-local failure must not be diluted by the rest of the
    # run. IFBench truncates 15% of ITS items; pooled run-wide that's 15/615 ~= 2.4% and
    # would pass. Per-bench, IFBench is nonconformant -> the whole run is nonconformant.
    results_by_bench = {
        "mmlu_pro": [_item() for _ in range(500)],
        "ifbench": [_item(finish_reason="length") for _ in range(15)] + [_item() for _ in range(85)],
    }
    run = assess_run_conformance(results_by_bench)
    assert run["status"] == "nonconformant"
    assert run["worst_bench"] == "ifbench"
    assert run["n_scored"] == 600
    assert run["per_bench"]["mmlu_pro"]["status"] == "headline-comparable"


def test_run_conformance_clean_when_every_bench_is_clean() -> None:
    run = assess_run_conformance({"mmlu_pro": [_item() for _ in range(20)], "ifbench": [_item() for _ in range(20)]})
    assert run["status"] == "headline-comparable"
    assert run["worst_bench"] is None
    assert run["reasons"] == []
