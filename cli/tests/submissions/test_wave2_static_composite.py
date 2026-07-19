from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from localbench._scoring import BenchAggregate
from localbench.scoring.axis_status import axis_status_for_benches, mark_axis_not_measured
from localbench.submissions.foundation_scores import axis_projection, score_summary


def test_score_summary_emits_static_and_full_composites_with_strict_presence() -> None:
    benches = {
        "mmlu_pro": _aggregate(1.0),
        "ifbench": _aggregate(0.0),
        "tc_json_v1": _aggregate(0.5),
        "bigcodebench_hard": _aggregate(0.25),
        "olymmath_hard": _aggregate(0.75),
    }
    status = axis_status_for_benches(benches)

    summary = score_summary(benches, status)

    assert summary["partial_composite"] == 0.45
    assert summary["composite_static"] == 0.45
    assert summary["static_index_version"] == "static-suite-v3"
    assert summary["composite_full"] is None


def test_score_summary_static_composite_is_none_when_static_axis_is_missing() -> None:
    benches = {
        "mmlu_pro": _aggregate(1.0),
        "ifbench": _aggregate(0.0),
        "tc_json_v1": _aggregate(0.5),
    }
    status = axis_status_for_benches(benches)
    mark_axis_not_measured(status, "coding", reason="not_run")

    summary = score_summary(benches, status)

    assert summary["composite_static"] is None
    assert "static_index_version" not in summary
    assert summary["composite_full"] is None


def test_score_summary_full_composite_requires_every_tool_use_facet() -> None:
    benches = {
        "mmlu_pro": _aggregate(1.0),
        "ifbench": _aggregate(0.0),
        "tc_json_v1": _aggregate(0.5),
        "bigcodebench_hard": _aggregate(0.25),
        "olymmath_hard": _aggregate(0.75),
        "appworld_c": _aggregate(0.75),
        "bfcl_multi_turn_base": _aggregate(0.25),
    }
    status = axis_status_for_benches(benches)

    summary = score_summary(benches, status)

    assert summary["composite_full"] == pytest.approx(summary["partial_composite"])
    assert summary["composite_static"] == 0.45


def test_full_exec_six_axis_uses_current_index_with_agentic_counted() -> None:
    benches = {
        "mmlu_pro": _aggregate(1.0),
        "ifbench": _aggregate(0.0),
        "tc_json_v1": _aggregate(0.5),
        "bigcodebench_hard": _aggregate(0.25),
        "olymmath_hard": _aggregate(0.75),
        "amo": _aggregate(0.75),
        "appworld_c": _aggregate(0.75),
    }
    suite_axes = {
        "knowledge": {"benches": ["mmlu_pro"]},
        "instruction_following": {"benches": ["ifbench"]},
        "math": {"benches": ["olymmath_hard", "amo"]},
        "agentic": {"benches": ["appworld_c"]},
        "tool_calling": {"benches": ["tc_json_v1"]},
        "coding": {"benches": ["bigcodebench_hard"]},
    }
    status = axis_status_for_benches(benches, suite_axes)

    summary = score_summary(benches, status, suite_axes=suite_axes)
    axes = axis_projection(benches, status)

    assert summary["headline_score"] == pytest.approx(0.525)
    assert summary["composite_full"] == pytest.approx(0.525)
    assert summary["measured_headline_weight"] == 1.0
    assert axes["tool_use"]["score"] == pytest.approx(0.75)
    assert axes["call_formatting"]["score"] == pytest.approx(0.5)


def test_frozen_board_v1_blob_hash_is_unchanged() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        ["git", "hash-object", "cli/runs/board/board_v1.json"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "3d058e6074bd781cc488c03255904b5f9599e37e"


def _aggregate(chance_corrected: float) -> BenchAggregate:
    return {
        "n": 1,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": chance_corrected,
        "chance_corrected": chance_corrected,
        "termination_rate": 1.0,
        "conditional_accuracy": chance_corrected,
    }
