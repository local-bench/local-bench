"""Algebra templates."""

from __future__ import annotations

from fractions import Fraction
from random import Random

from genmath_gen.models import Answer, ParamMap, Params, Template
from genmath_gen.utils import finish, i, param_copy


def templates() -> list[Template]:
    """Return algebra templates."""
    return [
        Template(
            name="linear_ax_plus_b",
            category="algebra",
            difficulty="easy",
            sample=_sample_ax_plus_b,
            render=lambda p: finish(
                f"Solve for x: {i(p, 'a')}x + {i(p, 'b')} = {i(p, 'c')}."
            ),
            answer=lambda p: i(p, "x"),
            verify=_verify_ax_plus_b,
        ),
        Template(
            name="linear_ax_minus_b",
            category="algebra",
            difficulty="easy",
            sample=_sample_ax_minus_b,
            render=lambda p: finish(
                f"Solve for x: {i(p, 'a')}x - {i(p, 'b')} = {i(p, 'c')}."
            ),
            answer=lambda p: i(p, "x"),
            verify=_verify_ax_minus_b,
        ),
        Template(
            name="division_then_shift",
            category="algebra",
            difficulty="easy",
            sample=_sample_division_shift,
            render=lambda p: finish(
                f"Solve for x: x/{i(p, 'd')} + {i(p, 'b')} = {i(p, 'c')}."
            ),
            answer=lambda p: i(p, "x"),
            verify=_verify_division_shift,
        ),
        Template(
            name="arithmetic_sequence_nth",
            category="algebra",
            difficulty="medium",
            sample=lambda rng: param_copy(
                first=rng.randint(-12, 30),
                diff=rng.randint(2, 14),
                n=rng.randint(8, 30),
            ),
            render=lambda p: finish(
                f"An arithmetic sequence has first term {i(p, 'first')} and common "
                f"difference {i(p, 'diff')}. What is term {i(p, 'n')}?"
            ),
            answer=lambda p: i(p, "first") + (i(p, "n") - 1) * i(p, "diff"),
            verify=lambda p, a: int(a)
            == i(p, "first") + (i(p, "n") - 1) * i(p, "diff"),
        ),
        Template(
            name="geometric_sequence_nth",
            category="algebra",
            difficulty="medium",
            sample=lambda rng: param_copy(
                first=rng.randint(2, 9),
                ratio=rng.randint(2, 4),
                n=rng.randint(4, 8),
            ),
            render=lambda p: finish(
                f"A geometric sequence has first term {i(p, 'first')} and common "
                f"ratio {i(p, 'ratio')}. What is term {i(p, 'n')}?"
            ),
            answer=lambda p: i(p, "first") * i(p, "ratio") ** (i(p, "n") - 1),
            verify=lambda p, a: int(a)
            == i(p, "first") * i(p, "ratio") ** (i(p, "n") - 1),
        ),
        Template(
            name="system_solve_x",
            category="algebra",
            difficulty="medium",
            sample=_sample_system,
            render=lambda p: finish(
                f"Solve for x: {i(p, 'a')}x + {i(p, 'b')}y = {i(p, 'e')} and "
                f"{i(p, 'c')}x + {i(p, 'd')}y = {i(p, 'f')}."
            ),
            answer=lambda p: i(p, "x"),
            verify=_verify_system,
        ),
        Template(
            name="quadratic_larger_root",
            category="algebra",
            difficulty="medium",
            sample=_sample_quadratic,
            render=lambda p: finish(
                f"The equation x^2 - {i(p, 'sum')}x + {i(p, 'product')} = 0 "
                "has two positive integer roots. What is the larger root?"
            ),
            answer=lambda p: i(p, "larger"),
            verify=_verify_quadratic,
        ),
        Template(
            name="linear_composition_value",
            category="algebra",
            difficulty="hard",
            sample=lambda rng: param_copy(
                a=rng.randint(2, 8),
                b=rng.randint(-12, 18),
                c=rng.randint(2, 7),
                d=rng.randint(-10, 15),
                x=rng.randint(-8, 12),
            ),
            render=lambda p: finish(
                f"Let f(t) = {i(p, 'a')}t + {i(p, 'b')} and "
                f"g(t) = {i(p, 'c')}t + {i(p, 'd')}. What is f(g({i(p, 'x')}))?"
            ),
            answer=lambda p: i(p, "a") * (i(p, "c") * i(p, "x") + i(p, "d"))
            + i(p, "b"),
            verify=lambda p, a: int(a)
            == i(p, "a") * (i(p, "c") * i(p, "x") + i(p, "d")) + i(p, "b"),
        ),
        Template(
            name="scaled_parentheses_equation",
            category="algebra",
            difficulty="hard",
            sample=_sample_scaled_parentheses,
            render=lambda p: finish(
                f"Solve for x: {i(p, 'a')} times (x - {i(p, 'b')}) / {i(p, 'c')} "
                f"= {i(p, 'd')}."
            ),
            answer=lambda p: i(p, "x"),
            verify=_verify_scaled_parentheses,
        ),
    ]


def _sample_ax_plus_b(rng: Random) -> Params:
    x = rng.randint(1, 30)
    a = rng.randint(2, 12)
    b = rng.randint(3, 40)
    return param_copy(a=a, b=b, c=a * x + b, x=x)


def _sample_ax_minus_b(rng: Random) -> Params:
    x = rng.randint(2, 35)
    a = rng.randint(2, 12)
    b = rng.randint(3, 50)
    return param_copy(a=a, b=b, c=a * x - b, x=x)


def _sample_division_shift(rng: Random) -> Params:
    d = rng.randint(2, 12)
    quotient = rng.randint(4, 30)
    b = rng.randint(3, 20)
    return param_copy(d=d, b=b, c=quotient + b, x=quotient * d)


def _sample_system(rng: Random) -> Params:
    while True:
        a = rng.randint(1, 8)
        b = rng.randint(1, 8)
        c = rng.randint(1, 8)
        d = rng.randint(1, 8)
        if a * d != b * c:
            x = rng.randint(-8, 12)
            y = rng.randint(-8, 12)
            return param_copy(a=a, b=b, c=c, d=d, e=a * x + b * y, f=c * x + d * y, x=x, y=y)


def _sample_quadratic(rng: Random) -> Params:
    smaller = rng.randint(1, 12)
    larger = smaller + rng.randint(2, 15)
    return param_copy(
        smaller=smaller,
        larger=larger,
        sum=smaller + larger,
        product=smaller * larger,
    )


def _sample_scaled_parentheses(rng: Random) -> Params:
    while True:
        c = rng.randint(2, 9)
        d = rng.randint(3, 18)
        b = rng.randint(1, 20)
        a = rng.choice((1, 2, 3, 4, 6))
        if (c * d) % a == 0:
            return param_copy(a=a, b=b, c=c, d=d, x=b + c * d // a)


def _verify_ax_plus_b(params: ParamMap, answer: Answer) -> bool:
    return i(params, "a") * int(answer) + i(params, "b") == i(params, "c")


def _verify_ax_minus_b(params: ParamMap, answer: Answer) -> bool:
    return i(params, "a") * int(answer) - i(params, "b") == i(params, "c")


def _verify_division_shift(params: ParamMap, answer: Answer) -> bool:
    return int(answer) // i(params, "d") + i(params, "b") == i(params, "c")


def _verify_system(params: ParamMap, answer: Answer) -> bool:
    x = int(answer)
    y = i(params, "y")
    return (
        i(params, "a") * x + i(params, "b") * y == i(params, "e")
        and i(params, "c") * x + i(params, "d") * y == i(params, "f")
    )


def _verify_quadratic(params: ParamMap, answer: Answer) -> bool:
    x = int(answer)
    return x * x - i(params, "sum") * x + i(params, "product") == 0 and x >= i(
        params, "smaller"
    )


def _verify_scaled_parentheses(params: ParamMap, answer: Answer) -> bool:
    return Fraction(i(params, "a") * (int(answer) - i(params, "b")), i(params, "c")) == i(
        params, "d"
    )
