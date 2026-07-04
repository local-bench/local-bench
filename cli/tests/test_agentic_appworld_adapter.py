from __future__ import annotations

from localbench.scoring.agentic_exec.adapter import AppWorldLiteAdapter
from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.observations import canonical_observation
from localbench.scoring.agentic_exec.stub_appworld import build_stub_appworld
from localbench.scoring.agentic_exec.types import FailureReason, FinalAnswerAction, ToolCallAction


def test_stub_fixture_exposes_three_dev_tasks() -> None:
    # Given the hermetic AppWorld-lite stub fixture.
    world = build_stub_appworld()

    # When listing available development tasks.
    task_ids = set(world.task_ids())

    # Then it covers lookup, mutation, and cross-app workflow families.
    assert task_ids == {
        "stub_read_order_total",
        "stub_refund_paid_order",
        "stub_schedule_vip_followup",
    }


def test_adapter_loads_task_from_stub_fixture() -> None:
    # Given the adapter backed by the stub fixture.
    adapter = AppWorldLiteAdapter(build_stub_appworld(), AgenticExecConfig())

    # When loading a task.
    task = adapter.load_task("stub_refund_paid_order")

    # Then task metadata and whitelist are exposed deterministically.
    assert task.task_id == "stub_refund_paid_order"
    assert task.family == "single_app_state_mutation"
    assert task.band == "appworld_level_1"
    assert task.allowed_tools == ("orders.get_order", "orders.refund_order")


def test_adapter_executes_only_whitelisted_apis() -> None:
    # Given a loaded task whose whitelist excludes supervisor APIs.
    world = build_stub_appworld()
    adapter = AppWorldLiteAdapter(world, AgenticExecConfig())
    task = adapter.load_task("stub_read_order_total")

    # When a forbidden tool is requested.
    result = adapter.execute_tool_call(
        task,
        ToolCallAction(tool="supervisor.complete_task", arguments={}),
    )

    # Then dispatch is blocked before the stub world sees an API call.
    assert result.failure_reason is FailureReason.FORBIDDEN_TOOL
    assert result.observation.text == '{"error":"forbidden_tool","tool":"supervisor.complete_task"}'
    assert world.api_call_log == []


def test_adapter_returns_canonical_observation_for_whitelisted_api() -> None:
    # Given a task and a whitelisted API call returning unsorted floats.
    adapter = AppWorldLiteAdapter(build_stub_appworld(), AgenticExecConfig())
    task = adapter.load_task("stub_read_order_total")

    # When executing the tool call.
    result = adapter.execute_tool_call(
        task,
        ToolCallAction(tool="orders.get_order", arguments={"order_id": "o-100"}),
    )

    # Then keys are sorted and floats are rounded to six significant figures.
    assert result.failure_reason is None
    assert result.observation.text == '{"order":{"customer_id":"u-1","id":"o-100","refunded":false,"status":"paid","total":12.3457}}'
    assert result.observation.truncated is False


def test_canonical_observation_truncates_deterministically_at_configured_limit() -> None:
    # Given a long observation and a small limit.
    value = {"b": "x" * 80, "a": 1.23456789}

    # When canonicalizing twice.
    first = canonical_observation(value, char_limit=24)
    second = canonical_observation(value, char_limit=24)

    # Then truncation is stable, sorted, and exactly capped.
    assert first == second
    assert first.truncated is True
    assert len(first.text) == 24
    assert first.text == '{"a":1.23457,"b":"xxxxxx'


def test_adapter_final_answer_returns_completion_and_eval_result() -> None:
    # Given a mutation task after its required API call.
    adapter = AppWorldLiteAdapter(build_stub_appworld(), AgenticExecConfig())
    task = adapter.load_task("stub_refund_paid_order")
    adapter.execute_tool_call(
        task,
        ToolCallAction(
            tool="orders.refund_order",
            arguments={"order_id": "o-100", "reason": "duplicate"},
        ),
    )

    # When the assistant emits final_answer.
    completion = adapter.final_answer(task, FinalAnswerAction(answer="refund complete"))

    # Then the stub verifier produces a completion record and deterministic eval result.
    assert completion.task_id == "stub_refund_paid_order"
    assert completion.answer == "refund complete"
    assert completion.success is True
    assert completion.eval_result.passed is True
    assert completion.eval_result.collateral_damage is False
