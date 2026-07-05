from __future__ import annotations

import json

from localbench.lane_conformance import (
    assess_conformance,
    assess_run_conformance,
    has_leaked_reasoning,
)
from localbench.orchestrate import _audit_forced_cap_hits


def _item(
    *,
    response_text: str | None = "The answer is A.",
    reasoning_text: str | None = None,
    finish_reason: str | None = "stop",
    error: str | None = None,
    completion_tokens: int | None = 8,
    max_tokens: int | None = 32,
) -> dict:
    item = {
        "id": "x",
        "response_text": response_text,
        "reasoning_text": reasoning_text,
        "finish_reason": finish_reason,
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": completion_tokens,
            "total_tokens": None if completion_tokens is None else completion_tokens + 1,
        },
    }
    if max_tokens is not None:
        item["max_tokens"] = max_tokens
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


def test_forced_truncation_is_a_scored_failure_not_a_headline_exclusion() -> None:
    # Budget-forcing: a cap hit means the model looped/failed to terminate (scored wrong),
    # not a measurement breach. The run stays headline-comparable with a visible diagnostic.
    truncated = [_item(finish_reason="length") for _ in range(17)]
    report = assess_conformance(truncated + [_item() for _ in range(83)], forced=True)
    assert report.status == "headline-comparable"
    assert report.forced is True
    assert report.truncation_rate == 0.17
    assert any("answer_cap_hit_rate" in reason for reason in report.reasons)
    assert not any("token cap" in reason for reason in report.reasons)


def test_forced_run_still_gates_on_leaked_reasoning() -> None:
    leaked = [_item(response_text="<think>oops</think> A") for _ in range(5)]
    report = assess_conformance(leaked + [_item() for _ in range(95)], forced=True)
    assert report.status == "nonconformant"  # leaked is a hard gate even under forcing


def test_forced_run_still_gates_on_no_final_answer() -> None:
    empty = [_item(response_text="") for _ in range(12)]
    report = assess_conformance(empty + [_item() for _ in range(88)], forced=True)
    assert report.status == "nonconformant"  # no-final-answer is a hard gate even under forcing


def test_bounded_final_cap_hit_is_visible_but_headline_comparable() -> None:
    capped = [_item(finish_reason="length", completion_tokens=32, max_tokens=32) for _ in range(17)]
    report = assess_conformance(
        capped + [_item(max_tokens=32) for _ in range(83)],
        lane_spec_id="bounded-final-v1",
    )

    assert report.status == "headline-comparable"
    assert report.truncation_rate == 0.17
    assert report.budget_cap_hit_rate == 0.17
    assert report.measurement_truncation_rate == 0.0
    assert any("budget_cap_hit_rate" in reason for reason in report.reasons)


def test_bounded_final_measurement_truncation_excludes_run() -> None:
    truncated = [
        _item(finish_reason="length", completion_tokens=16, max_tokens=32)
        for _ in range(3)
    ]
    report = assess_conformance(
        truncated + [_item(max_tokens=32) for _ in range(97)],
        lane_spec_id="bounded-final-v1",
    )

    assert report.status == "nonconformant"
    assert report.budget_cap_hit_rate == 0.0
    assert report.measurement_truncation_rate == 0.03
    assert any("measurement_truncation_rate" in reason for reason in report.reasons)


def test_bounded_final_empty_final_scores_zero_without_excluding() -> None:
    empty = [_item(response_text="") for _ in range(12)]
    report = assess_conformance(
        empty + [_item() for _ in range(88)],
        lane_spec_id="bounded-final-v1",
    )

    assert report.status == "headline-comparable"
    assert report.empty_final_rate == 0.12
    assert report.ambiguous_or_contaminated_final_rate == 0.0


def test_bounded_final_contaminated_final_excludes_at_two_percent() -> None:
    contaminated = [
        _item(response_text="<think>scratch</think> The answer is A.")
        for _ in range(3)
    ]
    report = assess_conformance(
        contaminated + [_item() for _ in range(97)],
        lane_spec_id="bounded-final-v1",
    )

    assert report.status == "nonconformant"
    assert report.ambiguous_or_contaminated_final_rate == 0.03
    assert any("ambiguous_or_contaminated_final_rate" in reason for reason in report.reasons)


def test_run_level_forced_threads_to_every_bench() -> None:
    results = {
        "mmlu_pro": [_item(finish_reason="length") for _ in range(15)] + [_item() for _ in range(85)],
        "ifbench": [_item() for _ in range(100)],
    }
    forced = assess_run_conformance(results, forced=True)
    assert forced["status"] == "headline-comparable"
    assert forced["per_bench"]["mmlu_pro"]["forced"] is True
    unforced = assess_run_conformance(results, forced=False)
    assert unforced["status"] == "nonconformant"  # single-pass truncation still excludes


def test_run_conformance_detects_gemma_channel_family_leaks() -> None:
    # Given enough scored items leaking Gemma channel scaffolding to breach the hard gate.
    results = {
        "ifbench": [
            _item(response_text="<|channel>thought\n<channel|>Final answer: A")
            for _ in range(3)
        ]
        + [_item() for _ in range(97)]
    }

    # When assessing the full run.
    run = assess_run_conformance(results)

    # Then the bench is nonconformant instead of headline-comparable.
    assert run["status"] == "nonconformant"
    assert run["worst_bench"] == "ifbench"
    assert run["per_bench"]["ifbench"]["leaked_reasoning_rate"] == 0.03


def test_run_conformance_unions_canonical_and_per_lane_leak_regexes() -> None:
    # Given a lane-specific leak regex that is not part of the canonical detector.
    results = {
        "ifbench": [_item(response_text="<custom_lane_leak> A") for _ in range(3)]
        + [_item() for _ in range(97)]
    }

    # When assessing conformance with per-lane registry regexes.
    run = assess_run_conformance(
        results,
        leak_regexes_by_bench={"ifbench": (r"<custom_lane_leak>",)},
    )

    # Then the per-lane leak still trips the unchanged 2% conformance gate.
    assert run["status"] == "nonconformant"
    assert run["per_bench"]["ifbench"]["leaked_reasoning_rate"] == 0.03


def test_audit_flags_a_cap_hit_that_scored_correct() -> None:
    items = [
        {"id": "a", "finish_reason": "length", "correct": True},
        {"id": "b", "finish_reason": "length", "correct": False},
        {"id": "c", "finish_reason": "stop", "correct": True},
    ]
    warnings = _audit_forced_cap_hits(items, forcing_active=True)  # type: ignore[arg-type]
    assert len(warnings) == 1
    assert "SCORER-GATE BUG" in warnings[0] and "a" in warnings[0]
    # no audit when forcing is off, or when no cap hit scored correct
    assert _audit_forced_cap_hits(items, forcing_active=False) == []  # type: ignore[arg-type]
    clean = [{"id": "b", "finish_reason": "length", "correct": False}]
    assert _audit_forced_cap_hits(clean, forcing_active=True) == []  # type: ignore[arg-type]


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
    for leaked in (
        "<think>x</think> a",
        "<thought>y</thought> a",
        "◁think▷ z",
        "<|think|> w",
        "<|begin_of_thought|> v",
        "<|channel|>analysis\nscratch<|message|> a",
        "<|channel>thought\n<channel|> a",
    ):
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
