"""Utility helpers for generated-math templates."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from math import comb, gcd
from random import Random

from genmath_gen.models import ParamMap, ParamValue

END_NUMBER = "Give your final answer as a single number."
END_FRACTION = "Give your final answer as a single number or fraction."

NAMES: tuple[str, ...] = (
    "Avery",
    "Blair",
    "Casey",
    "Devon",
    "Emery",
    "Finley",
    "Harper",
    "Jordan",
    "Morgan",
    "Quinn",
    "Riley",
    "Taylor",
)
OBJECTS: tuple[str, ...] = (
    "notebooks",
    "trail markers",
    "sample jars",
    "circuit boards",
    "seed packets",
    "clay tiles",
    "poster prints",
    "sensor kits",
)
PLACES: tuple[str, ...] = (
    "community lab",
    "robotics club",
    "garden co-op",
    "art studio",
    "field station",
    "maker space",
)


def finish(statement: str, *, fraction: bool = False) -> str:
    """Append the required answer-format instruction."""
    return f"{statement} {END_FRACTION if fraction else END_NUMBER}"


def pick(rng: Random, values: Sequence[str]) -> str:
    """Choose a deterministic wording variant."""
    return values[rng.randrange(len(values))]


def i(params: ParamMap, key: str) -> int:
    """Read an integer parameter."""
    return int(params[key])


def s(params: ParamMap, key: str) -> str:
    """Read a string parameter."""
    return str(params[key])


def frac(numerator: int, denominator: int) -> Fraction:
    """Create a reduced exact fraction."""
    return Fraction(numerator, denominator)


def lcm(left: int, right: int) -> int:
    """Return the least common multiple of two positive integers."""
    return left * right // gcd(left, right)


def permutations(total: int, chosen: int) -> int:
    """Return ordered selections without replacement."""
    result = 1
    for value in range(total - chosen + 1, total + 1):
        result *= value
    return result


def stars_and_bars(total: int, boxes: int) -> int:
    """Return nonnegative integer solutions to x_1 + ... + x_boxes = total."""
    return comb(total + boxes - 1, boxes - 1)


def param_copy(**kwargs: ParamValue) -> dict[str, ParamValue]:
    """Build a JSON-serializable parameter dict."""
    return dict(kwargs)
