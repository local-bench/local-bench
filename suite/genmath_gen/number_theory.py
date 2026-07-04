"""Number-theory templates."""

from __future__ import annotations

from math import gcd
from random import Random

from genmath_gen.models import Params, Template
from genmath_gen.utils import finish, i, lcm, param_copy

PRIMES: tuple[int, ...] = (2, 3, 5, 7, 11, 13)


def templates() -> list[Template]:
    """Return number-theory templates."""
    return [
        Template(
            name="gcd_pair",
            category="number_theory",
            difficulty="easy",
            sample=lambda rng: param_copy(a=rng.randint(24, 180), b=rng.randint(24, 180)),
            render=lambda p: finish(
                f"What is the greatest common divisor of {i(p, 'a')} and {i(p, 'b')}?"
            ),
            answer=lambda p: gcd(i(p, "a"), i(p, "b")),
        ),
        Template(
            name="lcm_pair",
            category="number_theory",
            difficulty="easy",
            sample=lambda rng: param_copy(a=rng.randint(6, 36), b=rng.randint(6, 36)),
            render=lambda p: finish(
                f"What is the least common multiple of {i(p, 'a')} and {i(p, 'b')}?"
            ),
            answer=lambda p: lcm(i(p, "a"), i(p, "b")),
        ),
        Template(
            name="count_multiples_interval",
            category="number_theory",
            difficulty="easy",
            sample=_sample_multiples,
            render=lambda p: finish(
                f"How many multiples of {i(p, 'm')} are between {i(p, 'lo')} "
                f"and {i(p, 'hi')}, inclusive?"
            ),
            answer=lambda p: i(p, "hi") // i(p, "m") - (i(p, "lo") - 1) // i(p, "m"),
        ),
        Template(
            name="linear_remainder",
            category="number_theory",
            difficulty="medium",
            sample=lambda rng: param_copy(
                a=rng.randint(3, 30),
                n=rng.randint(5, 40),
                b=rng.randint(2, 30),
                m=rng.randint(5, 31),
            ),
            render=lambda p: finish(
                f"What is the remainder when {i(p, 'a')} times {i(p, 'n')} "
                f"plus {i(p, 'b')} is divided by {i(p, 'm')}?"
            ),
            answer=lambda p: (i(p, "a") * i(p, "n") + i(p, "b")) % i(p, "m"),
        ),
        Template(
            name="least_shift_divisible",
            category="number_theory",
            difficulty="medium",
            sample=lambda rng: param_copy(a=rng.randint(4, 80), m=rng.randint(5, 35)),
            render=lambda p: finish(
                f"What is the smallest nonnegative integer x such that "
                f"{i(p, 'a')} + x is divisible by {i(p, 'm')}?"
            ),
            answer=lambda p: (-i(p, "a")) % i(p, "m"),
        ),
        Template(
            name="sum_divisors_two_prime_powers",
            category="number_theory",
            difficulty="medium",
            sample=_sample_two_prime_powers,
            render=lambda p: finish(
                f"Let n = {i(p, 'p')}^{i(p, 'a')} times {i(p, 'q')}^{i(p, 'b')}. "
                "What is the sum of all positive divisors of n?"
            ),
            answer=lambda p: _prime_power_sum(i(p, "p"), i(p, "a"))
            * _prime_power_sum(i(p, "q"), i(p, "b")),
        ),
        Template(
            name="count_divisors_factorization",
            category="number_theory",
            difficulty="medium",
            sample=_sample_three_exponents,
            render=lambda p: finish(
                f"If n has prime factorization 2^{i(p, 'a')} times 3^{i(p, 'b')} "
                f"times 5^{i(p, 'c')}, how many positive divisors does n have?"
            ),
            answer=lambda p: (i(p, "a") + 1) * (i(p, "b") + 1) * (i(p, "c") + 1),
        ),
        Template(
            name="phi_two_primes",
            category="number_theory",
            difficulty="hard",
            sample=_sample_two_distinct_primes,
            render=lambda p: finish(
                f"Let n = {i(p, 'p')} times {i(p, 'q')}, where both factors are prime. "
                "How many positive integers less than n are relatively prime to n?"
            ),
            answer=lambda p: (i(p, "p") - 1) * (i(p, "q") - 1),
        ),
        Template(
            name="chinese_remainder_pair",
            category="number_theory",
            difficulty="hard",
            sample=_sample_crt,
            render=lambda p: finish(
                f"What is the least nonnegative integer x such that x leaves remainder "
                f"{i(p, 'r1')} when divided by {i(p, 'm1')} and remainder {i(p, 'r2')} "
                f"when divided by {i(p, 'm2')}?"
            ),
            answer=lambda p: _crt_answer(i(p, "m1"), i(p, "r1"), i(p, "m2"), i(p, "r2")),
        ),
    ]


def _sample_multiples(rng: Random) -> Params:
    m = rng.randint(3, 18)
    lo = rng.randint(10, 80)
    hi = lo + rng.randint(40, 160)
    return param_copy(m=m, lo=lo, hi=hi)


def _sample_two_prime_powers(rng: Random) -> Params:
    p, q = rng.sample(PRIMES, 2)
    return param_copy(p=p, q=q, a=rng.randint(1, 3), b=rng.randint(1, 3))


def _sample_three_exponents(rng: Random) -> Params:
    return param_copy(a=rng.randint(1, 5), b=rng.randint(1, 4), c=rng.randint(1, 3))


def _sample_two_distinct_primes(rng: Random) -> Params:
    p, q = rng.sample(PRIMES[2:], 2)
    return param_copy(p=p, q=q)


def _sample_crt(rng: Random) -> Params:
    pairs = ((5, 7), (5, 9), (7, 8), (8, 9), (7, 11))
    m1, m2 = pairs[rng.randrange(len(pairs))]
    answer = rng.randint(0, m1 * m2 - 1)
    return param_copy(m1=m1, m2=m2, r1=answer % m1, r2=answer % m2)


def _prime_power_sum(prime: int, exponent: int) -> int:
    return sum(prime**power for power in range(exponent + 1))


def _crt_answer(m1: int, r1: int, m2: int, r2: int) -> int:
    for value in range(m1 * m2):
        if value % m1 == r1 and value % m2 == r2:
            return value
    raise ArithmeticError("sampled moduli were not coprime")
