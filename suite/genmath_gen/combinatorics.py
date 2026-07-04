"""Combinatorics templates with brute-force checkers."""

from __future__ import annotations

from itertools import combinations, pairwise, permutations, product
from math import comb, factorial
from random import Random

from genmath_gen.models import ParamMap, Params, Template
from genmath_gen.utils import finish, i, param_copy, permutations as n_perm, stars_and_bars


def templates() -> list[Template]:
    """Return combinatorics templates."""
    return [
        Template(
            name="topping_choices",
            category="combinatorics",
            difficulty="easy",
            sample=lambda rng: param_copy(n=rng.randint(6, 10), k=rng.randint(2, 4)),
            render=lambda p: finish(
                f"A menu has {i(p, 'n')} toppings. How many ways are there to choose "
                f"{i(p, 'k')} different toppings?"
            ),
            answer=lambda p: comb(i(p, "n"), i(p, "k")),
            brute_force=lambda p: sum(1 for _ in combinations(range(i(p, "n")), i(p, "k"))),
        ),
        Template(
            name="committee_with_chair",
            category="combinatorics",
            difficulty="easy",
            sample=lambda rng: param_copy(n=rng.randint(6, 10), r=rng.randint(2, 5)),
            render=lambda p: finish(
                f"From {i(p, 'n')} students, choose a committee of {i(p, 'r')} and "
                "then choose one committee member as chair. How many outcomes are possible?"
            ),
            answer=lambda p: comb(i(p, "n"), i(p, "r")) * i(p, "r"),
            brute_force=_brute_committee_chair,
        ),
        Template(
            name="license_codes_no_repeat",
            category="combinatorics",
            difficulty="easy",
            sample=lambda rng: param_copy(n=rng.randint(5, 8), k=rng.randint(2, 4)),
            render=lambda p: finish(
                f"A code uses {i(p, 'k')} distinct letters chosen from {i(p, 'n')} "
                "available letters, and order matters. How many codes are possible?"
            ),
            answer=lambda p: n_perm(i(p, "n"), i(p, "k")),
            brute_force=lambda p: sum(1 for _ in permutations(range(i(p, "n")), i(p, "k"))),
        ),
        Template(
            name="arrange_repeated_letters",
            category="combinatorics",
            difficulty="medium",
            sample=_sample_repeated_letters,
            render=lambda p: finish(
                f"How many distinct arrangements can be made from {i(p, 'a')} A letters, "
                f"{i(p, 'b')} B letters, and {i(p, 'c')} C letters?"
            ),
            answer=lambda p: factorial(i(p, "a") + i(p, "b") + i(p, "c"))
            // (factorial(i(p, "a")) * factorial(i(p, "b")) * factorial(i(p, "c"))),
            brute_force=_brute_repeated_letters,
        ),
        Template(
            name="grid_paths_via_checkpoint",
            category="combinatorics",
            difficulty="medium",
            sample=_sample_grid_checkpoint,
            render=lambda p: finish(
                f"On a grid, move only right or up from (0, 0) to ({i(p, 'a')}, {i(p, 'b')}). "
                f"How many paths pass through ({i(p, 'x')}, {i(p, 'y')})?"
            ),
            answer=lambda p: comb(i(p, "x") + i(p, "y"), i(p, "x"))
            * comb(i(p, "a") - i(p, "x") + i(p, "b") - i(p, "y"), i(p, "a") - i(p, "x")),
            brute_force=_brute_grid_checkpoint,
        ),
        Template(
            name="distribute_with_minimum",
            category="combinatorics",
            difficulty="medium",
            sample=_sample_distribution_minimum,
            render=lambda p: finish(
                f"How many ways can {i(p, 'total')} identical tokens be placed into "
                f"{i(p, 'boxes')} labeled boxes if each box gets at least {i(p, 'minimum')}?"
            ),
            answer=lambda p: stars_and_bars(
                i(p, "total") - i(p, "boxes") * i(p, "minimum"), i(p, "boxes")
            ),
            brute_force=_brute_distribution_minimum,
        ),
        Template(
            name="nonadjacent_selections",
            category="combinatorics",
            difficulty="medium",
            sample=lambda rng: param_copy(n=rng.randint(6, 11), k=rng.randint(2, 4)),
            render=lambda p: finish(
                f"From positions 1 through {i(p, 'n')}, how many ways can {i(p, 'k')} "
                "positions be chosen with no two chosen positions adjacent?"
            ),
            answer=lambda p: comb(i(p, "n") - i(p, "k") + 1, i(p, "k")),
            brute_force=_brute_nonadjacent,
        ),
        Template(
            name="strings_containing_a_and_b",
            category="combinatorics",
            difficulty="hard",
            sample=lambda rng: param_copy(n=rng.randint(4, 7)),
            render=lambda p: finish(
                f"How many strings of length {i(p, 'n')} over the alphabet A, B, C "
                "contain at least one A and at least one B?"
            ),
            answer=lambda p: 3 ** i(p, "n") - 2 * 2 ** i(p, "n") + 1,
            brute_force=_brute_strings_containing_a_and_b,
        ),
        Template(
            name="onto_functions_small",
            category="combinatorics",
            difficulty="hard",
            sample=lambda rng: param_copy(n=rng.randint(4, 6), k=rng.randint(2, 4)),
            render=lambda p: finish(
                f"How many functions from a {i(p, 'n')}-element set onto a "
                f"{i(p, 'k')}-element set are there?"
            ),
            answer=_onto_answer,
            brute_force=_brute_onto,
        ),
    ]


def _sample_repeated_letters(rng: Random) -> Params:
    a = rng.randint(1, 3)
    b = rng.randint(1, 3)
    c = rng.randint(1, 2)
    return param_copy(a=a, b=b, c=c)


def _sample_grid_checkpoint(rng: Random) -> Params:
    a = rng.randint(3, 6)
    b = rng.randint(3, 6)
    return param_copy(a=a, b=b, x=rng.randint(1, a - 1), y=rng.randint(1, b - 1))


def _sample_distribution_minimum(rng: Random) -> Params:
    boxes = rng.randint(3, 5)
    minimum = rng.randint(1, 3)
    extra = rng.randint(2, 7)
    return param_copy(total=boxes * minimum + extra, boxes=boxes, minimum=minimum)


def _brute_committee_chair(params: ParamMap) -> int:
    return sum(len(group) for group in combinations(range(i(params, "n")), i(params, "r")))


def _brute_repeated_letters(params: ParamMap) -> int:
    letters = "A" * i(params, "a") + "B" * i(params, "b") + "C" * i(params, "c")
    return len(set(permutations(letters, len(letters))))


def _brute_grid_checkpoint(params: ParamMap) -> int:
    count = 0
    a = i(params, "a")
    b = i(params, "b")
    checkpoint = (i(params, "x"), i(params, "y"))
    for right_positions in combinations(range(a + b), a):
        position = [0, 0]
        seen = False
        rights = set(right_positions)
        for step in range(a + b):
            if step in rights:
                position[0] += 1
            else:
                position[1] += 1
            seen = seen or tuple(position) == checkpoint
        count += int(seen)
    return count


def _brute_distribution_minimum(params: ParamMap) -> int:
    total = i(params, "total")
    boxes = i(params, "boxes")
    minimum = i(params, "minimum")
    return _count_allocations(total, boxes, minimum)


def _brute_nonadjacent(params: ParamMap) -> int:
    return sum(
        1
        for chosen in combinations(range(i(params, "n")), i(params, "k"))
        if all(right - left > 1 for left, right in pairwise(chosen))
    )


def _brute_strings_containing_a_and_b(params: ParamMap) -> int:
    return sum(
        1
        for word in product("ABC", repeat=i(params, "n"))
        if "A" in word and "B" in word
    )


def _onto_answer(params: ParamMap) -> int:
    n = i(params, "n")
    k = i(params, "k")
    return sum((-1) ** excluded * comb(k, excluded) * (k - excluded) ** n for excluded in range(k + 1))


def _brute_onto(params: ParamMap) -> int:
    k = i(params, "k")
    return sum(1 for outputs in product(range(k), repeat=i(params, "n")) if len(set(outputs)) == k)


def _count_allocations(total: int, boxes: int, minimum: int) -> int:
    if boxes == 1:
        return int(total >= minimum)
    count = 0
    for first in range(minimum, total + 1):
        count += _count_allocations(total - first, boxes - 1, minimum)
    return count
