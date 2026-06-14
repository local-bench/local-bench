from __future__ import annotations

import pytest

from localbench.scorers.math_symbolic import extract_math_answer, verify_math


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"\boxed{42}", "42"),
        (r"\boxed{\frac{3}{4}}", r"\frac{3}{4}"),
        ("Final answer: (x+1)^2", "(x+1)^2"),
        ("The answer is \\sqrt{2}.", r"\sqrt{2}"),
        ("We tried 2 and 3. Therefore, final answer = 5", "5"),
        ("No answer marker or value", None),
        ("", None),
    ],
)
def test_extract_math_answer_when_response_contains_answer_patterns(
    text: str,
    expected: str | None,
) -> None:
    # Given text that may contain a final math answer.
    # When extracting the answer.
    result = extract_math_answer(text)

    # Then the final answer is returned without numeric-only normalization.
    assert result == expected


@pytest.mark.parametrize(
    ("response_text", "gold"),
    [
        ("Final answer: 42", "42"),
        ("answer is -0.125", "-1/8"),
        (r"\boxed{+\frac{3}{4}}", "0.75"),
        ("Therefore final answer = 2.5e-3", "0.0025"),
        (r"The answer is \sqrt{8}.", r"2\sqrt{2}"),
        (r"\boxed{\pi}", "pi"),
        ("Final answer: e^2", "exp(2)"),
        ("Final answer: (x+1)^2", "x^2 + 2*x + 1"),
        ("Final answer: 1:2", "2:4"),
        (r"\boxed{\{1,2,3\}}", r"\{3,2,1\}"),
        ("Final answer: (1, 2)", "(1,2)"),
        ("Final answer: [0, 1]", r"\left[0,1\right]"),
    ],
)
def test_verify_math_when_equivalent_answers_use_supported_forms(
    response_text: str,
    gold: str,
) -> None:
    # Given a response and gold answer with equivalent math forms.
    # When verifying the response.
    result = verify_math(response_text, gold)

    # Then the answer is accepted.
    assert result is True


@pytest.mark.parametrize(
    ("response_text", "gold"),
    [
        ("Final answer: 5", "6"),
        ("", "1"),
        ("Final answer: x + 1", "x + 2"),
        ("Final answer: not @@@ parseable", "1"),
    ],
)
def test_verify_math_when_answer_is_missing_or_not_equivalent(
    response_text: str,
    gold: str,
) -> None:
    # Given a response that is wrong, empty, or malformed.
    # When verifying the response.
    result = verify_math(response_text, gold)

    # Then the answer is rejected without raising.
    assert result is False
