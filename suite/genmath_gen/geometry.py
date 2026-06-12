"""Geometry templates."""

from __future__ import annotations

from fractions import Fraction

from genmath_gen.models import Answer, ParamMap, Template
from genmath_gen.utils import finish, frac, i, param_copy


def templates() -> list[Template]:
    """Return geometry templates."""
    return [
        Template(
            name="rectangle_area",
            category="geometry",
            difficulty="easy",
            sample=lambda rng: param_copy(length=rng.randint(5, 40), width=rng.randint(3, 25)),
            render=lambda p: finish(
                f"A rectangle has length {i(p, 'length')} and width {i(p, 'width')}. "
                "What is its area?"
            ),
            answer=lambda p: i(p, "length") * i(p, "width"),
            verify=lambda p, a: int(a) == i(p, "length") * i(p, "width"),
        ),
        Template(
            name="triangle_area",
            category="geometry",
            difficulty="easy",
            sample=lambda rng: param_copy(base=2 * rng.randint(3, 25), height=rng.randint(4, 30)),
            render=lambda p: finish(
                f"A triangle has base {i(p, 'base')} and height {i(p, 'height')}. "
                "What is its area?"
            ),
            answer=lambda p: i(p, "base") * i(p, "height") // 2,
            verify=lambda p, a: int(a) * 2 == i(p, "base") * i(p, "height"),
        ),
        Template(
            name="trapezoid_area",
            category="geometry",
            difficulty="medium",
            sample=lambda rng: param_copy(
                base_a=rng.randint(5, 30),
                base_b=rng.randint(5, 30),
                height=rng.randint(4, 20),
            ),
            render=lambda p: finish(
                f"A trapezoid has bases {i(p, 'base_a')} and {i(p, 'base_b')} "
                f"and height {i(p, 'height')}. What is its area?",
                fraction=True,
            ),
            answer=lambda p: frac((i(p, "base_a") + i(p, "base_b")) * i(p, "height"), 2),
            verify=_verify_trapezoid,
        ),
        Template(
            name="rectangular_prism_volume",
            category="geometry",
            difficulty="medium",
            sample=lambda rng: param_copy(
                length=rng.randint(4, 18),
                width=rng.randint(4, 16),
                height=rng.randint(3, 15),
            ),
            render=lambda p: finish(
                f"A rectangular prism has side lengths {i(p, 'length')}, "
                f"{i(p, 'width')}, and {i(p, 'height')}. What is its volume?"
            ),
            answer=lambda p: i(p, "length") * i(p, "width") * i(p, "height"),
            verify=lambda p, a: int(a) == i(p, "length") * i(p, "width") * i(p, "height"),
        ),
        Template(
            name="coordinate_distance_squared",
            category="geometry",
            difficulty="medium",
            sample=lambda rng: param_copy(
                x1=rng.randint(-10, 10),
                y1=rng.randint(-10, 10),
                x2=rng.randint(-10, 10),
                y2=rng.randint(-10, 10),
            ),
            render=lambda p: finish(
                f"Points A({i(p, 'x1')}, {i(p, 'y1')}) and B({i(p, 'x2')}, {i(p, 'y2')}) "
                "are in the coordinate plane. What is the squared distance AB^2?"
            ),
            answer=lambda p: (i(p, "x2") - i(p, "x1")) ** 2
            + (i(p, "y2") - i(p, "y1")) ** 2,
            verify=_verify_distance_squared,
        ),
        Template(
            name="similar_triangle_side",
            category="geometry",
            difficulty="medium",
            sample=lambda rng: param_copy(
                small_a=rng.randint(3, 16),
                large_a=rng.randint(8, 40),
                small_b=rng.randint(3, 18),
            ),
            render=lambda p: finish(
                f"Two triangles are similar. A side of length {i(p, 'small_a')} "
                f"corresponds to a side of length {i(p, 'large_a')}. "
                f"What length corresponds to a side of length {i(p, 'small_b')}?",
                fraction=True,
            ),
            answer=lambda p: frac(i(p, "large_a") * i(p, "small_b"), i(p, "small_a")),
            verify=_verify_similar_triangle,
        ),
        Template(
            name="pythagorean_missing_leg",
            category="geometry",
            difficulty="hard",
            sample=_sample_pythagorean,
            render=lambda p: finish(
                f"A right triangle has hypotenuse {i(p, 'hypotenuse')} and one leg "
                f"{i(p, 'leg')}. What is the length of the other leg?"
            ),
            answer=lambda p: i(p, "missing"),
            verify=lambda p, a: int(a) ** 2 + i(p, "leg") ** 2 == i(p, "hypotenuse") ** 2,
        ),
        Template(
            name="composite_cutout_area",
            category="geometry",
            difficulty="hard",
            sample=lambda rng: param_copy(
                outer_l=rng.randint(14, 40),
                outer_w=rng.randint(12, 35),
                cut_l=rng.randint(3, 12),
                cut_w=rng.randint(3, 10),
            ),
            render=lambda p: finish(
                f"A {i(p, 'outer_l')} by {i(p, 'outer_w')} rectangle has a "
                f"{i(p, 'cut_l')} by {i(p, 'cut_w')} rectangular corner removed. "
                "What area remains?"
            ),
            answer=lambda p: i(p, "outer_l") * i(p, "outer_w")
            - i(p, "cut_l") * i(p, "cut_w"),
            verify=lambda p, a: int(a)
            == i(p, "outer_l") * i(p, "outer_w") - i(p, "cut_l") * i(p, "cut_w"),
        ),
    ]


def _sample_pythagorean(rng) -> dict[str, int]:
    triples = ((3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25))
    leg_a, leg_b, hypotenuse = triples[rng.randrange(len(triples))]
    scale = rng.randint(1, 8)
    if rng.randrange(2) == 0:
        return param_copy(leg=leg_a * scale, missing=leg_b * scale, hypotenuse=hypotenuse * scale)
    return param_copy(leg=leg_b * scale, missing=leg_a * scale, hypotenuse=hypotenuse * scale)


def _verify_trapezoid(params: ParamMap, answer: Answer) -> bool:
    return Fraction(answer) == Fraction(
        (i(params, "base_a") + i(params, "base_b")) * i(params, "height"), 2
    )


def _verify_distance_squared(params: ParamMap, answer: Answer) -> bool:
    dx = i(params, "x2") - i(params, "x1")
    dy = i(params, "y2") - i(params, "y1")
    return int(answer) == dx * dx + dy * dy


def _verify_similar_triangle(params: ParamMap, answer: Answer) -> bool:
    return Fraction(answer) == Fraction(i(params, "large_a") * i(params, "small_b"), i(params, "small_a"))
