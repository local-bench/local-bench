"""Verdict-carried (dynamic-bench) handling in the projection rescorer.

Agentic benches (``appworld_c``) ship no static item set in the suite — re-scoring them
needs the live AppWorld evaluator, so the projection carries the bundle's per-item
verdicts instead. These tests pin the trust boundary of that path:

  * eligibility is derived ONLY from the suite dir's scorecard registry (headline axes),
  * candidate-axis and unknown benches are still rejected,
  * carried verdicts cannot be duplicated to inflate the axis,
  * the aggregate for a carried bench uses a zero chance-correction baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.submissions.projection import (
    _axis_status_from_dynamic_verdicts,
    _bench_aggregates,
    _dynamic_benches,
    _locally_graded_benches,
    _scored_items,
)
from localbench.scoring.axis_status import axis_status_for_benches
from localbench.submissions.validate import SubmissionValidationError, SuiteItem


def _suite_dir_with_scorecard(tmp_path: Path) -> Path:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "SCORECARD.json").write_text(
        json.dumps(
            {
                "registry": [
                    {"key": "knowledge", "role": "headline", "benches": ["statbench"], "weight": 0.5},
                    {"key": "agentic", "role": "headline", "benches": ["dynbench"], "weight": 0.5},
                    {"key": "math", "role": "candidate", "benches": ["candbench"], "weight": 0.0},
                ],
            },
        ),
        encoding="utf-8",
    )
    return suite_dir


def _static_suite_items() -> dict[tuple[str, str], SuiteItem]:
    return {
        ("statbench", "s1"): SuiteItem(
            bench="statbench",
            item_id="s1",
            source={"id": "s1"},
            baseline=0.25,
            item_sha256="0" * 64,
        ),
    }


def _dynamic_item(item_id: str, *, correct: bool) -> dict[str, object]:
    return {
        "bench": "dynbench",
        "id": item_id,
        "correct": correct,
        "response_text": None,
        "extracted": None,
        "finish_reason": None,
        "latency_seconds": 0.0,
        "started_at": "2026-07-04T00:00:00+00:00",
        "finished_at": "2026-07-04T00:00:00+00:00",
        "attempts": 1,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        "error": None,
    }


def test_dynamic_benches_are_headline_axes_without_static_sources(tmp_path: Path) -> None:
    # Given: a scorecard with a static headline bench, a dynamic headline bench, and a
    # candidate-axis bench that also has no static source.
    suite_dir = _suite_dir_with_scorecard(tmp_path)

    # When: eligibility is derived from the suite dir + the static item index.
    dynamic = _dynamic_benches(suite_dir, _static_suite_items())

    # Then: only the headline bench WITHOUT a static source is verdict-carried eligible.
    assert dynamic == frozenset({"dynbench"})


def test_dynamic_benches_come_from_release_manifest_coverage(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite_release_manifest.json").write_text(
        json.dumps(
            {
                "coverage_profile": {
                    "benches": ["statbench", "dynbench", "candidate_without_items"],
                },
            },
        ),
        encoding="utf-8",
    )
    (suite_dir / "SCORECARD.json").write_text(
        json.dumps(
            {
                "registry": [
                    {"key": "agentic", "role": "headline", "benches": ["wrong_fallback"]},
                ],
            },
        ),
        encoding="utf-8",
    )

    dynamic = _dynamic_benches(suite_dir, _static_suite_items())

    assert dynamic == frozenset({"dynbench", "candidate_without_items"})


def test_scored_items_carries_dynamic_verdicts_verbatim() -> None:
    items = [_dynamic_item("t1", correct=True), _dynamic_item("t2", correct=False)]

    scored = _scored_items(items, _static_suite_items(), frozenset({"dynbench"}))

    assert [(item["id"], item["correct"]) for item in scored] == [("t1", True), ("t2", False)]
    assert all(item["bench"] == "dynbench" for item in scored)


def test_locally_graded_static_coding_verdict_is_carried() -> None:
    suite_items = {
        ("bigcodebench_hard", "code-1"): SuiteItem(
            bench="bigcodebench_hard",
            item_id="code-1",
            source={"id": "code-1", "answer": "would-rescore-false"},
            baseline=0.0,
            item_sha256="0" * 64,
        ),
    }
    item = {
        **_dynamic_item("code-1", correct=True),
        "bench": "bigcodebench_hard",
        "code_artifact": {
            "verdict_source": "verifier",
            "image_digest": "image@sha256:" + "a" * 64,
            "verdict": {"passed": True},
        },
    }

    carried = _locally_graded_benches([item])
    scored = _scored_items([item], suite_items, carried)

    assert carried == frozenset({"bigcodebench_hard"})
    assert scored[0]["correct"] is True


def test_scored_items_still_rejects_unknown_bench() -> None:
    items = [{**_dynamic_item("t1", correct=True), "bench": "madeupbench"}]

    with pytest.raises(SubmissionValidationError, match="unknown item: madeupbench/t1"):
        _scored_items(items, _static_suite_items(), frozenset({"dynbench"}))


def test_scored_items_rejects_candidate_axis_bench_without_source(tmp_path: Path) -> None:
    # candbench has no static source AND is not headline -> not eligible -> unknown.
    suite_dir = _suite_dir_with_scorecard(tmp_path)
    dynamic = _dynamic_benches(suite_dir, _static_suite_items())
    items = [{**_dynamic_item("c1", correct=True), "bench": "candbench"}]

    with pytest.raises(SubmissionValidationError, match="unknown item: candbench/c1"):
        _scored_items(items, _static_suite_items(), dynamic)


def test_scored_items_rejects_duplicated_carried_verdicts() -> None:
    items = [_dynamic_item("t1", correct=True), _dynamic_item("t1", correct=True)]

    with pytest.raises(SubmissionValidationError, match="duplicate item: dynbench/t1"):
        _scored_items(items, _static_suite_items(), frozenset({"dynbench"}))


def test_suite_without_scorecard_has_no_dynamic_benches(tmp_path: Path) -> None:
    # Older/dev suites (no SCORECARD.json) keep the strict pre-dynamic behavior.
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()

    assert _dynamic_benches(suite_dir, _static_suite_items()) == frozenset()


def test_bench_aggregates_carried_bench_uses_zero_baseline() -> None:
    items = [_dynamic_item("t1", correct=True), _dynamic_item("t2", correct=False)]
    scored = _scored_items(items, _static_suite_items(), frozenset({"dynbench"}))

    benches = _bench_aggregates(scored, _static_suite_items(), frozenset({"dynbench"}))

    agg = benches["dynbench"]
    assert agg["n"] == 2
    assert agg["raw_accuracy"] == 0.5
    # Zero baseline: no guess-rate correction on a verdict bench.
    assert agg["chance_corrected"] == 0.5
    assert agg["n_errors"] == 0


def test_dynamic_axis_status_requires_every_verdict_to_be_well_formed() -> None:
    items = [_dynamic_item("t1", correct=True), _dynamic_item("t2", correct=False)]
    items[1]["correct"] = None
    suite_axes = {"agentic": {"benches": ["dynbench"]}}
    status = axis_status_for_benches((), suite_axes)

    adjusted = _axis_status_from_dynamic_verdicts(
        status,
        items,
        frozenset({"dynbench"}),
        suite_axes,
    )

    assert adjusted["axes"]["agentic"]["status"] == "not_measured"
