from __future__ import annotations

from collections.abc import Sequence
from typing import NotRequired, TypedDict

from localbench.scoring.bootstrap import Interval, stratified_mean_ci


class DeltaObservation(TypedDict):
    domain: str
    stratum: str
    cluster: NotRequired[str]
    signed_delta: float


class SubgroupDelta(TypedDict):
    domain: str
    stratum: str
    n: int
    ci: Interval
    severe_subgroup_regression: bool


def subgroup_delta_cis(
    observations: Sequence[DeltaObservation],
    *,
    iters: int = 10_000,
    seed: int = 0,
    threshold: float = 0.10,
) -> list[SubgroupDelta]:
    """Return per-stratum paired delta CIs and severe-regression flags."""
    grouped: dict[tuple[str, str], list[DeltaObservation]] = {}
    for observation in observations:
        grouped.setdefault(
            (observation["domain"], observation["stratum"]),
            [],
        ).append(observation)
    subgroups: list[SubgroupDelta] = []
    for index, key in enumerate(sorted(grouped)):
        domain, stratum = key
        cell = grouped[key]
        values = [observation["signed_delta"] for observation in cell]
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
        subgroups.append(
            {
                "domain": domain,
                "stratum": stratum,
                "n": len(values),
                "ci": ci,
                "severe_subgroup_regression": ci["hi"] < -threshold,
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
        if subgroup["ci"]["hi"] < -threshold
    ]
