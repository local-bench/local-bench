"""Canonical capability-axis registry.

This is the single source of truth for normal-run axis membership, composite
weights, web keys, and roles.

Per METHODOLOGY-v2.1, the headline Local Intelligence Index is modular and
weighted as:

- Agentic: 0.50
- Knowledge: 0.15
- Instruction-Following: 0.15
- Tool-calling: 0.10
- Coding: 0.10

Math and Long-Context remain candidate axes. The normal-run Coding axis is the
lightweight, exec-free LiveCodeBench output-prediction proxy (`lcb`) so standard
runs stay practical. BigCodeBench-Hard remains the heavier opt-in coding-exec
module and is tracked in benchmark module metadata, not pooled into this static
axis until its execution lane is hardened.

Everything downstream derives from `AXES`:
- `localbench.scoring.metadata` builds `BENCH_DOMAINS` + `DOMAIN_WEIGHTS`.
- `web/build_data_axes.py` imports web composite weights + bench groups.
- `localbench.scoring.scorecard` hashes the registry into `scorecard_id`.
- `suite/*/suite.json` carries no independent weight numbers.

To re-weight or promote an axis, edit this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

AxisRole = Literal["headline", "candidate", "experimental"]


@dataclass(frozen=True, slots=True)
class Axis:
    key: str
    display: str
    web_key: str
    benches: tuple[str, ...]
    legacy_benches: tuple[str, ...]
    role: AxisRole
    weight: float
    web_display: bool


AXES: Final[tuple[Axis, ...]] = (
    Axis(
        "knowledge",
        "Knowledge",
        "knowledge",
        ("mmlu_pro",),
        ("supergpqa",),
        "headline",
        0.15,
        True,
    ),
    Axis(
        "instruction_following",
        "Instruction-Following",
        "instruction",
        ("ifbench",),
        ("ifeval",),
        "headline",
        0.15,
        True,
    ),
    Axis(
        "math",
        "Math",
        "math",
        ("olymmath_hard", "amo"),
        ("genmath",),
        "candidate",
        0.0,
        True,
    ),
    Axis(
        "long_context",
        "Long-Context",
        "long_context",
        ("ruler_32k",),
        (),
        "candidate",
        0.0,
        False,
    ),
    Axis(
        "agentic",
        "Agentic",
        "agentic",
        ("appworld_c",),
        (),
        "headline",
        0.50,
        True,
    ),
    Axis(
        "tool_calling",
        "Tool-calling",
        "tool_calling",
        ("tc_json_v1",),
        (),
        "headline",
        0.10,
        True,
    ),
    Axis(
        "coding",
        "Coding",
        "coding",
        ("lcb",),
        (),
        "headline",
        0.10,
        True,
    ),
)
STATIC_SUITE_INDEX_VERSION: Final = "static-suite-v1"
STATIC_SUITE_WEIGHTS: Final[dict[str, float]] = {
    "knowledge": 0.30,
    "instruction_following": 0.30,
    "tool_calling": 0.20,
    "coding": 0.20,
}


def bench_domains() -> dict[str, str]:
    return {
        bench: axis.display
        for axis in AXES
        for bench in (*axis.benches, *axis.legacy_benches)
    }


def domain_weights() -> dict[str, float]:
    return {axis.display: axis.weight for axis in AXES}


def headline_displays() -> tuple[str, ...]:
    return tuple(axis.display for axis in AXES if axis.role == "headline")


def headline_web_axes() -> tuple[str, ...]:
    return tuple(axis.web_key for axis in AXES if axis.role == "headline" and axis.web_display)


def axis_membership() -> dict[str, tuple[str, ...]]:
    return {axis.key: axis.benches for axis in AXES}


def web_display_axes() -> tuple[str, ...]:
    return tuple(axis.web_key for axis in AXES if axis.web_display)


def web_composite_weights() -> dict[str, float]:
    return {axis.web_key: axis.weight for axis in AXES if axis.web_display}


def static_suite_domain_weights() -> dict[str, float]:
    return {
        axis.display: STATIC_SUITE_WEIGHTS[axis.key]
        for axis in AXES
        if axis.key in STATIC_SUITE_WEIGHTS
    }


def static_suite_web_weights() -> dict[str, float]:
    return {
        axis.web_key: STATIC_SUITE_WEIGHTS[axis.key]
        for axis in AXES
        if axis.key in STATIC_SUITE_WEIGHTS
    }


def web_source_bench_groups() -> dict[str, tuple[tuple[str, ...], ...]]:
    groups: dict[str, tuple[tuple[str, ...], ...]] = {}
    for axis in AXES:
        if not axis.web_display:
            continue
        ordered = [axis.benches]
        if axis.legacy_benches:
            ordered.append(axis.legacy_benches)
        groups[axis.web_key] = tuple(ordered)
    return groups


def _validate() -> None:
    headline = [axis for axis in AXES if axis.role == "headline"]
    headline_weight = sum(axis.weight for axis in headline)
    if abs(headline_weight - 1.0) > 1e-9:
        raise ValueError(f"headline axis weights must sum to 1.0, got {headline_weight}")
    if any(axis.role != "headline" and axis.weight != 0.0 for axis in AXES):
        raise ValueError("only headline axes may carry a non-zero composite weight")
    benches = [bench for axis in AXES for bench in (*axis.benches, *axis.legacy_benches)]
    if len(benches) != len(set(benches)):
        raise ValueError("a bench is mapped to more than one axis")
    headline_keys = {axis.key for axis in headline}
    if not set(STATIC_SUITE_WEIGHTS) <= headline_keys:
        raise ValueError("static suite weights must reference headline axes")
    static_weight = sum(STATIC_SUITE_WEIGHTS.values())
    if abs(static_weight - 1.0) > 1e-9:
        raise ValueError(f"static suite weights must sum to 1.0, got {static_weight}")


_validate()
