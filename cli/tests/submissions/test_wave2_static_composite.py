from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from localbench._scoring import BenchAggregate
from localbench.scoring.axis_status import axis_status_for_benches, mark_axis_not_measured
from localbench.submissions.foundation_scores import score_summary


def test_score_summary_emits_static_and_full_composites_with_strict_presence() -> None:
    benches = {
        "mmlu_pro": _aggregate(1.0),
        "ifbench": _aggregate(0.0),
        "tc_json_v1": _aggregate(0.5),
        "lcb": _aggregate(0.25),
    }
    status = axis_status_for_benches(benches)

    summary = score_summary(benches, status)

    assert summary["partial_composite"] == 0.45
    assert summary["composite_static"] == 0.45
    assert summary["static_index_version"] == "static-suite-v1"
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


def test_score_summary_full_composite_requires_agentic_axis() -> None:
    benches = {
        "mmlu_pro": _aggregate(1.0),
        "ifbench": _aggregate(0.0),
        "tc_json_v1": _aggregate(0.5),
        "lcb": _aggregate(0.25),
        "appworld_c": _aggregate(0.75),
    }
    status = axis_status_for_benches(benches)

    summary = score_summary(benches, status)

    assert summary["composite_full"] == pytest.approx(summary["partial_composite"])
    assert summary["composite_static"] == 0.45


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
