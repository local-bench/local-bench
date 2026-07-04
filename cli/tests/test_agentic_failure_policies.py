from __future__ import annotations

from localbench.scoring.agentic_exec.adapter import AppWorldLiteAdapter
from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.runner import ScriptedAgentRunner, ScriptedPlan
from localbench.scoring.agentic_exec.stub_appworld import build_stub_appworld
from localbench.scoring.agentic_exec.types import FailureReason, FinalAnswerAction, ToolCallAction


def test_runner_hard_fails_when_max_turns_are_exceeded() -> None:
    # Given a plan needing two turns but a one-turn cap.
    config = AgenticExecConfig(max_turns=1)
    runner = ScriptedAgentRunner(AppWorldLiteAdapter(build_stub_appworld(), config), config)
    plan = ScriptedPlan(
        task_id="stub_read_order_total",
        actions=(
            ToolCallAction(tool="orders.get_order", arguments={"order_id": "o-100"}),
            FinalAnswerAction(answer={"order_id": "o-100", "total": 12.3457}),
        ),
    )

    # When running the plan.
    log = runner.run_task(plan)

    # Then the task hard-fails with a cap-hit diagnostic.
    assert log.success is False
    assert log.failure_reason is FailureReason.MAX_TURNS_EXCEEDED
    assert log.cap_hit is True


def test_runner_hard_fails_when_max_tool_calls_are_exceeded() -> None:
    # Given a zero-tool-call cap.
    config = AgenticExecConfig(max_tool_calls=0)
    runner = ScriptedAgentRunner(AppWorldLiteAdapter(build_stub_appworld(), config), config)
    plan = ScriptedPlan(
        task_id="stub_read_order_total",
        actions=(ToolCallAction(tool="orders.get_order", arguments={"order_id": "o-100"}),),
    )

    # When running the first tool call.
    log = runner.run_task(plan)

    # Then the task hard-fails before dispatch.
    assert log.success is False
    assert log.failure_reason is FailureReason.MAX_TOOL_CALLS_EXCEEDED
    assert log.cap_hit is True
    assert log.api_calls_by_type == {}


def test_runner_loop_guard_fails_repeated_invalid_call_and_args() -> None:
    # Given a plan that repeats the same forbidden call twice.
    config = AgenticExecConfig()
    runner = ScriptedAgentRunner(AppWorldLiteAdapter(build_stub_appworld(), config), config)
    repeated = ToolCallAction(tool="supervisor.complete_task", arguments={})
    plan = ScriptedPlan(task_id="stub_read_order_total", actions=(repeated, repeated))

    # When running the plan.
    log = runner.run_task(plan)

    # Then the loop guard hard-fails on the repeated invalid signature.
    assert log.success is False
    assert log.failure_reason is FailureReason.LOOP_GUARD
    assert log.api_calls_by_type == {}


def test_runner_reports_verifier_failure_for_wrong_final_answer() -> None:
    # Given a read task with an incorrect final answer.
    config = AgenticExecConfig()
    runner = ScriptedAgentRunner(AppWorldLiteAdapter(build_stub_appworld(), config), config)
    plan = ScriptedPlan(
        task_id="stub_read_order_total",
        actions=(FinalAnswerAction(answer={"order_id": "o-100", "total": 99.0}),),
    )

    # When running the plan.
    log = runner.run_task(plan)

    # Then the deterministic verifier failure is explicit.
    assert log.success is False
    assert log.failure_reason is FailureReason.VERIFIER_FAILED
