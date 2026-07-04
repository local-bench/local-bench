from __future__ import annotations

import pytest

from localbench._types import JsonValue
from localbench.scoring.agentic_exec.protocol import parse_assistant_action
from localbench.scoring.agentic_exec.types import ActionSchemaError


def test_protocol_parses_tool_call_schema() -> None:
    # Given a decoded JSON object matching the tool-call protocol.
    payload = {
        "type": "tool_call",
        "tool": "crm.get_user",
        "arguments": {"user_id": "u-1"},
    }

    # When validating the protocol schema.
    action = parse_assistant_action(payload)

    # Then a typed tool-call action is returned.
    assert action.type == "tool_call"
    assert action.tool == "crm.get_user"
    assert action.arguments == {"user_id": "u-1"}


def test_protocol_parses_final_answer_schema() -> None:
    # Given a decoded final-answer object.
    payload = {"type": "final_answer", "answer": "refund issued"}

    # When validating the protocol schema.
    action = parse_assistant_action(payload)

    # Then a typed final-answer action is returned.
    assert action.type == "final_answer"
    assert action.answer == "refund issued"


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "tool_call", "tool": "crm.get_user"},
        {"type": "tool_call", "tool": 10, "arguments": {}},
        {"type": "tool_call", "tool": "crm.get_user", "arguments": []},
        {"type": "final_answer"},
        {"type": "unknown", "answer": "x"},
    ],
)
def test_protocol_rejects_schema_errors(payload: JsonValue) -> None:
    # Given a decoded JSON object that violates the assistant action protocol.
    # When validating the schema, then the typed schema error names the problem.
    with pytest.raises(ActionSchemaError) as exc_info:
        parse_assistant_action(payload)

    assert exc_info.value.message
