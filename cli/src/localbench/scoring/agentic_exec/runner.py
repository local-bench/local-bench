"""Deterministic non-LLM runner for AppWorld-lite smoke tasks."""

from __future__ import annotations

import time
from dataclasses import dataclass

from localbench.scoring.agentic_exec.adapter import AppWorldLiteAdapter
from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.observations import normalize_json
from localbench.scoring.agentic_exec.types import (
    AssistantAction,
    FailureReason,
    FinalAnswerAction,
    ToolCallAction,
)


@dataclass(frozen=True, slots=True)
class ScriptedPlan:
    """Hardcoded action sequence for one deterministic smoke task."""

    task_id: str
    actions: tuple[AssistantAction, ...]


@dataclass(frozen=True, slots=True)
class ScriptedTaskLog:
    """Per-task execution log required by the build-time validation."""

    task_id: str
    steps_taken: int
    api_calls_by_type: dict[str, int]
    success: bool
    wall_time_ms: float
    failure_reason: FailureReason | None = None
    cap_hit: bool = False


class ScriptedAgentRunner:
    """Run deterministic plans through the real harness path without an LLM."""

    def __init__(self, adapter: AppWorldLiteAdapter, config: AgenticExecConfig) -> None:
        self._adapter = adapter
        self._config = config

    def run_tasks(self, plans: tuple[ScriptedPlan, ...]) -> list[ScriptedTaskLog]:
        """Run scripted plans in deterministic order."""
        return [self.run_task(plan) for plan in plans]

    def run_task(self, plan: ScriptedPlan) -> ScriptedTaskLog:
        """Run one plan and record API-call metrics."""
        task = self._adapter.load_task(plan.task_id)
        start = time.perf_counter()
        api_calls_by_type: dict[str, int] = {}
        invalid_signatures: set[str] = set()
        steps_taken = 0
        tool_calls = 0

        for action in plan.actions:
            if steps_taken >= self._config.max_turns:
                return self._failure_log(
                    plan.task_id,
                    steps_taken,
                    api_calls_by_type,
                    start,
                    FailureReason.MAX_TURNS_EXCEEDED,
                    cap_hit=True,
                )
            steps_taken += 1
            match action:  # noqa: MATCH_OK - no-op fallback is unreachable by type.
                case ToolCallAction():
                    if tool_calls >= self._config.max_tool_calls:
                        return self._failure_log(
                            plan.task_id,
                            steps_taken,
                            api_calls_by_type,
                            start,
                            FailureReason.MAX_TOOL_CALLS_EXCEEDED,
                            cap_hit=True,
                        )
                    tool_calls += 1
                    result = self._adapter.execute_tool_call(task, action)
                    if result.failure_reason is None:
                        api_calls_by_type[action.tool] = api_calls_by_type.get(action.tool, 0) + 1
                        continue
                    signature = _action_signature(action)
                    if signature in invalid_signatures:
                        return self._failure_log(
                            plan.task_id,
                            steps_taken,
                            api_calls_by_type,
                            start,
                            FailureReason.LOOP_GUARD,
                        )
                    invalid_signatures.add(signature)
                case FinalAnswerAction():
                    completion = self._adapter.final_answer(task, action)
                    if completion.success:
                        return ScriptedTaskLog(
                            task_id=plan.task_id,
                            steps_taken=steps_taken,
                            api_calls_by_type=api_calls_by_type,
                            success=True,
                            wall_time_ms=_elapsed_ms(start),
                        )
                    reason = (
                        FailureReason.COLLATERAL_DAMAGE
                        if completion.eval_result.collateral_damage
                        else FailureReason.VERIFIER_FAILED
                    )
                    return self._failure_log(
                        plan.task_id,
                        steps_taken,
                        api_calls_by_type,
                        start,
                        reason,
                    )
        return self._failure_log(
            plan.task_id,
            steps_taken,
            api_calls_by_type,
            start,
            FailureReason.MAX_TURNS_EXCEEDED,
        )

    def _failure_log(
        self,
        task_id: str,
        steps_taken: int,
        api_calls_by_type: dict[str, int],
        start: float,
        reason: FailureReason,
        *,
        cap_hit: bool = False,
    ) -> ScriptedTaskLog:
        return ScriptedTaskLog(
            task_id=task_id,
            steps_taken=steps_taken,
            api_calls_by_type=api_calls_by_type,
            success=False,
            wall_time_ms=_elapsed_ms(start),
            failure_reason=reason,
            cap_hit=cap_hit,
        )


def default_scripted_plans() -> tuple[ScriptedPlan, ...]:
    """Return deterministic gold paths for the hermetic stub tasks."""
    # SEAM: real AppWorld scripted gold paths wire in here for build-time calibration.
    return (
        ScriptedPlan(
            task_id="stub_read_order_total",
            actions=(
                ToolCallAction(tool="orders.get_order", arguments={"order_id": "o-100"}),
                FinalAnswerAction(answer={"order_id": "o-100", "total": 12.3457}),
            ),
        ),
        ScriptedPlan(
            task_id="stub_refund_paid_order",
            actions=(
                ToolCallAction(tool="orders.get_order", arguments={"order_id": "o-100"}),
                ToolCallAction(
                    tool="orders.refund_order",
                    arguments={"order_id": "o-100", "reason": "duplicate"},
                ),
                FinalAnswerAction(answer="refund complete"),
            ),
        ),
        ScriptedPlan(
            task_id="stub_schedule_vip_followup",
            actions=(
                ToolCallAction(tool="crm.get_user", arguments={"user_id": "u-2"}),
                ToolCallAction(
                    tool="calendar.create_event",
                    arguments={"user_id": "u-2", "title": "VIP follow-up", "day": "2026-06-24"},
                ),
                ToolCallAction(
                    tool="mail.send_email",
                    arguments={
                        "user_id": "u-2",
                        "subject": "VIP follow-up scheduled",
                        "body": "Your follow-up is scheduled for 2026-06-24.",
                    },
                ),
                FinalAnswerAction(answer="vip follow-up scheduled"),
            ),
        ),
    )


def api_call_count_distribution(logs: list[ScriptedTaskLog]) -> dict[int, int]:
    """Count tasks by total whitelisted API calls used."""
    distribution: dict[int, int] = {}
    for log in logs:
        total_calls = sum(log.api_calls_by_type.values())
        distribution[total_calls] = distribution.get(total_calls, 0) + 1
    return dict(sorted(distribution.items()))


def _action_signature(action: ToolCallAction) -> str:
    normalized_args = normalize_json(action.arguments)
    return f"{action.tool}:{normalized_args!r}"


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0
