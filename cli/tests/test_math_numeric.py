"""Tests for numeric answer extraction and scoring."""

from __future__ import annotations

import pytest

from localbench.scorers.math_numeric import (
    equivalent,
    extract_final_number,
    score_math,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"\boxed{42}", "42"),
        (r"\boxed{ 3/4 }", "3/4"),
        ("Final answer: $1,234 meters", "1234"),
        ("answer is -7.", "-7"),
        ("Answer: 0.75", "0.75"),
        ("Therefore final answer = 3e8 m/s", "3e8"),
        ("We used 2 and 5, so 9", "9"),
        ("No numeric answer", None),
        ("answer is about -0.125 kg", "-0.125"),
        (r"\boxed{$1,234.50}", "1234.50"),
        ("Final answer: 6/8.", "6/8"),
        ("Answer is +12 volts", "12"),
        ("The value is .5", "0.5"),
        ("Final answer: -3/4 units", "-3/4"),
        ("Final answer: 1,234,567", "1234567"),
        ("x=5; y=10", "10"),
        (r"\boxed{not a number} then final answer: 8", "8"),
        ("Answer: 2.5e-3 seconds", "2.5e-3"),
        ("Price is $0.99", "0.99"),
        ("final answer: -1,234.00 USD", "-1234.00"),
        ("answer is 10 apples and 2 oranges", "10"),
        ("1/2 then 3/4", "3/4"),
    ],
)
def test_extract_final_number_when_response_contains_numeric_patterns(
    text: str,
    expected: str | None,
) -> None:
    # Given text that may contain a final numeric answer.
    # When extracting the final number.
    result = extract_final_number(text)

    # Then the number is normalized or rejected.
    assert result == expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("3/4", "0.75", True),
        ("1/3", "0.333333", True),
        ("1000", "1,000", True),
        ("3e8", "300000000", True),
        ("-2", "2", False),
        ("foo", "1", False),
        ("1.0002", "1", False),
    ],
)
def test_equivalent_when_numbers_use_different_formats(
    left: str,
    right: str,
    expected: bool,
) -> None:
    # Given two candidate numeric strings.
    # When comparing them for benchmark equivalence.
    result = equivalent(left, right)

    # Then exact and tolerant numeric matches are accepted.
    assert result is expected


def test_score_math_when_extracted_number_matches_gold() -> None:
    # Given a boxed fractional response.
    # When scoring against an equivalent decimal gold answer.
    result = score_math(r"\boxed{3/4}", "0.75")

    # Then the score is correct.
    assert result is True


def test_score_math_when_extracted_number_does_not_match_gold() -> None:
    # Given a numeric response.
    # When scoring against a different gold answer.
    result = score_math("answer is 5", "6")

    # Then the score is wrong.
    assert result is False


def test_score_math_when_no_number_is_extracted() -> None:
    # Given a response without a number.
    # When scoring against any gold answer.
    result = score_math("No answer.", "1")

    # Then missing extraction is wrong.
    assert result is False
