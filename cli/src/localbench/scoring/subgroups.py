from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NotRequired, TypedDict

from localbench.scoring.bootstrap import Interval, stratified_mean_ci


class DeltaObservation(TypedDict):
    domain: str
    stratum: str
    cluster: NotRequired[str]
    raw_delta: NotRequired[int]
    signed_delta: float


class SubgroupDelta(TypedDict):
    domain: str
    stratum: str
    n: int
    ci: Interval
    mcnemar_p: float
    bh_adjusted_p: float
    b_regressions: int
    c_improvements: int
    severe_subgroup_regression: bool


@dataclass(frozen=True, slots=True)
class _SubgroupCell:
    domain: str
    stratum: str
    n: int
    ci: Interval
    mcnemar_p: float
    b_regressions: int
    c_improvements: int


def subgroup_delta_cis(
    observations: Sequence[DeltaObservation],
    *,
    iters: int = 10_000,
    seed: int = 0,
    threshold: float = 0.10,
    alpha: float = 0.05,
) -> list[SubgroupDelta]:
    """Return per-stratum paired delta CIs and severe-regression flags."""
    grouped: dict[tuple[str, str], list[DeltaObservation]] = {}
    for observation in observations:
        grouped.setdefault(
            (observation["domain"], observation["stratum"]),
            [],
        ).append(observation)
    cells: list[_SubgroupCell] = []
    for index, key in enumerate(sorted(grouped)):
        domain, stratum = key
        cell = grouped[key]
        values = [observation["signed_delta"] for observation in cell]
        raw_deltas = [observation.get("raw_delta", 0) for observation in cell]
        b_regressions = sum(1 for delta in raw_deltas if delta == -1)
        c_improvements = sum(1 for delta in raw_deltas if delta == 1)
        clusters = [
            observation.get("cluster", f"{domain}|{stratum}|{index}")
            for index, observation in enumerate(cell)
        ]
        ci = stratified_mean_ci(
            values,
            [stratum] * len(values),
            iters=iters,
            seed=seed + index,
            clusters=clusters,
        )
        cells.append(
            _SubgroupCell(
                domain=domain,
                stratum=stratum,
                n=len(values),
                ci=ci,
                mcnemar_p=_one_sided_mcnemar_p(b_regressions, c_improvements),
                b_regressions=b_regressions,
                c_improvements=c_improvements,
            ),
        )
    adjusted_p_values = _benjamini_hochberg([cell.mcnemar_p for cell in cells])
    subgroups: list[SubgroupDelta] = []
    for cell, adjusted_p in zip(cells, adjusted_p_values, strict=True):
        subgroups.append(
            {
                "domain": cell.domain,
                "stratum": cell.stratum,
                "n": cell.n,
                "ci": cell.ci,
                "mcnemar_p": cell.mcnemar_p,
                "bh_adjusted_p": adjusted_p,
                "b_regressions": cell.b_regressions,
                "c_improvements": cell.c_improvements,
                "severe_subgroup_regression": adjusted_p < alpha
                and cell.ci["hi"] < -threshold,
            },
        )
    return subgroups


def severe_subgroup_regressions(
    subgroups: Sequence[SubgroupDelta],
    *,
    threshold: float = 0.10,
) -> list[SubgroupDelta]:
    """Return strata whose paired delta CI is wholly below -threshold."""
    return [
        subgroup
        for subgroup in subgroups
        if subgroup.get("severe_subgroup_regression", subgroup["ci"]["hi"] < -threshold)
        and subgroup["ci"]["hi"] < -threshold
    ]


def _one_sided_mcnemar_p(b_regressions: int, c_improvements: int) -> float:
    total = b_regressions + c_improvements
    if total == 0:
        return 1.0
    tail = sum(math.comb(total, successes) for successes in range(b_regressions, total + 1))
    return tail / (2**total)


def _benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    count = len(p_values)
    adjusted = [1.0] * count
    running_min = 1.0
    ranked = sorted(range(count), key=p_values.__getitem__)
    for rank, index in reversed(list(enumerate(ranked, start=1))):
        running_min = min(running_min, p_values[index] * count / rank)
        adjusted[index] = min(1.0, running_min)
    return adjusted
