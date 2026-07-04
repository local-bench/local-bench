"""Probability templates with brute-force checkers."""

from __future__ import annotations

from itertools import combinations, pairwise, permutations, product

from genmath_gen.models import ParamMap, Template
from genmath_gen.utils import finish, frac, i, param_copy


def templates() -> list[Template]:
    """Return probability templates."""
    return [
        Template(
            name="single_die_at_least",
            category="probability",
            difficulty="easy",
            sample=lambda rng: param_copy(target=rng.randint(2, 6)),
            render=lambda p: finish(
                f"A fair six-sided die is rolled once. What is the probability of rolling "
                f"at least {i(p, 'target')}?",
                fraction=True,
            ),
            answer=lambda p: frac(7 - i(p, "target"), 6),
            brute_force=_brute_single_die_at_least,
        ),
        Template(
            name="one_marble_color",
            category="probability",
            difficulty="easy",
            sample=lambda rng: param_copy(
                red=rng.randint(2, 8), blue=rng.randint(2, 8), green=rng.randint(1, 5)
            ),
            render=lambda p: finish(
                f"A bag has {i(p, 'red')} red, {i(p, 'blue')} blue, and {i(p, 'green')} "
                "green marbles. One marble is drawn. What is the probability it is red?",
                fraction=True,
            ),
            answer=lambda p: frac(i(p, "red"), i(p, "red") + i(p, "blue") + i(p, "green")),
            brute_force=_brute_one_marble_color,
        ),
        Template(
            name="two_dice_sum",
            category="probability",
            difficulty="medium",
            sample=lambda rng: param_copy(target=rng.randint(4, 10)),
            render=lambda p: finish(
                f"Two fair six-sided dice are rolled. What is the probability that their "
                f"sum is {i(p, 'target')}?",
                fraction=True,
            ),
            answer=lambda p: frac(
                sum(1 for a in range(1, 7) for b in range(1, 7) if a + b == i(p, "target")),
                36,
            ),
            brute_force=_brute_two_dice_sum,
        ),
        Template(
            name="coin_exact_heads",
            category="probability",
            difficulty="medium",
            sample=lambda rng: param_copy(n=rng.randint(4, 8), k=rng.randint(1, 3)),
            render=lambda p: finish(
                f"A fair coin is flipped {i(p, 'n')} times. What is the probability of "
                f"getting exactly {i(p, 'k')} heads?",
                fraction=True,
            ),
            answer=lambda p: frac(
                sum(1 for flips in product((0, 1), repeat=i(p, "n")) if sum(flips) == i(p, "k")),
                2 ** i(p, "n"),
            ),
            brute_force=_brute_coin_exact_heads,
        ),
        Template(
            name="same_color_two_draws",
            category="probability",
            difficulty="medium",
            sample=lambda rng: param_copy(red=rng.randint(3, 9), blue=rng.randint(3, 9)),
            render=lambda p: finish(
                f"A bag has {i(p, 'red')} red and {i(p, 'blue')} blue marbles. "
                "Two marbles are drawn without replacement. What is the probability "
                "they are the same color?",
                fraction=True,
            ),
            answer=lambda p: frac(
                _choose2(i(p, "red")) + _choose2(i(p, "blue")),
                _choose2(i(p, "red") + i(p, "blue")),
            ),
            brute_force=_brute_same_color_two_draws,
        ),
        Template(
            name="ordered_red_then_blue",
            category="probability",
            difficulty="medium",
            sample=lambda rng: param_copy(
                red=rng.randint(2, 7), blue=rng.randint(2, 7), green=rng.randint(1, 5)
            ),
            render=lambda p: finish(
                f"A bag has {i(p, 'red')} red, {i(p, 'blue')} blue, and {i(p, 'green')} "
                "green marbles. Two marbles are drawn without replacement. What is "
                "the probability the first is red and the second is blue?",
                fraction=True,
            ),
            answer=lambda p: frac(
                i(p, "red") * i(p, "blue"),
                (i(p, "red") + i(p, "blue") + i(p, "green"))
                * (i(p, "red") + i(p, "blue") + i(p, "green") - 1),
            ),
            brute_force=_brute_ordered_red_then_blue,
        ),
        Template(
            name="at_least_one_six",
            category="probability",
            difficulty="hard",
            sample=lambda rng: param_copy(n=rng.randint(2, 3)),
            render=lambda p: finish(
                f"A fair six-sided die is rolled {i(p, 'n')} times. What is the "
                "probability that at least one roll is a 6?",
                fraction=True,
            ),
            answer=lambda p: frac(6 ** i(p, "n") - 5 ** i(p, "n"), 6 ** i(p, "n")),
            brute_force=_brute_at_least_one_six,
        ),
        Template(
            name="bitstring_no_adjacent_ones",
            category="probability",
            difficulty="hard",
            sample=lambda rng: param_copy(n=rng.randint(5, 9)),
            render=lambda p: finish(
                f"A binary string of length {i(p, 'n')} is chosen uniformly at random. "
                "What is the probability that it has no adjacent 1s?",
                fraction=True,
            ),
            answer=lambda p: frac(_count_no_adjacent_ones(i(p, "n")), 2 ** i(p, "n")),
            brute_force=_brute_bitstring_no_adjacent_ones,
        ),
    ]


def _choose2(value: int) -> int:
    return value * (value - 1) // 2


def _bag(params: ParamMap) -> list[str]:
    return ["R"] * i(params, "red") + ["B"] * i(params, "blue") + ["G"] * i(params, "green")


def _brute_single_die_at_least(params: ParamMap):
    wins = sum(1 for roll in range(1, 7) if roll >= i(params, "target"))
    return frac(wins, 6)


def _brute_one_marble_color(params: ParamMap):
    bag = _bag(params)
    return frac(sum(1 for marble in bag if marble == "R"), len(bag))


def _brute_two_dice_sum(params: ParamMap):
    outcomes = list(product(range(1, 7), repeat=2))
    return frac(sum(1 for a, b in outcomes if a + b == i(params, "target")), len(outcomes))


def _brute_coin_exact_heads(params: ParamMap):
    outcomes = list(product((0, 1), repeat=i(params, "n")))
    return frac(sum(1 for flips in outcomes if sum(flips) == i(params, "k")), len(outcomes))


def _brute_same_color_two_draws(params: ParamMap):
    bag = ["R"] * i(params, "red") + ["B"] * i(params, "blue")
    pairs = list(combinations(range(len(bag)), 2))
    wins = sum(1 for left, right in pairs if bag[left] == bag[right])
    return frac(wins, len(pairs))


def _brute_ordered_red_then_blue(params: ParamMap):
    bag = _bag(params)
    pairs = list(permutations(range(len(bag)), 2))
    wins = sum(1 for left, right in pairs if bag[left] == "R" and bag[right] == "B")
    return frac(wins, len(pairs))


def _brute_at_least_one_six(params: ParamMap):
    outcomes = list(product(range(1, 7), repeat=i(params, "n")))
    return frac(sum(1 for rolls in outcomes if 6 in rolls), len(outcomes))


def _count_no_adjacent_ones(length: int) -> int:
    return sum(
        1
        for bits in product((0, 1), repeat=length)
        if all(left + right < 2 for left, right in pairwise(bits))
    )


def _brute_bitstring_no_adjacent_ones(params: ParamMap):
    length = i(params, "n")
    return frac(_count_no_adjacent_ones(length), 2**length)
