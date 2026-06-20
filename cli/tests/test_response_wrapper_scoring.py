from __future__ import annotations

from localbench._scoring import _score_response, _strip_response_wrapper


def test_strip_response_wrapper_strips_one_balanced_outer_wrapper() -> None:
    assert _strip_response_wrapper("<response>\nFinal answer: C\n</response>") == "Final answer: C"
    assert (
        _strip_response_wrapper("<response><response>Final answer: C</response></response>")
        == "<response>Final answer: C</response>"
    )


def test_strip_response_wrapper_leaves_unbalanced_or_non_outer_text_unchanged() -> None:
    assert _strip_response_wrapper("<response>Final answer: C") == "<response>Final answer: C"
    assert (
        _strip_response_wrapper("prefix <response>Final answer: C</response>")
        == "prefix <response>Final answer: C</response>"
    )


def test_mmlu_pro_scoring_strips_response_wrapper_before_choice_extraction() -> None:
    source_item = {"answer": "C", "options": ["A", "B", "C", "D"]}

    extracted, correct = _score_response(
        "mmlu_pro",
        source_item,
        "<response>\nFinal answer: C\n</response>",
        None,
    )

    assert extracted == "C"
    assert correct is True


def test_ifbench_scoring_strips_response_wrapper_before_constraint_checking() -> None:
    source_item = {
        "id": "ifbench-wrapper-001",
        "key": "fixture",
        "prompt": "Follow the instruction.",
        "instruction_id_list": ["format:no_whitespace"],
        "kwargs": [{}],
    }

    extracted, correct = _score_response(
        "ifbench",
        source_item,
        "<response>\nNoSpaces\n</response>",
        None,
    )

    assert extracted is None
    assert correct is True
