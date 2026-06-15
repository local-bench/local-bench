from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias

from localbench.scorers.lcb import build_lcb_prompt, score_lcb

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def test_build_lcb_prompt_when_given_item_uses_test_output_prediction_format() -> None:
    # Given a LiveCodeBench Test Output Prediction item.
    item = _fixture_item(output="3")

    # When building the prompt.
    prompt = build_lcb_prompt(item)

    # Then it asks for the test output without executing candidate code.
    assert "Problem:" in prompt
    assert "Function:" in prompt
    assert "def add" in prompt
    assert "Test input:" in prompt
    assert "1\n2" in prompt
    assert "Only return the predicted output" in prompt


def test_score_lcb_when_response_matches_expected_output() -> None:
    # Given an item whose expected output is a JSON-encoded integer.
    item = _fixture_item(output="3")

    # When scoring a raw literal and a fenced assertion.
    raw = score_lcb(item, "3")
    asserted = score_lcb(item, "```python\nassert add(1, 2) == 3\n```")

    # Then both forms normalize to the expected output.
    assert raw == {"correct": True, "extracted": "3"}
    assert asserted == {"correct": True, "extracted": "3"}


def test_score_lcb_when_structured_response_matches_expected_output() -> None:
    # Given an item whose expected output is a JSON-encoded list.
    item = _fixture_item(output='["a", "b"]')

    # When scoring a Python literal assertion.
    result = score_lcb(item, "assert solve([1, 2]) == ['a', 'b']")

    # Then literal output comparison accepts the structured value without execution.
    assert result == {"correct": True, "extracted": '["a","b"]'}


def test_score_lcb_when_response_is_wrong_or_malformed_returns_false() -> None:
    # Given a valid item and malformed item shape.
    item = _fixture_item(output="3")

    # When scoring wrong and unsafe/malformed responses.
    wrong = score_lcb(item, "4")
    expression = score_lcb(item, "assert add(1, 2) == 1 + 2")
    missing_gold = score_lcb({"id": "bad"}, "3")

    # Then the scorer reports failure instead of executing or raising.
    assert wrong == {"correct": False, "extracted": "4"}
    assert expression == {"correct": False, "extracted": None}
    assert missing_gold == {"correct": False, "extracted": None}


def _fixture_item(*, output: str) -> JsonObject:
    return {
        "id": "lcb-test-001",
        "source_id": "2727:0",
        "source_dataset": "livecodebench/test_generation",
        "source_revision": "6f3ac40bbecf81eba15899139d279b077f2816fd",
        "source_url": "https://huggingface.co/datasets/livecodebench/test_generation",
        "license": "CC-BY-4.0",
        "source_site": "leetcode",
        "source_tos_note": "Problem statement originates from LeetCode; retain source-site ToS awareness.",
        "contest_date": "2024-01-06",
        "difficulty": "easy",
        "question_id": "fixture",
        "contest_id": "weekly-contest-fixture",
        "test_id": 0,
        "question_title": "add-two-numbers",
        "question_content": "Return the sum of two integers.",
        "starter_code": "def add(self, a: int, b: int) -> int:\n    pass",
        "function_name": "add",
        "input": "1\n2",
        "answer": output,
    }
