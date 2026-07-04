"""Arithmetic templates."""

from __future__ import annotations

from fractions import Fraction
from random import Random

from genmath_gen.models import Params, Template
from genmath_gen.utils import finish, frac, i, param_copy


def templates() -> list[Template]:
    """Return arithmetic templates."""
    return [
        Template(
            name="sum_three_numbers",
            category="arithmetic",
            difficulty="easy",
            sample=lambda rng: param_copy(
                a=rng.randint(12, 89), b=rng.randint(12, 89), c=rng.randint(12, 89)
            ),
            render=lambda p: finish(f"Compute {i(p, 'a')} + {i(p, 'b')} + {i(p, 'c')}."),
            answer=lambda p: i(p, "a") + i(p, "b") + i(p, "c"),
        ),
        Template(
            name="subtract_then_add",
            category="arithmetic",
            difficulty="easy",
            sample=lambda rng: param_copy(
                start=rng.randint(80, 180),
                remove=rng.randint(15, 60),
                add=rng.randint(10, 55),
            ),
            render=lambda p: finish(
                f"Start with {i(p, 'start')}, subtract {i(p, 'remove')}, "
                f"then add {i(p, 'add')}."
            ),
            answer=lambda p: i(p, "start") - i(p, "remove") + i(p, "add"),
        ),
        Template(
            name="product_minus_offset",
            category="arithmetic",
            difficulty="easy",
            sample=lambda rng: param_copy(
                a=rng.randint(6, 18), b=rng.randint(7, 19), offset=rng.randint(9, 50)
            ),
            render=lambda p: finish(
                f"What is {i(p, 'a')} times {i(p, 'b')}, minus {i(p, 'offset')}?"
            ),
            answer=lambda p: i(p, "a") * i(p, "b") - i(p, "offset"),
        ),
        Template(
            name="fraction_sum",
            category="arithmetic",
            difficulty="medium",
            sample=_sample_fraction_sum,
            render=lambda p: finish(
                f"Compute {i(p, 'a')}/{i(p, 'b')} + {i(p, 'c')}/{i(p, 'd')}.",
                fraction=True,
            ),
            answer=lambda p: frac(i(p, "a"), i(p, "b")) + frac(i(p, "c"), i(p, "d")),
        ),
        Template(
            name="average_of_five",
            category="arithmetic",
            difficulty="medium",
            sample=lambda rng: param_copy(
                a=rng.randint(10, 90),
                b=rng.randint(10, 90),
                c=rng.randint(10, 90),
                d=rng.randint(10, 90),
                e=rng.randint(10, 90),
            ),
            render=lambda p: finish(
                "Find the average of "
                f"{i(p, 'a')}, {i(p, 'b')}, {i(p, 'c')}, {i(p, 'd')}, and {i(p, 'e')}.",
                fraction=True,
            ),
            answer=lambda p: Fraction(
                i(p, "a") + i(p, "b") + i(p, "c") + i(p, "d") + i(p, "e"),
                5,
            ),
        ),
        Template(
            name="weighted_total",
            category="arithmetic",
            difficulty="medium",
            sample=lambda rng: param_copy(
                groups_a=rng.randint(3, 11),
                size_a=rng.randint(6, 24),
                groups_b=rng.randint(2, 9),
                size_b=rng.randint(5, 21),
            ),
            render=lambda p: finish(
                f"There are {i(p, 'groups_a')} groups of {i(p, 'size_a')} and "
                f"{i(p, 'groups_b')} groups of {i(p, 'size_b')}. How many items are there?"
            ),
            answer=lambda p: i(p, "groups_a") * i(p, "size_a")
            + i(p, "groups_b") * i(p, "size_b"),
        ),
        Template(
            name="nested_operations",
            category="arithmetic",
            difficulty="medium",
            sample=lambda rng: param_copy(
                a=rng.randint(8, 30),
                b=rng.randint(4, 22),
                c=rng.randint(12, 30),
                d=rng.randint(2, 10),
                e=rng.randint(5, 40),
            ),
            render=lambda p: finish(
                f"Compute ({i(p, 'a')} + {i(p, 'b')}) "
                f"times ({i(p, 'c')} - {i(p, 'd')}) plus {i(p, 'e')}."
            ),
            answer=lambda p: (i(p, "a") + i(p, "b")) * (i(p, "c") - i(p, "d"))
            + i(p, "e"),
        ),
        Template(
            name="successive_percent_changes",
            category="arithmetic",
            difficulty="hard",
            sample=_sample_successive_percent,
            render=lambda p: finish(
                f"A value starts at {i(p, 'start')}. It increases by {i(p, 'up')}% "
                f"and then decreases by {i(p, 'down')}%. What is the final value?",
                fraction=True,
            ),
            answer=lambda p: Fraction(
                i(p, "start") * (100 + i(p, "up")) * (100 - i(p, "down")),
                10_000,
            ),
        ),
        Template(
            name="fraction_of_remainder",
            category="arithmetic",
            difficulty="hard",
            sample=_sample_fraction_remainder,
            render=lambda p: finish(
                f"Begin with {i(p, 'total')}. Use {i(p, 'a')}/{i(p, 'b')} of it, "
                f"then use {i(p, 'c')}/{i(p, 'd')} of what remains. "
                "How much is left?",
                fraction=True,
            ),
            answer=lambda p: Fraction(i(p, "total"), 1)
            * (1 - frac(i(p, "a"), i(p, "b")))
            * (1 - frac(i(p, "c"), i(p, "d"))),
        ),
    ]


def _sample_fraction_sum(rng: Random) -> Params:
    b = rng.randint(3, 12)
    d = rng.randint(3, 12)
    return param_copy(a=rng.randint(1, b - 1), b=b, c=rng.randint(1, d - 1), d=d)


def _sample_successive_percent(rng: Random) -> Params:
    up = rng.choice((10, 20, 25, 40, 50))
    down = rng.choice((10, 20, 25, 40))
    start = rng.randint(8, 80) * 20
    return param_copy(start=start, up=up, down=down)


def _sample_fraction_remainder(rng: Random) -> Params:
    b = rng.randint(3, 10)
    d = rng.randint(3, 10)
    return param_copy(
        total=rng.randint(24, 180),
        a=rng.randint(1, b - 1),
        b=b,
        c=rng.randint(1, d - 1),
        d=d,
    )
