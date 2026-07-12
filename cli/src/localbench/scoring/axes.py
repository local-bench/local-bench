"""Canonical capability-axis registry.

This is the single source of truth for normal-run axis membership, composite
weights, web keys, and roles.

Season 2 uses five weighted headline axes. Tool Use is a bench-normalized
macro-axis whose declared facet weights are independent of item counts.

Coding is BigCodeBench-Hard Instruct generation with verifier-side execution.
LiveCodeBench (`lcb`) remains a legacy diagnostic bench and is not pooled into
the v3 headline coding axis. Long-Context remains candidate-only.

Everything downstream derives from `AXES`:
- `localbench.scoring.metadata` builds `BENCH_DOMAINS` + `DOMAIN_WEIGHTS`.
- `web/build_data_axes.py` imports web composite weights + bench groups.
- `localbench.scoring.scorecard` hashes the registry into `scorecard_id`.
- `suite/*/suite.json` carries no independent weight numbers.

To re-weight or promote an axis, edit this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Final, Literal, TypeVar

AxisRole = Literal["headline", "candidate", "experimental"]
SampleT = TypeVar("SampleT")


@dataclass(frozen=True, slots=True)
class FacetSpec:
    key: str
    bench: str
    weight: float


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
    facets: tuple[FacetSpec, ...] = ()


AXES: Final[tuple[Axis, ...]] = (
    Axis(
        "knowledge",
        "Knowledge",
        "knowledge",
        ("mmlu_pro",),
        ("supergpqa",),
        "headline",
        0.24,
        True,
    ),
    Axis(
        "instruction_following",
        "Instruction-Following",
        "instruction",
        ("ifbench",),
        ("ifeval",),
        "headline",
        0.24,
        True,
    ),
    Axis(
        "math",
        "Math",
        "math",
        ("olymmath_hard", "amo"),
        ("genmath",),
        "headline",
        0.08,
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
        "tool_use",
        "Tool Use",
        "tool_use",
        ("appworld_c", "bfcl_multi_turn_base", "tc_json_v1"),
        (),
        "headline",
        0.20,
        True,
        (
            FacetSpec("agentic", "appworld_c", 0.50),
            FacetSpec("multi_turn_tool_control", "bfcl_multi_turn_base", 0.35),
            FacetSpec("call_formatting", "tc_json_v1", 0.15),
        ),
    ),
    Axis(
        "coding",
        "Coding",
        "coding",
        ("bigcodebench_hard",),
        ("lcb",),
        "headline",
        0.24,
        True,
    ),
    Axis(
        "bfcl_single_turn",
        "BFCL Single-Turn",
        "bfcl_single_turn",
        ("bfcl",),
        (),
        "experimental",
        0.0,
        False,
    ),
    Axis(
        "bfcl_multi_turn_long_context",
        "BFCL Multi-Turn Long-Context",
        "bfcl_multi_turn_long_context",
        ("bfcl_multi_turn_long_context",),
        (),
        "experimental",
        0.0,
        False,
    ),
)
STATIC_SUITE_INDEX_VERSION: Final = "static-suite-v2"
STATIC_SUITE_WEIGHTS: Final[dict[str, float]] = {
    "knowledge": 0.25,
    "instruction_following": 0.25,
    "tool_calling": 0.20,
    "coding": 0.20,
    "math": 0.10,
}
STATIC_SUITE_V3_INDEX_VERSION: Final = "static-suite-v3"
STATIC_SUITE_V3_WEIGHTS: Final[dict[str, float]] = {
    "knowledge": 0.30,
    "instruction_following": 0.30,
    "coding": 0.30,
    "math": 0.10,
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


def agentic_benches() -> frozenset[str]:
    """Benches on the agentic axis — multi-turn tasks with no single per-item token
    budget (each turn is bounded separately). They are excluded from the per-item
    token-budget audit, which only applies to single-generation benches."""
    return frozenset(
        facet.bench
        for axis in AXES
        for facet in axis.facets
        if facet.key == "agentic"
    )


def axis_for_key(key: str) -> Axis | None:
    return next((axis for axis in AXES if axis.key == key), None)


def axis_for_web_key(web_key: str) -> Axis | None:
    return next((axis for axis in AXES if axis.web_key == web_key), None)


def materialize_facet_samples(
    axis: Axis,
    samples: Mapping[str, SampleT],
) -> tuple[dict[str, SampleT], dict[str, float]] | None:
    """Return complete whole-bench facet samples and their declared weights.

    Faceted axes are fail-closed: a partial set is not a macro-axis sample.
    """
    if not axis.facets or any(facet.bench not in samples for facet in axis.facets):
        return None
    return (
        {facet.bench: samples[facet.bench] for facet in axis.facets},
        {facet.bench: facet.weight for facet in axis.facets},
    )


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


def static_suite_v3_domain_weights() -> dict[str, float]:
    return {
        axis.display: STATIC_SUITE_V3_WEIGHTS[axis.key]
        for axis in AXES
        if axis.key in STATIC_SUITE_V3_WEIGHTS
    }


def static_suite_v3_web_weights() -> dict[str, float]:
    return {
        axis.web_key: STATIC_SUITE_V3_WEIGHTS[axis.key]
        for axis in AXES
        if axis.key in STATIC_SUITE_V3_WEIGHTS
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
    for axis in AXES:
        if not axis.facets:
            continue
        facet_keys = [facet.key for facet in axis.facets]
        if len(facet_keys) != len(set(facet_keys)):
            raise ValueError(f"facet keys must be unique within axis {axis.key}")
        if any(facet.weight <= 0.0 for facet in axis.facets):
            raise ValueError(f"facet weights must be positive within axis {axis.key}")
        facet_weight = sum(facet.weight for facet in axis.facets)
        if abs(facet_weight - 1.0) > 1e-9:
            raise ValueError(f"facet weights must sum to 1.0 within axis {axis.key}, got {facet_weight}")
        if any(facet.bench not in axis.benches for facet in axis.facets):
            raise ValueError(f"facet benches must belong to axis {axis.key}")
    benches = [bench for axis in AXES for bench in (*axis.benches, *axis.legacy_benches)]
    if len(benches) != len(set(benches)):
        raise ValueError("a bench is mapped to more than one axis")
    headline_keys = {axis.key for axis in headline}
    if not set(STATIC_SUITE_V3_WEIGHTS) <= headline_keys:
        raise ValueError("static suite weights must reference headline axes")
    static_weight = sum(STATIC_SUITE_V3_WEIGHTS.values())
    if abs(static_weight - 1.0) > 1e-9:
        raise ValueError(f"static suite weights must sum to 1.0, got {static_weight}")


_validate()
