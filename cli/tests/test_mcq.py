"""Tests for multiple-choice extraction and scoring."""

from __future__ import annotations

import pytest

from localbench.scorers.mcq import extract_choice, score_mcq, score_mcq_detailed


@pytest.mark.parametrize(
    ("text", "n_options", "expected"),
    [
        ("Answer: C", 4, "C"),
        ("The answer is (C).", 4, "C"),
        ("final answer: d", 4, "D"),
        ("After the work, **C**", 4, "C"),
        (r"The result is \boxed{C}", 4, "C"),
        ("Reasoning...\nC", 4, "C"),
        ("Reasoning ends with (C)", 4, "C"),
        ("I considered C, but the answer is D.", 4, "D"),
        ("A looked close. B failed. Final answer: C.", 4, "C"),
        ("The answer is J.", 10, "J"),
        ("answer: j", 10, "J"),
        ("The answer is J.", 4, None),
        ("The answer is catalyst.", 4, None),
        ("", 4, None),
        ("No option follows.", 4, None),
        ("Answer: A. Later, answer: B.", 4, "B"),
        (r"\boxed{A} then \boxed{B}", 4, "B"),
        ("Answer: C. Because of that, answer is c.", 4, "C"),
        ("Answer: D. Photosynthesis is the process.", 4, "D"),
        ("Final answer is (B).", 4, "B"),
        ("ANSWER IS [A]", 4, "A"),
        ("I will choose ** e **", 5, "E"),
        ("Reasoning\n(f)", 6, "F"),
        ("Options were A, B, C. The final answer: A.", 4, "A"),
        ("The best choice is (H).", 8, "H"),
        ("final answer: A. final answer: B.", 4, "B"),
        ("Answer: B - evaporation.", 4, "B"),
        ("abc", 4, None),
        ("The answer is a.", 1, "A"),
        ("The answer is C... wait, no, the answer is D.", 4, "D"),
        ("Answer: B\n\nD", 4, "B"),
        ("Reasoning...\nA\nB", 4, None),
        ("Maybe (A), but maybe (B)", 4, None),
        ("Final answer: A or B", 4, None),
        ("The answer is A or B", 4, None),
        ("Final answer: C", 4, "C"),
        ("The answer is (D).", 4, "D"),
        # Answer stated first, another option only mentioned in trailing explanation -> extract the answer.
        ("answer is A because B is wrong", 10, "A"),
        ("The answer is D. Note option B is a distractor.", 10, "D"),
        ("The correct answer is G, not A.", 10, "G"),
        # Adjacent alternation is genuinely ambiguous.
        ("Final answer: A and B", 10, None),
        ("answer: A/B", 10, None),
    ],
)
def test_extract_choice_when_response_contains_choice_patterns(
    text: str,
    n_options: int,
    expected: str | None,
) -> None:
    # Given text that may contain a final answer marker.
    # When extracting the final choice.
    result = extract_choice(text, n_options)

    # Then the chosen letter is normalized or rejected.
    assert result == expected


def test_score_mcq_when_extracted_choice_matches_gold() -> None:
    # Given a response with a lower-case answer marker.
    # When scoring against the matching gold letter.
    result = score_mcq("Reasoning. Answer: b.", "B", 4)

    # Then the score is correct.
    assert result is True


def test_score_mcq_when_no_choice_is_extracted() -> None:
    # Given a response without a usable final answer.
    # When scoring against any gold letter.
    result = score_mcq("I cannot tell.", "A", 4)

    # Then missing extraction is wrong.
    assert result is False


def test_score_mcq_when_choice_does_not_match_gold() -> None:
    # Given a response with a final answer marker.
    # When scoring against a different gold letter.
    result = score_mcq("Final answer: D", "A", 4)

    # Then the score is wrong.
    assert result is False


def test_score_mcq_detailed_when_answer_is_extracted() -> None:
    # Given a response with a final answer marker.
    # When requesting detailed MCQ scoring.
    result = score_mcq_detailed("Final answer: c", "C", 4)

    # Then both extraction and correctness are returned.
    assert result == {"extracted": "C", "correct": True}


def test_score_mcq_detailed_when_answer_is_missing() -> None:
    # Given a response without a usable answer.
    # When requesting detailed MCQ scoring.
    result = score_mcq_detailed("No final choice.", "A", 4)

    # Then missing extraction is visible and scored as wrong.
    assert result == {"extracted": None, "correct": False}
