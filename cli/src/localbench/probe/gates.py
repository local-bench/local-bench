"""Confidence-bound promotion gates for the discrimination campaign (oracle #4).

Point-estimate gates (>=15pp keep / <5pp drop / <5% parse-fail) mislead at small N: a
two-model difference needs ~770 items for +/-5pp, so a 148-item axis can *detect a big
spread* but cannot make a fine drop decision. These functions replace point estimates
with confidence-bound decisions:

- KEEP only if the LOWER 95% bound on the floor->frontier spread clears the keep threshold.
- DROP only if the UPPER 95% bound is below the drop threshold AND the axis has enough items.
- never PROMOTE unless at least three local models are present, so the axis separates the
  local range rather than a single local-vs-frontier gap.
- gate parse/extraction-failure on its UPPER confidence bound, not the observed rate, and
  require it to be similar ACROSS families (a differential failure is a formatting artifact).
- require a candidate axis to add information BEYOND the headline (not merely correlate).

Everything here is pure statistics over counts/scores — no run data, no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

Z95: Final = 1.959963984540054  # two-sided 95% normal quantile

# Promotion thresholds on the 0..1 axis-score scale (floor->frontier spread).
KEEP_SPREAD: Final = 0.15  # promote only if the LOWER 95% bound clears this
DROP_SPREAD: Final = 0.05  # drop only if the UPPER 95% bound is below this
MIN_LOCALS_FOR_PROMOTION: Final = 3
MIN_ITEMS_FOR_DROP: Final = 300  # don't make a fine drop decision on a tiny axis
PARSE_FAIL_CEILING: Final = 0.05  # max acceptable parse/extraction-failure (upper bound)
DIFFERENTIAL_PARSE_FAIL_MAX: Final = 0.10  # max acceptable gap in parse-fail rate across families
REDUNDANCY_R: Final = 0.95  # |corr| with the headline above which a candidate adds nothing

SpreadVerdict = Literal["keep", "drop", "triage", "inconclusive:wide-ci", "inconclusive:small-n"]


_MIN_VAR: Final = 0.05 * 0.95  # variance floor (see _score_variance)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _score_variance(score: float) -> float:
    """Per-score binomial variance proxy, FLOORED so a clamped 0/1 (or below-chance, i.e.
    negative chance-corrected) score isn't treated as zero-variance — which would make the
    spread CI overconfident exactly at the floor. Conservative (never under-estimates)."""
    p = _clamp01(score)
    return max(p * (1 - p), _MIN_VAR)


def wilson_interval(successes: float, n: int, *, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (stable near 0/1, unlike Wald)."""
    if n <= 0:
        return (0.0, 1.0)
    p = _clamp01(successes / n)
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def proportion_upper_bound(failures: int, n: int, *, z: float = Z95) -> float:
    """Upper 95% bound on a failure rate. With n==0 we know nothing -> 1.0 (fail closed)."""
    if n <= 0:
        return 1.0
    return wilson_interval(failures, n, z=z)[1]


def spread_ci(
    frontier: float, n_frontier: int, floor: float, n_floor: int, *, z: float = Z95
) -> tuple[float, float]:
    """95% CI on the floor->frontier spread (a difference of two independent scores).

    SE uses the Wald variance of each score treated as a proportion (clamped to [0,1] for
    the variance only); the point spread uses the raw scores. An approximation suitable as
    a GATE, not a published CI.
    """
    point = frontier - floor
    if n_frontier <= 0 or n_floor <= 0:
        return (-math.inf, math.inf)  # unknown N -> infinitely wide -> neither keep nor drop fires
    se = math.sqrt(_score_variance(frontier) / n_frontier + _score_variance(floor) / n_floor)
    return (point - z * se, point + z * se)


@dataclass(frozen=True, slots=True)
class SpreadGateResult:
    verdict: SpreadVerdict
    spread: float
    ci_low: float
    ci_high: float
    n_items: int
    n_anchors: int
    n_locals: int
    reasons: tuple[str, ...]


def spread_gate(
    *,
    frontier: float,
    n_frontier: int,
    floor: float,
    n_floor: int,
    n_anchors: int,
    n_locals: int,
    n_items: int,
    keep: float = KEEP_SPREAD,
    drop: float = DROP_SPREAD,
    min_locals: int = MIN_LOCALS_FOR_PROMOTION,
    min_items_for_drop: int = MIN_ITEMS_FOR_DROP,
) -> SpreadGateResult:
    """Decide keep / drop / triage / inconclusive on the floor->frontier spread by CI."""
    point = frontier - floor
    ci_low, ci_high = spread_ci(frontier, n_frontier, floor, n_floor)
    reasons: list[str] = []

    if n_locals < min_locals:
        reasons.append(f"only {n_locals} local model(s); >= {min_locals} required to promote")
        return SpreadGateResult("triage", point, ci_low, ci_high, n_items, n_anchors, n_locals, tuple(reasons))

    if ci_low >= keep:
        reasons.append(f"lower 95% bound on spread {ci_low:.2f} >= keep {keep:.2f}")
        return SpreadGateResult("keep", point, ci_low, ci_high, n_items, n_anchors, n_locals, tuple(reasons))

    if ci_high < drop:
        if n_items < min_items_for_drop:
            reasons.append(f"would drop (upper {ci_high:.2f} < {drop:.2f}) but only {n_items} items (< {min_items_for_drop})")
            return SpreadGateResult(
                "inconclusive:small-n",
                point,
                ci_low,
                ci_high,
                n_items,
                n_anchors,
                n_locals,
                tuple(reasons),
            )
        reasons.append(f"upper 95% bound on spread {ci_high:.2f} < drop {drop:.2f}")
        return SpreadGateResult("drop", point, ci_low, ci_high, n_items, n_anchors, n_locals, tuple(reasons))

    reasons.append(f"CI [{ci_low:.2f}, {ci_high:.2f}] straddles keep/drop; need more items")
    return SpreadGateResult("inconclusive:wide-ci", point, ci_low, ci_high, n_items, n_anchors, n_locals, tuple(reasons))


def parse_fail_gate(failures: int, n: int, *, ceiling: float = PARSE_FAIL_CEILING) -> tuple[bool, float]:
    """Pass only if the UPPER confidence bound on the parse-fail rate is below `ceiling`."""
    upper = proportion_upper_bound(failures, n)
    return (upper < ceiling, upper)


def differential_parse_fail_gate(
    rates_by_family: Sequence[float], *, max_gap: float = DIFFERENTIAL_PARSE_FAIL_MAX
) -> tuple[bool, float]:
    """Pass only if parse-fail rates are similar across families (a big gap = a formatting
    test masquerading as a capability test). Returns (passed, observed max-min gap)."""
    if len(rates_by_family) < 2:
        return (True, 0.0)
    gap = max(rates_by_family) - min(rates_by_family)
    return (gap <= max_gap, gap)


def pearson_r(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson correlation, or None if undefined (n<2 or a zero-variance series)."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return sxy / math.sqrt(sxx * syy)


def is_redundant_with_headline(axis_scores: Sequence[float], headline_scores: Sequence[float], *, threshold: float = REDUNDANCY_R) -> bool:
    """True when a candidate axis is so correlated with the headline it adds no information."""
    r = pearson_r(axis_scores, headline_scores)
    return r is not None and abs(r) >= threshold
