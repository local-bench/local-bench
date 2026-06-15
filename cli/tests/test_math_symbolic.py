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


@pytest.mark.parametrize(
    ("response_text", "gold"),
    [
        # Real over-acceptances observed from math_verify's loose settings (olymmath-hard-052,
        # olymmath-hard-070): a numerically/structurally different final answer was credited.
        (r"\boxed{2}", "2sqrt(2)-1"),  # 2 != 2*sqrt(2)-1 (=1.828...)
        (r"\boxed{[-1, 1]}", "(-1, 1)"),  # closed interval != open interval
    ],
)
def test_verify_math_rejects_math_verify_over_acceptance(response_text: str, gold: str) -> None:
    # Given a final answer that is not equivalent to gold but which math_verify's loose
    # settings previously credited.
    # When verifying with strict-local-equivalence-first.
    # Then the over-acceptance is rejected.
    assert verify_math(response_text, gold) is False


def test_verify_math_rejects_truncated_bare_number_non_answer() -> None:
    # Given a TRUNCATED output (finish_reason="length") with no boxed/marked final answer,
    # whose trailing scratch number happens to coincide with gold (the olymmath/amo local
    # false-positive pattern: every local "correct" math item was a finish_reason=length
    # non-answer credited by the bare-number fallback).
    truncated = "We test n=1, then n=2, and continuing the sum so far is 4"

    # When verifying as truncated, the coincidental bare number is NOT credited;
    # but the identical text from a COMPLETED output keeps the bare-number fallback.
    assert verify_math(truncated, "4", finish_reason="length") is False
    assert verify_math(truncated, "4", finish_reason="stop") is True


def test_verify_math_keeps_boxed_answer_even_when_truncated() -> None:
    # Given a truncated output that DID emit a boxed answer before being cut off.
    truncated_boxed = r"The minimum is \boxed{7}. To double-check we also compute 9"

    # When verifying as truncated, the genuine boxed answer still counts.
    assert verify_math(truncated_boxed, "7", finish_reason="length") is True


@pytest.mark.parametrize(
    ("text", "allow_fallback", "expected"),
    [
        ("scratch work 1, 2, 3", True, "3"),  # completed: bare-number fallback active
        ("scratch work 1, 2, 3", False, None),  # truncated: bare-number fallback suppressed
        (r"\boxed{5} then 9", False, "5"),  # a boxed answer survives suppression
    ],
)
def test_extract_math_answer_bare_number_fallback_gate(
    text: str,
    allow_fallback: bool,
    expected: str | None,
) -> None:
    # Given the bare-number fallback gate (off for truncated outputs).
    assert extract_math_answer(text, allow_bare_number_fallback=allow_fallback) == expected
