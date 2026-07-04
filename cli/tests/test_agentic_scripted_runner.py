from __future__ import annotations

from localbench.scoring.agentic_exec.adapter import AppWorldLiteAdapter
from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.runner import (
    ScriptedAgentRunner,
    api_call_count_distribution,
    default_scripted_plans,
)
from localbench.scoring.agentic_exec.stub_appworld import build_stub_appworld


def test_scripted_runner_solves_all_stub_dev_tasks() -> None:
    # Given deterministic non-LLM plans for the stub task set.
    config = AgenticExecConfig()
    adapter = AppWorldLiteAdapter(build_stub_appworld(), config)
    runner = ScriptedAgentRunner(adapter, config)

    # When running the scripted suite.
    logs = runner.run_tasks(default_scripted_plans())

    # Then every task succeeds through the adapter and verifier path.
    assert [log.task_id for log in logs] == [
        "stub_read_order_total",
        "stub_refund_paid_order",
        "stub_schedule_vip_followup",
    ]
    assert [log.success for log in logs] == [True, True, True]
    assert [log.steps_taken for log in logs] == [2, 3, 4]
    assert [log.api_calls_by_type for log in logs] == [
        {"orders.get_order": 1},
        {"orders.get_order": 1, "orders.refund_order": 1},
        {"crm.get_user": 1, "calendar.create_event": 1, "mail.send_email": 1},
    ]
    assert all(log.wall_time_ms >= 0.0 for log in logs)


def test_scripted_runner_reports_api_call_count_distribution() -> None:
    # Given successful scripted runner logs.
    config = AgenticExecConfig()
    adapter = AppWorldLiteAdapter(build_stub_appworld(), config)
    runner = ScriptedAgentRunner(adapter, config)
    logs = runner.run_tasks(default_scripted_plans())

    # When aggregating API-call counts per task.
    distribution = api_call_count_distribution(logs)

    # Then the distribution exposes the measured feasibility envelope.
    assert distribution == {1: 1, 2: 1, 3: 1}
