from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

import pytest

from localbench.scorers.math_numeric import score_math as score_math_numeric
from localbench.scorers.math_symbolic import verify_math

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENMATH_FILES = (
    _REPO_ROOT / "suite" / "v0" / "genmath_quick.jsonl",
    _REPO_ROOT / "suite" / "v0" / "genmath_standard.jsonl",
)


def _load_genmath_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for path in _GENMATH_FILES:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                item = json.loads(line)
                item_id = item["id"]
                answer = item["answer"]
                cases.append((f"{path.name}:{line_number}:{item_id}", answer))
    return cases


def _fraction_from_gold(gold: str) -> Fraction:
    token = gold.strip().replace(",", "")
    if "/" in token:
        numerator, denominator = token.split("/", 1)
        return Fraction(Decimal(numerator)) / Fraction(Decimal(denominator))
    return Fraction(Decimal(token))


def _format_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _perturb_gold_answer(gold: str) -> str:
    try:
        value = _fraction_from_gold(gold)
    except (InvalidOperation, ValueError, ZeroDivisionError) as error:
        raise AssertionError(f"Unsupported genmath gold answer {gold!r}") from error
    delta = max(abs(value), Fraction(1, 1))
    return _format_fraction(value + delta)


@pytest.mark.parametrize(("case_id", "gold"), _load_genmath_cases())
def test_verify_math_matches_numeric_scorer_when_genmath_answer_is_checked(
    case_id: str,
    gold: str,
) -> None:
    # Given a frozen genmath gold answer and one perturbed wrong answer.
    correct_response = f"After solving, final answer: {gold}"
    wrong_answer = _perturb_gold_answer(gold)
    wrong_response = f"After solving, final answer: {wrong_answer}"

    # When both scorers check the correct and wrong responses.
    old_correct = score_math_numeric(correct_response, gold)
    new_correct = verify_math(correct_response, gold)
    old_wrong = score_math_numeric(wrong_response, gold)
    new_wrong = verify_math(wrong_response, gold)

    # Then the symbolic scorer preserves frozen genmath scoring behavior.
    assert old_correct is True, f"{case_id} numeric scorer rejected gold {gold!r}"
    assert new_correct is old_correct, f"{case_id} symbolic scorer rejected gold {gold!r}"
    assert old_wrong is False, f"{case_id} perturbation {wrong_answer!r} was not wrong"
    assert new_wrong is old_wrong, f"{case_id} symbolic scorer accepted {wrong_answer!r}"
