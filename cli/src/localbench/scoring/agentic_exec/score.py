"""Agentic execution scoring metrics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskScoreInput:
    """One task-level record consumed by the scorer."""

    task_id: str
    family: str
    band: str
    success: bool
    invalid_json_count: int = 0
    schema_error_count: int = 0
    total_assistant_turns: int = 1
    tool_turns: int = 0
    generated_tokens: int = 0
    max_tool_calls_hit: bool = False
    collateral_damage: bool = False
    had_tool_error: bool = False
    recovered_after_tool_error: bool = False


@dataclass(frozen=True, slots=True)
class RateInterval:
    """Point estimate plus Wilson 95% interval."""

    point: float
    lo: float
    hi: float


@dataclass(frozen=True, slots=True)
class AgenticDiagnostics:
    """Non-composited diagnostics displayed beside ASR."""

    invalid_json_rate: float
    schema_error_rate: float
    avg_tool_turns: float
    avg_generated_tokens: float
    cap_hit_rate: float
    collateral_damage_rate: float
    recovery_after_tool_error_rate: float


@dataclass(frozen=True, slots=True)
class AgenticScore:
    """Complete score output for the candidate axis."""

    tasks_passed: int
    tasks_total: int
    agentic_success_rate: float
    wilson_ci: RateInterval
    family_scores: dict[str, RateInterval]
    band_scores: dict[str, RateInterval]
    diagnostics: AgenticDiagnostics


def score_agentic_runs(records: Sequence[TaskScoreInput]) -> AgenticScore:
    """Compute ASR, Wilson CI, subscores, and diagnostics."""
    tasks_total = len(records)
    tasks_passed = sum(1 for record in records if record.success)
    interval = wilson_95_ci(successes=tasks_passed, total=tasks_total)
    return AgenticScore(
        tasks_passed=tasks_passed,
        tasks_total=tasks_total,
        agentic_success_rate=interval.point,
        wilson_ci=interval,
        family_scores=_subscores(records, key="family"),
        band_scores=_subscores(records, key="band"),
        diagnostics=_diagnostics(records),
    )


def wilson_95_ci(*, successes: int, total: int) -> RateInterval:
    """Compute a Wilson score interval with the standard 95% z value."""
    if total == 0:
        return RateInterval(point=0.0, lo=0.0, hi=0.0)
    z = 1.959963984540054
    phat = successes / total
    z2 = z * z
    denominator = 1 + (z2 / total)
    center = (phat + (z2 / (2 * total))) / denominator
    margin = (z / denominator) * math.sqrt((phat * (1 - phat) / total) + (z2 / (4 * total * total)))
    return RateInterval(
        point=phat,
        lo=max(0.0, center - margin),
        hi=min(1.0, center + margin),
    )


def _subscores(records: Sequence[TaskScoreInput], *, key: str) -> dict[str, RateInterval]:
    grouped: dict[str, list[TaskScoreInput]] = {}
    for record in records:
        match key:  # noqa: MATCH_OK - private helper accepts two known strings.
            case "family":
                group = record.family
            case "band":
                group = record.band
            case _:
                group = ""
        grouped.setdefault(group, []).append(record)
    return {
        group: wilson_95_ci(
            successes=sum(1 for record in group_records if record.success),
            total=len(group_records),
        )
        for group, group_records in sorted(grouped.items())
    }


def _diagnostics(records: Sequence[TaskScoreInput]) -> AgenticDiagnostics:
    task_count = len(records)
    total_turns = sum(record.total_assistant_turns for record in records)
    tool_error_tasks = sum(1 for record in records if record.had_tool_error)
    return AgenticDiagnostics(
        invalid_json_rate=_rate(
            sum(record.invalid_json_count for record in records),
            total_turns,
        ),
        schema_error_rate=_rate(
            sum(record.schema_error_count for record in records),
            total_turns,
        ),
        avg_tool_turns=_rate(sum(record.tool_turns for record in records), task_count),
        avg_generated_tokens=_rate(sum(record.generated_tokens for record in records), task_count),
        cap_hit_rate=_rate(
            sum(1 for record in records if record.max_tool_calls_hit),
            task_count,
        ),
        collateral_damage_rate=_rate(
            sum(1 for record in records if record.collateral_damage),
            task_count,
        ),
        recovery_after_tool_error_rate=_rate(
            sum(1 for record in records if record.recovered_after_tool_error),
            tool_error_tasks,
        ),
    )


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
