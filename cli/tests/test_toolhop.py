from __future__ import annotations

import json
from pathlib import Path
from typing import Final, TypeAlias

import pytest

from localbench.scorers.toolhop import FailureKind, build_toolhop_prompt, score_toolhop
from localbench.scorers.toolhop._executor import execute_toolhop_trace

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]


def test_score_toolhop_when_gold_trace_matches_answer_is_deterministic() -> None:
    # Given a synthetic multi-hop ToolHop item and a known-correct call chain.
    item = _synthetic_item()
    response = json.dumps(
        [
            "lookup_birth_year(name='Ada Lovelace')",
            "sum_digits(number=1815)",
        ],
    )

    # When scoring the same response twice.
    first = score_toolhop(item, response)
    second = score_toolhop(item, response)

    # Then final-answer correctness and extracted trace details are deterministic.
    assert first == second
    assert first["correct"] is True
    assert first["failure_kind"] is None
    assert first["extracted"] is not None


def test_score_toolhop_when_trace_finishes_with_wrong_value_reports_wrong_final_answer() -> None:
    # Given a valid chain that calls the right tools but produces the wrong final value.
    item = _synthetic_item()
    response = json.dumps(
        [
            "lookup_birth_year(name='Ada Lovelace')",
            "sum_digits(number=1816)",
        ],
    )

    # When scoring the response.
    result = score_toolhop(item, response)

    # Then the failure is classified as a final-answer miss, not a tool failure.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.WRONG_FINAL_ANSWER


def test_score_toolhop_when_call_is_malformed_reports_taxonomy() -> None:
    # Given a JSON trace containing a syntactically invalid call.
    item = _synthetic_item()

    # When scoring the trace.
    result = score_toolhop(item, json.dumps(["lookup_birth_year(name='Ada'"]))

    # Then syntax failures are separated from wrong tools and wrong answers.
    assert result["correct"] is False
    assert result["extracted"] is None
    assert result["failure_kind"] == FailureKind.MALFORMED_CALL


def test_score_toolhop_when_call_uses_unknown_tool_reports_wrong_tool() -> None:
    # Given a trace that attempts an unadvertised tool.
    item = _synthetic_item()

    # When scoring the trace.
    result = score_toolhop(item, json.dumps(["open('owned.txt', 'w')"]))

    # Then the scorer rejects the tool before any filesystem effect can happen.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.WRONG_TOOL
    assert not (_REPO_ROOT / "owned.txt").exists()


def test_score_toolhop_when_signature_does_not_bind_reports_wrong_args() -> None:
    # Given a real advertised tool called with missing required arguments.
    item = _synthetic_item()

    # When scoring the trace.
    result = score_toolhop(item, json.dumps(["lookup_birth_year()"]))

    # Then argument binding is reported separately.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.WRONG_ARGS


def test_score_toolhop_when_tool_raises_reports_tool_exec_error() -> None:
    # Given an advertised vendored tool that raises during execution.
    item = _synthetic_item(extra_functions=[_EXPLODING_TOOL], extra_tool_names=["explode"])

    # When scoring the trace.
    result = score_toolhop(item, json.dumps(["explode()"]))

    # Then runtime tool failures are distinct from malformed model calls.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.TOOL_EXEC_ERROR


@pytest.mark.parametrize(
    ("tool_source", "tool_name"),
    [
        ("def evil_open():\n    return open('toolhop-owned.txt', 'w')\n", "evil_open"),
        ("def evil_socket():\n    import socket\n    return socket.socket()\n", "evil_socket"),
        ("def evil_subprocess():\n    import subprocess\n    return subprocess.run(['echo', 'x'])\n", "evil_subprocess"),
        ("def evil_system():\n    import os\n    return os.system('echo x')\n", "evil_system"),
        ("def evil_import():\n    import importlib\n    return importlib.import_module('os')\n", "evil_import"),
    ],
)
def test_score_toolhop_blocks_side_effecting_or_nonallowlisted_tools(
    tool_source: str,
    tool_name: str,
) -> None:
    # Given an item whose vendored tool attempts a forbidden operation.
    item = _synthetic_item(extra_functions=[tool_source], extra_tool_names=[tool_name])

    # When the model calls that tool.
    result = score_toolhop(item, json.dumps([f"{tool_name}()"]))

    # Then the confined runtime blocks it and leaves the filesystem unchanged.
    assert result["correct"] is False
    assert result["failure_kind"] == FailureKind.TOOL_EXEC_ERROR
    assert not (_REPO_ROOT / "toolhop-owned.txt").exists()


def test_execute_toolhop_trace_when_step_cap_is_exceeded_reports_timeout() -> None:
    # Given a valid trace whose call count exceeds the configured step cap.
    item = _synthetic_item()
    trace = [
        "lookup_birth_year(name='Ada Lovelace')",
        "sum_digits(number=1815)",
    ]

    # When executing with a one-step budget.
    result = execute_toolhop_trace(item=item, trace=trace, max_steps=1)

    # Then timeout is reported through the same failure taxonomy.
    assert result.failure_kind == FailureKind.TIMEOUT


def test_build_toolhop_prompt_when_given_item_exposes_tools_not_gold() -> None:
    # Given a ToolHop item that carries hidden gold calls for tests.
    item = _synthetic_item()
    item["gold_calls"] = ["lookup_birth_year(name='Ada Lovelace')"]

    # When rendering the prompt.
    prompt = build_toolhop_prompt(item)

    # Then the prompt describes the tool-call contract without leaking answers or traces.
    assert "Return only a JSON array" in prompt
    assert "lookup_birth_year" in prompt
    assert "gold_calls" not in prompt
    assert "15" not in prompt


def _synthetic_item(
    *,
    extra_functions: list[str] | None = None,
    extra_tool_names: list[str] | None = None,
) -> JsonObject:
    functions = [_LOOKUP_TOOL, _SUM_TOOL, *(extra_functions or [])]
    tool_names = ["lookup_birth_year", "sum_digits", *(extra_tool_names or [])]
    tools = {
        name: {
            "name": name,
            "description": f"Synthetic {name} tool.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
        for name in tool_names
    }
    return {
        "id": "toolhop-test-001",
        "source_id": 1,
        "question": "What is the sum of the digits in Ada Lovelace's birth year?",
        "answer": "15",
        "sub_task": {
            "When was Ada Lovelace born?": "1815",
            "What is the sum of the digits in 1815?": "15",
        },
        "tools": tools,
        "functions": functions,
        "domain": "History",
        "category": "history",
        "answer_type": "number",
        "previous_answer_type": "date",
        "hop_count": 2,
        "gold_calls": [],
    }


_LOOKUP_TOOL: Final = """
def lookup_birth_year(name: str) -> int:
    if name == 'Ada Lovelace':
        return 1815
    raise ValueError('unknown person')
"""

_SUM_TOOL: Final = """
def sum_digits(number: int) -> int:
    return sum(int(char) for char in str(number))
"""

_EXPLODING_TOOL: Final = """
def explode() -> str:
    raise RuntimeError('boom')
"""
