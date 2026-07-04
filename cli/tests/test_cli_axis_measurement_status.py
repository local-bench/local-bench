from __future__ import annotations

import pytest

from localbench._scoring import ScoredItem
from localbench._suite import RenderedBench
from localbench._types import JsonValue
from localbench.cli import _append_scorer_gated_benches
from localbench.orchestrate import LocalbenchRun
from localbench.scoring.axis_status import axis_status_for_benches, mark_axis_not_measured


def test_scorer_unavailable_gate_marks_axis_not_measured_without_failed_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a run record with suite-axis mapping, measured benches, and one
    # scorer-gated bench.
    monkeypatch.setattr(
        "localbench._scoring.DOMAIN_WEIGHTS",
        {
            "Knowledge": 0.90,
            "Instruction-Following": 0.000000000001,
        },
    )
    suite_axes = {"suite_knowledge": {"benches": ["mmlu_pro"]}}
    record = _record_with_benches(("mmlu_pro", "ifbench"), suite_axes)
    mark_axis_not_measured(record["axis_status"], "knowledge", reason="not_run")

    # When the scorer gate is appended to the record.
    _append_scorer_gated_benches(
        record,
        {
            "bfcl_multi_turn": (
                _rendered_bfcl_multi_turn(),
                "Scorer unavailable for bfcl_multi_turn: missing evaluator",
                "agentic",
            ),
        },
        suite_axes,
    )

    # Then the axis is not measured, and no fake failed item or zero aggregate is emitted.
    assert record["axis_status"]["axes"]["agentic"] == {
        "axis": "agentic",
        "status": "not_measured",
        "reason": "scorer_unavailable",
        "detail": "Scorer unavailable for bfcl_multi_turn: missing evaluator",
    }
    assert "bfcl_multi_turn" not in record["benches"]
    assert [item["bench"] for item in record["items"]] == ["mmlu_pro", "ifbench"]
    assert record["totals"]["n_items"] == 2
    assert record["scores"]["partial_composite"] == pytest.approx(0.90)
    assert record["warnings"] == ["Scorer unavailable for bfcl_multi_turn: missing evaluator"]


def _scored_item(bench: str) -> ScoredItem:
    return {
        "id": "item-1",
        "bench": bench,
        "response_text": "A",
        "extracted": "A",
        "correct": True,
        "finish_reason": "stop",
        "latency_seconds": 0.0,
        "started_at": "2026-06-26T00:00:00+00:00",
        "finished_at": "2026-06-26T00:00:01+00:00",
        "attempts": 1,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "error": None,
    }


def _record_with_benches(
    benches: tuple[str, ...],
    suite_axes: dict[str, JsonValue],
) -> LocalbenchRun:
    return {
        "schema": "localbench-run-v0",
        "schema_version": "localbench.run.v1",
        "submission_ticket_id": None,
        "server_nonce": None,
        "issued_at": None,
        "run_started_at": "2026-06-26T00:00:00+00:00",
        "run_finished_at": "2026-06-26T00:00:01+00:00",
        "source": "localbench-cli",
        "tier": "standard",
        "account": None,
        "model": {},
        "manifest": {},
        "axis_status": axis_status_for_benches(benches, suite_axes),
        "headline_complete": False,
        "benches": {
            "mmlu_pro": {
                "n": 1,
                "n_errors": 0,
                "n_extraction_failures": 0,
                "raw_accuracy": 0.90,
                "chance_corrected": 0.90,
                "termination_rate": 1.0,
                "conditional_accuracy": 0.90,
            },
            "ifbench": {
                "n": 1,
                "n_errors": 0,
                "n_extraction_failures": 0,
                "raw_accuracy": 0.10,
                "chance_corrected": 0.10,
                "termination_rate": 1.0,
                "conditional_accuracy": 0.10,
            },
        },
        "composite": 0.10,
        "conformance": {},
        "items": [_scored_item("mmlu_pro"), _scored_item("ifbench")],
        "totals": {
            "n_items": 2,
            "n_errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "wall_time_seconds": 1.0,
            "completion_tokens_per_second": 0.0,
        },
        "warnings": [],
        "output_path": "unused.json",
    }


def _rendered_bfcl_multi_turn() -> RenderedBench:
    return RenderedBench(
        name="bfcl_multi_turn",
        source_items=[],
        benchmark_items=[
            {
                "id": "turn-1",
                "messages": [{"role": "user", "content": "act"}],
                "sampling_params": {},
            },
        ],
        baseline=0.0,
        decoding={},
        item_file="bfcl_multi_turn.jsonl",
    )
