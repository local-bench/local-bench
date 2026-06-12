"""Tests for IFEval instruction-following scoring."""

from __future__ import annotations

from typing import TypeAlias

import pytest

from localbench.scorers.ifeval import score_ifeval

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _item(instruction_id: str, kwargs: dict[str, JsonValue] | None = None) -> dict[str, JsonValue]:
    return {
        "key": 1,
        "prompt": "Follow the instruction.",
        "instruction_id_list": [instruction_id],
        "kwargs": [kwargs or {}],
    }


@pytest.mark.parametrize(
    ("instruction_id", "kwargs", "passing_response", "failing_response"),
    [
        (
            "length_constraints:number_paragraphs",
            {"num_paragraphs": 2},
            "First paragraph.\n***\nSecond paragraph.",
            "Only one paragraph.",
        ),
        (
            "keywords:forbidden_words",
            {"forbidden_words": ["banana"]},
            "This response talks about apples.",
            "This response mentions banana.",
        ),
        (
            "change_case:capital_word_frequency",
            {"capital_frequency": 2, "capital_relation": "at least"},
            "NASA and ESA coordinate launches.",
            "NASA coordinates launches.",
        ),
        (
            "detectable_format:json_format",
            {},
            '{"answer": "yes"}',
            "answer: yes",
        ),
        (
            "detectable_content:postscript",
            {"postscript_marker": "P.S."},
            "The answer is short.\nP.S. extra note",
            "The answer is short.",
        ),
        (
            "detectable_format:title",
            {},
            "<<Plain Title>>\nBody text.",
            "<Plain Title>\nBody text.",
        ),
        (
            "length_constraints:number_words",
            {"num_words": 4, "relation": "at least"},
            "one two three four",
            "one two three",
        ),
        (
            "detectable_format:number_bullet_lists",
            {"num_bullets": 2},
            "* first\n- second",
            "* only one",
        ),
    ],
)
def test_score_ifeval_when_single_instruction_is_followed_or_broken(
    instruction_id: str,
    kwargs: dict[str, JsonValue],
    passing_response: str,
    failing_response: str,
) -> None:
    # Given a prompt item with one verifiable IFEval instruction.
    prompt_item = _item(instruction_id, kwargs)

    # When scoring a response that follows the instruction.
    passing = score_ifeval(prompt_item, passing_response)

    # Then strict prompt-level and instruction-level results are true.
    assert passing == {
        "follow_all": True,
        "per_instruction": [True],
        "strict": True,
    }

    # When scoring a response that breaks the instruction.
    failing = score_ifeval(prompt_item, failing_response)

    # Then strict prompt-level and instruction-level results are false.
    assert failing == {
        "follow_all": False,
        "per_instruction": [False],
        "strict": False,
    }


def test_score_ifeval_when_multiple_instructions_are_mixed() -> None:
    # Given a prompt item with two verifiable IFEval instructions.
    prompt_item = {
        "key": 2,
        "prompt": "Return JSON and avoid a forbidden word.",
        "instruction_id_list": [
            "detectable_format:json_format",
            "keywords:forbidden_words",
        ],
        "kwargs": [{}, {"forbidden_words": ["banana"]}],
    }

    # When only the first instruction is followed.
    result = score_ifeval(prompt_item, '{"word": "banana"}')

    # Then per-instruction scoring preserves the strict failure.
    assert result == {
        "follow_all": False,
        "per_instruction": [True, False],
        "strict": False,
    }
