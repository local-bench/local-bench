from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

import pytest

from localbench._scoring import _score_response_detail
from localbench.scorers._reasoning import strip_reasoning

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Final answer: A", "Final answer: A"),
        ("  {\"schema_version\":\"localbench.tc.v1\",\"calls\":[]}  ", "  {\"schema_version\":\"localbench.tc.v1\",\"calls\":[]}  "),
    ],
)
def test_strip_reasoning_is_noop_when_text_has_no_reasoning_markers(
    text: str,
    expected: str,
) -> None:
    # Given clean scorer input.
    # When stripping reasoning.
    result = strip_reasoning(text)

    # Then the text is returned byte-for-byte unchanged.
    assert result == expected


def test_strip_reasoning_returns_text_after_last_think_close() -> None:
    # Given a response with complete leading reasoning.
    text = "<think>answer: B</think>Final answer: A"

    # When stripping reasoning.
    result = strip_reasoning(text)

    # Then only the answer after the reasoning block remains.
    assert result == "Final answer: A"


def test_strip_reasoning_uses_last_think_close_when_multiple_blocks_exist() -> None:
    # Given multiple complete reasoning blocks.
    text = "<think>first</think>draft<think>second</think>{\"ok\": true}"

    # When stripping reasoning.
    result = strip_reasoning(text)

    # Then the last close tag defines the scorer-visible answer.
    assert result == '{"ok": true}'


def test_strip_reasoning_returns_empty_for_unclosed_think_block() -> None:
    # Given a truncated response still inside a reasoning block.
    text = "<think>still deriving the answer"

    # When stripping reasoning.
    result = strip_reasoning(text)

    # Then the scorer receives no answer rather than crediting scratch work.
    assert result == ""


def test_strip_reasoning_keeps_final_harmony_message() -> None:
    # Given a harmony/channel style response with an analysis segment before the message.
    text = "<|channel|>analysis\nhidden scratch<|message|>Final answer: A"

    # When stripping reasoning.
    result = strip_reasoning(text)

    # Then only the final message is scored.
    assert result == "Final answer: A"


def test_strip_reasoning_removes_leading_gemma_empty_thought_scaffold() -> None:
    # Given a Gemma channel response that re-opened empty thought scaffolds before the answer.
    text = "<|channel>thought\n<channel|><|channel>thought\n<channel|>Final answer: C"

    # When stripping reasoning.
    result = strip_reasoning(text)

    # Then the empty channel scaffolds cannot corrupt the scorer-visible answer.
    assert result == "Final answer: C"


@dataclass(frozen=True, slots=True)
class ScorerCase:
    bench: str
    source_item: JsonObject
    clean_response: str
    adversarial_reasoning: str
    finish_reason: str | None = None


def test_score_response_detail_strips_reasoning_prefix_for_every_scorer_arm() -> None:
    # Given known-good answers for each scorer dispatch arm.
    cases = [
        ScorerCase(
            bench="mmlu_pro",
            source_item={
                "id": "mcq-think",
                "answer": "A",
                "options": ["alpha", "beta", "gamma", "delta"],
            },
            clean_response="Final answer: A",
            adversarial_reasoning="I considered C and D. answer: B",
        ),
        ScorerCase(
            bench="ifeval",
            source_item={
                "key": 1,
                "prompt": "Return JSON.",
                "instruction_id_list": ["detectable_format:json_format"],
                "kwargs": [{}],
            },
            clean_response='{"answer": "yes"}',
            adversarial_reasoning="A prose answer would fail the JSON instruction.",
        ),
        ScorerCase(
            bench="ifbench",
            source_item={
                "id": "ifbench-think",
                "key": "fixture",
                "prompt": "Respond with no whitespace.",
                "instruction_id_list": ["format:no_whitespace"],
                "kwargs": [{}],
            },
            clean_response="NoSpaces",
            adversarial_reasoning="Has spaces here.",
        ),
        ScorerCase(
            bench="genmath",
            source_item={"id": "genmath-think", "answer": "42"},
            clean_response="Final answer: 42",
            adversarial_reasoning="The answer is 99.",
        ),
        ScorerCase(
            bench="amo",
            source_item={"id": "math-symbolic-think", "answer": "7"},
            clean_response=r"\boxed{7}",
            adversarial_reasoning=r"The tempting wrong value is \boxed{99}.",
        ),
        ScorerCase(
            bench="bfcl",
            source_item=_bfcl_item(),
            clean_response="calculate_area(base=10, height=5)",
            adversarial_reasoning="calculate_area(base=10, height=99)",
        ),
        ScorerCase(
            bench="tc_json_v1",
            source_item=_tc_json_item(),
            clean_response=_tc_json_response(
                [_tool_call("weather.get", {"location": "Brisbane"})]
            ),
            adversarial_reasoning='{"schema_version":"localbench.tc.v1","calls":[]}',
        ),
        ScorerCase(
            bench="bfcl_multi_turn",
            source_item={
                "id": "bfcl-multi-think",
                "ground_truth": [],
                "involved_classes": [],
                "function": [],
            },
            clean_response="[]",
            adversarial_reasoning='[["unknown_tool()"]]',
        ),
        ScorerCase(
            bench="lcb",
            source_item={"id": "lcb-think", "answer": "3"},
            clean_response="3",
            adversarial_reasoning="4",
        ),
        ScorerCase(
            bench="ruler_32k",
            source_item=_ruler_item(),
            clean_response="needle-value",
            adversarial_reasoning="wrong-value",
        ),
    ]

    for case in cases:
        # When scoring the clean answer and the same answer after adversarial reasoning.
        clean = _score_response_detail(
            case.bench,
            case.source_item,
            case.clean_response,
            None,
            case.finish_reason,
        )
        prefixed = _score_response_detail(
            case.bench,
            case.source_item,
            f"<think>{case.adversarial_reasoning}</think>{case.clean_response}",
            None,
            case.finish_reason,
        )

        # Then the reasoning prefix cannot change scorer output.
        assert prefixed == clean, case.bench
        assert clean["correct"] is True, case.bench


def _bfcl_item() -> JsonObject:
    return {
        "id": "bfcl-think",
        "source_id": "simple_fixture",
        "category": "simple",
        "question": [[{"role": "user", "content": "Find the area of a triangle."}]],
        "function": [
            _function_schema(
                "calculate_area",
                {"base": [10], "height": [5], "unit": ["", "cm"]},
            )
        ],
        "possible_answer": [
            {"calculate_area": {"base": [10], "height": [5], "unit": ["", "cm"]}}
        ],
    }


def _function_schema(function_name: str, params: Mapping[str, JsonValue]) -> JsonObject:
    properties = {
        key: {"type": _schema_type(values), "description": key}
        for key, values in params.items()
        if isinstance(values, list)
    }
    required = [
        key for key, values in params.items() if isinstance(values, list) and "" not in values
    ]
    return {
        "name": function_name,
        "description": f"Tool {function_name}.",
        "parameters": {"type": "dict", "properties": properties, "required": required},
    }


def _schema_type(values: JsonValue) -> str:
    candidates = values if isinstance(values, list) else []
    first = next((value for value in candidates if value != ""), "")
    if isinstance(first, bool):
        return "boolean"
    if isinstance(first, int):
        return "integer"
    if isinstance(first, float):
        return "float"
    if isinstance(first, list):
        return "array"
    if isinstance(first, dict):
        return "dict"
    return "string"


def _tc_json_item() -> JsonObject:
    return {
        "id": "tc-json-think",
        "source": "test",
        "stratum": "unit",
        "prompt": "Need weather.",
        "tools": [
            _tool(
                "weather.get",
                {"location": {"type": "string"}},
                ["location"],
            )
        ],
        "gold": {
            "order_matters": True,
            "calls": [_tool_call("weather.get", {"location": "Brisbane"})],
        },
        "match_policy": {
            "default": "typed_canonical_json_equality",
            "normalizers": {},
            "allow_default_omission": True,
            "unordered_arrays": [],
        },
    }


def _tool(name: str, properties: JsonObject, required: list[str]) -> JsonObject:
    return {
        "name": name,
        "description": name,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def _tool_call(name: str, arguments: JsonObject) -> JsonObject:
    return {"name": name, "arguments": arguments}


def _tc_json_response(calls: list[JsonObject]) -> str:
    return json.dumps({"schema_version": "localbench.tc.v1", "calls": calls})


def _ruler_item() -> JsonObject:
    return {
        "id": "ruler-think",
        "seed": 1,
        "haystack_token_count": 32,
        "target_depth_percent": 50,
        "task_type": "niah_single",
        "needle_key": "needle-key",
        "needle_value": "needle-value",
    }
