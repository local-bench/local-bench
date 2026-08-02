from __future__ import annotations

import json

from localbench.check.grading import grade_response, sandbox_command
from localbench.coding_exec.sandbox import MANDATORY_SECURITY_FLAGS


def test_grade_response_routes_v1_knowledge_instruction_and_math_scorers() -> None:
    knowledge = grade_response(
        "knowledge",
        {"answer_index": 1, "choices": ["one", "two", "three", "four"]},
        {"text": "Final answer: B", "finish_reason": "stop"},
    )
    instruction = grade_response(
        "instruction",
        {
            "prompt": "Return text without whitespace.",
            "instruction_id_list": ["format:no_whitespace"],
            "kwargs": [{}],
        },
        {"text": "NoSpaces", "finish_reason": "stop"},
    )
    math = grade_response(
        "math",
        {"answer": "2"},
        {"text": r"\boxed{2}", "finish_reason": "stop"},
    )

    assert knowledge["correct"] is True
    assert knowledge["chance_corrected"] == 1.0
    assert instruction["correct"] is True
    assert math["correct"] is True


def test_grade_response_routes_tc_json_and_stateful_scorers() -> None:
    call = {"name": "weather.get", "arguments": {"location": "Brisbane"}}
    tc_item = {
        "id": "tc-test",
        "source": "fixture",
        "stratum": "single",
        "prompt": "Need weather.",
        "tools": [
            {
                "name": "weather.get",
                "description": "Get weather.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            }
        ],
        "gold": {"calls": [call], "order_matters": True},
        "match_policy": {
            "default": "exact",
            "normalizers": {},
            "allow_default_omission": False,
            "unordered_arrays": [],
        },
    }
    tc_text = json.dumps({"schema_version": "localbench.tc.v1", "calls": [call]})
    tc = grade_response("tools-single", tc_item, {"text": tc_text, "finish_reason": "stop"})

    instance = {
        "initial_state": {"current": "new", "entity_id": "x"},
        "canonical_final_state": {"current": "done", "entity_id": "x"},
        "required_arguments": {"finish": {"id": "x"}},
        "transitions": [{"tool": "finish", "from": "new", "to": "done"}],
        "inspect_tool": "inspect",
        "accepted_equivalent_trajectories": [[{"name": "finish", "arguments": {"id": "x"}}]],
    }
    stateful = grade_response(
        "tools-stateful",
        instance,
        {"text": "", "finish_reason": "stop", "parsed_tool_calls": [{"name": "finish", "arguments": {"id": "x"}}]},
    )

    assert tc["correct"] is True
    assert stateful["correct"] is True


def test_coding_grade_rejects_placeholder_and_accepts_only_verifier_artifact() -> None:
    placeholder = grade_response("coding", {"correct": True}, {"text": "", "correct": True})
    trusted = grade_response(
        "coding",
        {"correct": False},
        {
            "text": "",
            "code_artifact": {
                "verdict_source": "verifier",
                "verdict": {"passed": True},
                "image_digest": "sandbox@sha256:" + "a" * 64,
            },
        },
    )

    assert placeholder["correct"] is False
    assert placeholder["trusted_verdict"] is False
    assert trusted["correct"] is True
    assert trusted["trusted_verdict"] is True


def test_sandbox_command_keeps_all_v1_security_flags() -> None:
    argv = sandbox_command("sandbox@sha256:" + "b" * 64, ["python", "runner.py"])

    for flag in MANDATORY_SECURITY_FLAGS:
        assert any(tuple(argv[index : index + len(flag)]) == flag for index in range(len(argv)))


def test_sanity_gate_determinism_requires_independent_identical_restarts() -> None:
    source = {
        "category": "determinism",
        "gate_kind": "validity",
        "expected": {"answer": "101"},
    }
    first = {
        "server_start_id": "one",
        "text": "101",
        "token_ids": [1, 0, 1],
        "finish_reason": "stop",
        "parsed_tool_calls": [],
        "scorer_result": True,
    }
    second = {**first, "server_start_id": "two"}

    passing = grade_response("sanity-gates", source, first, repeated_generation=second)
    failing = grade_response("sanity-gates", source, first, repeated_generation={**second, "token_ids": [9]})

    assert passing["correct"] is True
    assert failing["correct"] is False


def test_signed_chance_correction_keeps_wrong_four_choice_item_negative() -> None:
    result = grade_response(
        "knowledge",
        {"answer_index": 0, "choices": ["one", "two", "three", "four"]},
        {"text": "Final answer: B", "finish_reason": "stop"},
    )

    assert result["correct"] is False
    assert result["chance_corrected"] == -1.0 / 3.0
