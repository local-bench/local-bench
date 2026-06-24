from __future__ import annotations

import pytest

from localbench.scoring.agentic_exec.score import TaskScoreInput, score_agentic_runs, wilson_95_ci


def test_score_computes_agentic_success_rate_and_wilson_ci() -> None:
    # Given three task records with two verifier passes.
    records = (
        _record("read", "read_lookup_exact_answer", "appworld_level_1", success=True),
        _record("refund", "single_app_state_mutation", "appworld_level_1", success=False),
        _record("cross", "cross_app_workflow", "appworld_level_2", success=True),
    )

    # When scoring agentic runs.
    score = score_agentic_runs(records)

    # Then ASR is tasks_passed / tasks_total with Wilson 95% interval.
    assert score.tasks_passed == 2
    assert score.tasks_total == 3
    assert score.agentic_success_rate == pytest.approx(2 / 3)
    assert score.wilson_ci.point == pytest.approx(2 / 3)
    assert score.wilson_ci.lo == pytest.approx(0.20765, abs=1e-5)
    assert score.wilson_ci.hi == pytest.approx(0.93851, abs=1e-5)


def test_score_reports_family_and_band_subscores() -> None:
    # Given records spanning families and bands.
    records = (
        _record("read", "read_lookup_exact_answer", "appworld_level_1", success=True),
        _record("refund", "single_app_state_mutation", "appworld_level_1", success=False),
        _record("cross", "cross_app_workflow", "appworld_level_2", success=True),
    )

    # When scoring.
    score = score_agentic_runs(records)

    # Then family and band breakdowns use the same ASR semantics.
    assert score.family_scores["read_lookup_exact_answer"].point == 1.0
    assert score.family_scores["single_app_state_mutation"].point == 0.0
    assert score.family_scores["cross_app_workflow"].point == 1.0
    assert score.band_scores["appworld_level_1"].point == 0.5
    assert score.band_scores["appworld_level_2"].point == 1.0


def test_score_reports_required_diagnostics() -> None:
    # Given records with parser failures, cap hits, collateral damage, and tool recovery.
    records = (
        _record(
            "a",
            "read_lookup_exact_answer",
            "appworld_level_1",
            success=True,
            invalid_json_count=1,
            total_assistant_turns=4,
            tool_turns=2,
            generated_tokens=100,
            had_tool_error=True,
            recovered_after_tool_error=True,
        ),
        _record(
            "b",
            "single_app_state_mutation",
            "appworld_level_1",
            success=False,
            schema_error_count=2,
            total_assistant_turns=5,
            tool_turns=3,
            generated_tokens=200,
            max_tool_calls_hit=True,
            collateral_damage=True,
            had_tool_error=True,
            recovered_after_tool_error=False,
        ),
        _record(
            "c",
            "cross_app_workflow",
            "appworld_level_2",
            success=True,
            total_assistant_turns=3,
            tool_turns=1,
            generated_tokens=300,
        ),
    )

    # When scoring diagnostics.
    diagnostics = score_agentic_runs(records).diagnostics

    # Then every required diagnostic is computed deterministically.
    assert diagnostics.invalid_json_rate == pytest.approx(1 / 12)
    assert diagnostics.schema_error_rate == pytest.approx(2 / 12)
    assert diagnostics.avg_tool_turns == pytest.approx(2.0)
    assert diagnostics.avg_generated_tokens == pytest.approx(200.0)
    assert diagnostics.cap_hit_rate == pytest.approx(1 / 3)
    assert diagnostics.collateral_damage_rate == pytest.approx(1 / 3)
    assert diagnostics.recovery_after_tool_error_rate == pytest.approx(1 / 2)


def test_wilson_interval_handles_empty_task_set() -> None:
    # Given no scored tasks.
    interval = wilson_95_ci(successes=0, total=0)

    # Then the interval is deterministic and non-crashing.
    assert interval.point == 0.0
    assert interval.lo == 0.0
    assert interval.hi == 0.0


def _record(
    task_id: str,
    family: str,
    band: str,
    *,
    success: bool,
    invalid_json_count: int = 0,
    schema_error_count: int = 0,
    total_assistant_turns: int = 1,
    tool_turns: int = 0,
    generated_tokens: int = 0,
    max_tool_calls_hit: bool = False,
    collateral_damage: bool = False,
    had_tool_error: bool = False,
    recovered_after_tool_error: bool = False,
) -> TaskScoreInput:
    return TaskScoreInput(
        task_id=task_id,
        family=family,
        band=band,
        success=success,
        invalid_json_count=invalid_json_count,
        schema_error_count=schema_error_count,
        total_assistant_turns=total_assistant_turns,
        tool_turns=tool_turns,
        generated_tokens=generated_tokens,
        max_tool_calls_hit=max_tool_calls_hit,
        collateral_damage=collateral_damage,
        had_tool_error=had_tool_error,
        recovered_after_tool_error=recovered_after_tool_error,
    )
