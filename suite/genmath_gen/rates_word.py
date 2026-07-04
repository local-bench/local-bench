"""Rate and work word-problem templates."""

from __future__ import annotations

from fractions import Fraction
from random import Random

from genmath_gen.models import Params, Template
from genmath_gen.utils import NAMES, OBJECTS, PLACES, finish, frac, i, param_copy, pick, s


def templates() -> list[Template]:
    """Return rates-word templates."""
    return [
        Template(
            name="constant_speed_distance",
            category="rates_word",
            difficulty="easy",
            sample=_sample_constant_speed,
            render=lambda p: finish(
                f"{s(p, 'name')} rides from the {s(p, 'place')} at {i(p, 'speed')} "
                f"miles per hour for {i(p, 'hours')} hours. How many miles are covered?"
            ),
            answer=lambda p: i(p, "speed") * i(p, "hours"),
        ),
        Template(
            name="unit_rate_total_cost",
            category="rates_word",
            difficulty="easy",
            sample=_sample_unit_rate,
            render=lambda p: finish(
                f"{s(p, 'name')} buys {i(p, 'count')} {s(p, 'object')} for a total "
                f"of {i(p, 'total')} dollars. What is the cost of one item?"
            ),
            answer=lambda p: i(p, "total") // i(p, "count"),
        ),
        Template(
            name="shared_work_time",
            category="rates_word",
            difficulty="medium",
            sample=_sample_shared_work,
            render=lambda p: finish(
                f"{s(p, 'first')} can label a batch of {s(p, 'object')} in {i(p, 'a')} "
                f"hours. {s(p, 'second')} can label the same batch in {i(p, 'b')} hours. "
                "Working together, how many hours will they take?",
                fraction=True,
            ),
            answer=lambda p: frac(i(p, "a") * i(p, "b"), i(p, "a") + i(p, "b")),
        ),
        Template(
            name="opposite_directions_meet",
            category="rates_word",
            difficulty="medium",
            sample=_sample_opposite_meet,
            render=lambda p: finish(
                f"{s(p, 'first')} and {s(p, 'second')} start {i(p, 'distance')} miles "
                f"apart and walk toward each other at {i(p, 'speed_a')} and {i(p, 'speed_b')} "
                "miles per hour. How many hours until they meet?",
                fraction=True,
            ),
            answer=lambda p: frac(i(p, "distance"), i(p, "speed_a") + i(p, "speed_b")),
        ),
        Template(
            name="two_stage_production",
            category="rates_word",
            difficulty="medium",
            sample=_sample_two_stage_production,
            render=lambda p: finish(
                f"At the {s(p, 'place')}, a cutter makes {i(p, 'rate_a')} {s(p, 'object')} "
                f"per hour for {i(p, 'hours_a')} hours, then {i(p, 'rate_b')} per hour "
                f"for {i(p, 'hours_b')} hours. How many are made?"
            ),
            answer=lambda p: i(p, "rate_a") * i(p, "hours_a")
            + i(p, "rate_b") * i(p, "hours_b"),
        ),
        Template(
            name="fill_with_leak_time",
            category="rates_word",
            difficulty="hard",
            sample=_sample_fill_leak,
            render=lambda p: finish(
                f"A pump can fill a tank in {i(p, 'fill')} hours, while a leak can drain "
                f"a full tank in {i(p, 'drain')} hours. If both are active from empty, "
                "how many hours does filling take?",
                fraction=True,
            ),
            answer=lambda p: frac(i(p, "fill") * i(p, "drain"), i(p, "drain") - i(p, "fill")),
        ),
        Template(
            name="round_trip_average_speed",
            category="rates_word",
            difficulty="hard",
            sample=_sample_round_trip,
            render=lambda p: finish(
                f"{s(p, 'name')} travels {i(p, 'distance')} miles out at {i(p, 'out_speed')} "
                f"miles per hour and returns the same distance at {i(p, 'back_speed')} "
                "miles per hour. What is the average speed for the whole trip?",
                fraction=True,
            ),
            answer=lambda p: frac(2 * i(p, "out_speed") * i(p, "back_speed"), i(p, "out_speed") + i(p, "back_speed")),
        ),
        Template(
            name="catch_up_after_head_start",
            category="rates_word",
            difficulty="hard",
            sample=_sample_catch_up,
            render=lambda p: finish(
                f"{s(p, 'first')} leaves the {s(p, 'place')} at {i(p, 'slow_speed')} "
                f"miles per hour. {i(p, 'head_start')} hours later, {s(p, 'second')} "
                f"leaves from the same place at {i(p, 'fast_speed')} miles per hour. "
                f"How many hours after {s(p, 'second')} starts will it take to catch up?",
                fraction=True,
            ),
            answer=lambda p: frac(
                i(p, "slow_speed") * i(p, "head_start"),
                i(p, "fast_speed") - i(p, "slow_speed"),
            ),
        ),
    ]


def _two_names(rng: Random) -> tuple[str, str]:
    first, second = rng.sample(NAMES, 2)
    return first, second


def _sample_constant_speed(rng: Random) -> Params:
    return param_copy(
        name=pick(rng, NAMES),
        place=pick(rng, PLACES),
        speed=rng.randint(8, 55),
        hours=rng.randint(2, 8),
    )


def _sample_unit_rate(rng: Random) -> Params:
    count = rng.randint(3, 12)
    price = rng.randint(4, 25)
    return param_copy(name=pick(rng, NAMES), object=pick(rng, OBJECTS), count=count, total=count * price)


def _sample_shared_work(rng: Random) -> Params:
    first, second = _two_names(rng)
    return param_copy(
        first=first,
        second=second,
        object=pick(rng, OBJECTS),
        a=rng.randint(3, 12),
        b=rng.randint(4, 14),
    )


def _sample_opposite_meet(rng: Random) -> Params:
    first, second = _two_names(rng)
    speed_a = rng.randint(3, 8)
    speed_b = rng.randint(3, 8)
    distance = rng.randint(5, 30) * (speed_a + speed_b)
    return param_copy(first=first, second=second, distance=distance, speed_a=speed_a, speed_b=speed_b)


def _sample_two_stage_production(rng: Random) -> Params:
    return param_copy(
        place=pick(rng, PLACES),
        object=pick(rng, OBJECTS),
        rate_a=rng.randint(8, 35),
        hours_a=rng.randint(2, 6),
        rate_b=rng.randint(8, 35),
        hours_b=rng.randint(2, 6),
    )


def _sample_fill_leak(rng: Random) -> Params:
    fill = rng.randint(3, 12)
    drain = fill + rng.randint(2, 14)
    return param_copy(fill=fill, drain=drain)


def _sample_round_trip(rng: Random) -> Params:
    return param_copy(
        name=pick(rng, NAMES),
        distance=rng.randint(10, 80),
        out_speed=rng.randint(20, 55),
        back_speed=rng.randint(20, 55),
    )


def _sample_catch_up(rng: Random) -> Params:
    first, second = _two_names(rng)
    slow = rng.randint(3, 8)
    fast = slow + rng.randint(2, 8)
    return param_copy(
        first=first,
        second=second,
        place=pick(rng, PLACES),
        slow_speed=slow,
        fast_speed=fast,
        head_start=rng.randint(1, 5),
    )
