"""Canonical capability-axis registry — the SINGLE source of truth for the JUDGE-FREE,
normal-run axes' membership, composite weights, and roles.

Per METHODOLOGY-v1.2 (`docs/foundations/methodology-lock/METHODOLOGY-v1.2-LOCKED.md`):
the headline composite is the equal-weight mean of the VALIDATED discriminating axes
(Knowledge + Instruction). Math + Long-Context are *candidates* (measured + displayed, not
yet weighted; promotable once they pass the discrimination gate). Agentic (BFCL) and the
STATIC Coding proxy (LiveCodeBench output-prediction, `lcb`) are *experimental*: judge-free
proxies for tool/code REASONING that are saturated/gameable — displayed, not promotable.

NOTE — the static `coding` axis here is NOT the credible code-GENERATION axis. That one
runs by EXECUTION (BigCodeBench-Hard via `localbench code`), is a *candidate* for the
headline once it passes discrimination, and lives in a SEPARATE opt-in exec LANE with its
own run schema — deliberately NOT in this judge-free registry (different command + schema).
See CODING-EXEC-MODULE-SPEC. So "experimental / not in the composite" describes the static
proxy; coding-exec's "candidate" status is its own lane's — the two are different axes, not
a contradiction.

Everything downstream DERIVES from `AXES`:
- `localbench.scoring.metadata` builds `BENCH_DOMAINS` + `DOMAIN_WEIGHTS` from it,
- `web/build_data_axes.py` imports its composite weights + bench groups,
- `localbench.scoring.scorecard` hashes it into the run `scorecard_id` (reweighting moves it),
- `suite/*/suite.json` carries NO independent weight numbers (a test asserts the manifest's
  axis membership matches this registry — the drift gate).

To re-weight or promote a candidate, edit THIS file; nothing else hardcodes weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

AxisRole = Literal["headline", "candidate", "experimental"]


@dataclass(frozen=True, slots=True)
class Axis:
    """One capability axis.

    `benches` are the suite-v1 member benches (item-level pooled into the axis);
    `legacy_benches` are suite-v0 back-compat benches that also map to this axis.
    `display` is the runtime domain label; `web_key` is the site/web axis key.
    `weight` is the composite weight (0.0 unless `role == "headline"`).
    `web_display` marks the axes the web build computes/shows on model pages.
    """

    key: str
    display: str
    web_key: str
    benches: tuple[str, ...]
    legacy_benches: tuple[str, ...]
    role: AxisRole
    weight: float
    web_display: bool


# THE registry. Order is the canonical axis order. Weights MUST sum to 1.0 over
# the headline axes (validated by `_validate()` at import).
AXES: Final[tuple[Axis, ...]] = (
    Axis("knowledge", "Knowledge", "knowledge",
         ("mmlu_pro",), ("supergpqa",), "headline", 0.5, True),
    Axis("instruction_following", "Instruction-Following", "instruction",
         ("ifbench",), ("ifeval",), "headline", 0.5, True),
    Axis("math", "Math", "math",
         ("olymmath_hard", "amo"), ("genmath",), "candidate", 0.0, True),
    Axis("long_context", "Long-Context", "long_context",
         ("ruler_32k",), (), "candidate", 0.0, False),
    # agentic_exec_appworld_lite_v0 harness is BUILT (scoring/agentic_exec/) but deliberately
    # NOT registered here until its AppWorld bench is wired into suite-v1 with a frozen
    # scorer_version + real items (register-only-what-we-measure; keeps the registry<->suite
    # drift gate green). Re-add this Axis when the agentic data lands.
    Axis("agentic", "Agentic", "agentic",
         ("bfcl", "bfcl_multi_turn"), (), "experimental", 0.0, True),
    # STATIC judge-free coding proxy (LCB output-prediction) — experimental/gameable. The
    # credible code-GENERATION axis is exec-based (bigcodebench_hard, a SEPARATE opt-in lane
    # via `localbench code`; a candidate), NOT this axis. See the module docstring.
    Axis("coding", "Coding", "coding",
         ("lcb",), (), "experimental", 0.0, False),
)


def bench_domains() -> dict[str, str]:
    """Map every bench (suite-v1 + legacy) to its runtime domain display label."""
    return {
        bench: axis.display
        for axis in AXES
        for bench in (*axis.benches, *axis.legacy_benches)
    }


def domain_weights() -> dict[str, float]:
    """Map each runtime domain display label to its composite weight.

    Headline axes carry their weight; candidate/experimental axes carry 0.0 so a
    present-but-unvalidated axis never enters the headline composite.
    """
    return {axis.display: axis.weight for axis in AXES}


def headline_displays() -> tuple[str, ...]:
    """Runtime domain labels that enter the headline composite."""
    return tuple(axis.display for axis in AXES if axis.role == "headline")


def axis_membership() -> dict[str, tuple[str, ...]]:
    """Canonical axis key -> suite-v1 member benches (the suite.json drift gate)."""
    return {axis.key: axis.benches for axis in AXES}


def web_display_axes() -> tuple[str, ...]:
    """Web/site axis keys the web build computes and shows on model pages."""
    return tuple(axis.web_key for axis in AXES if axis.web_display)


def web_composite_weights() -> dict[str, float]:
    """Web axis key -> composite weight, for the web-displayed axes."""
    return {axis.web_key: axis.weight for axis in AXES if axis.web_display}


def web_source_bench_groups() -> dict[str, tuple[tuple[str, ...], ...]]:
    """Web axis key -> ordered source-bench groups (suite-v1 first, then legacy).

    The web build picks the first group whose benches are all present, then pools
    them. Suite-v1 benches are preferred over their v0 back-compat fallback.
    """
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
    benches = [b for axis in AXES for b in (*axis.benches, *axis.legacy_benches)]
    if len(benches) != len(set(benches)):
        raise ValueError("a bench is mapped to more than one axis")


_validate()
