"""Shared models for the standalone generated-math builder."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from random import Random
from typing import Literal, TypeAlias

Category: TypeAlias = Literal[
    "arithmetic",
    "number_theory",
    "algebra",
    "combinatorics",
    "probability",
    "geometry",
    "rates_word",
]
Difficulty: TypeAlias = Literal["easy", "medium", "hard"]
ParamValue: TypeAlias = int | str
Params: TypeAlias = dict[str, ParamValue]
ParamMap: TypeAlias = Mapping[str, ParamValue]
Answer: TypeAlias = int | Fraction
Sampler: TypeAlias = Callable[[Random], Params]
Renderer: TypeAlias = Callable[[ParamMap], str]
AnswerFn: TypeAlias = Callable[[ParamMap], Answer]
BruteForceFn: TypeAlias = Callable[[ParamMap], Answer]
VerifyFn: TypeAlias = Callable[[ParamMap, Answer], bool]


@dataclass(frozen=True, slots=True)
class Template:
    """A parameterized generated-math item template."""

    name: str
    category: Category
    difficulty: Difficulty
    sample: Sampler
    render: Renderer
    answer: AnswerFn
    brute_force: BruteForceFn | None = None
    verify: VerifyFn | None = None


def answer_to_string(answer: Answer) -> str:
    """Serialize an exact numeric answer for the math_numeric scorer."""
    if isinstance(answer, Fraction):
        if answer.denominator == 1:
            return str(answer.numerator)
        return f"{answer.numerator}/{answer.denominator}"
    return str(answer)
