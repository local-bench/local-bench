"""Robustness: the symbolic math scorer must never crash a run on pathological model output.

Regression for a real overnight failure: a model produced a response that parsed into a
sympy `FiniteSet ** power` expression, and simplification raised
`AttributeError: 'FiniteSet' object has no attribute 'as_coeff_Mul'`, which crashed the entire
benchmark run. verify_math / extract_math_answer must swallow ANY such failure (a garbage answer
is simply "not equivalent"), never propagate it.
"""

from __future__ import annotations

import pytest

from localbench.scorers.math_symbolic import extract_math_answer, verify_math

_PATHOLOGICAL = [
    "answer: {1, 2, 3}^{2}",
    "the result is {a, b}**2",
    r"\boxed{\{1,2\}^{2}}",
    "final answer: (1, 2, 3) / 0",
    "2^{1,2,3}",
    r"\boxed{\frac{1}{0}}",
    "[1, 2)^2 + {3}",
    "answer is " + "Z" * 4000,
    "Final answer: \\{1,2,3\\}**\\{4,5\\}",
]


@pytest.mark.parametrize("response", _PATHOLOGICAL, ids=range(len(_PATHOLOGICAL)))
def test_verify_math_never_raises_on_pathological_response(response: str) -> None:
    # Given a pathological model response (this code runs on every real model answer).
    # When scoring it against a gold value, it returns a clean bool without raising.
    assert verify_math(response, "5") is False


@pytest.mark.parametrize("response", _PATHOLOGICAL, ids=range(len(_PATHOLOGICAL)))
def test_extract_math_answer_never_raises_on_pathological_response(response: str) -> None:
    # When extracting the answer, it returns a string or None without raising.
    extracted = extract_math_answer(response)
    assert extracted is None or isinstance(extracted, str)


def test_verify_math_still_matches_valid_set_answer() -> None:
    # Guard rails must not break legitimate set-equality scoring.
    assert verify_math("the final answer is {1, 2, 3}", "{1,2,3}") is True
