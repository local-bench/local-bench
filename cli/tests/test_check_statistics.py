from __future__ import annotations

from localbench.check.statistics import (
    AREA_NAMES,
    PairedOutcome,
    bootstrap_area_deltas,
    paired_measures,
    simultaneous_intervals,
)


def _pair(item: str, reference: bool, candidate: bool, *, cluster: str | None = None) -> PairedOutcome:
    return PairedOutcome(
        item_id=item,
        reference_correct=reference,
        candidate_correct=candidate,
        stratum="s",
        cluster=cluster or item,
    )


def test_paired_measures_are_unconditional_over_all_items() -> None:
    measures = paired_measures(
        [
            _pair("stable-right", True, True),
            _pair("drop", True, False),
            _pair("leap", False, True),
            _pair("stable-wrong", False, False),
            _pair("drop-2", True, False),
        ]
    )

    assert measures["drop_count"] == 2
    assert measures["leapfrog_count"] == 1
    assert measures["drop_rate"] == 0.4
    assert measures["leapfrog_rate"] == 0.2
    assert measures["delta_pp"] == -20.0
    assert measures["disagreement_rate"] == 0.6


def test_cluster_bootstrap_resamples_whole_clusters_with_known_seeded_answer() -> None:
    outcomes = [
        _pair("a1", False, True, cluster="a"),
        _pair("a2", False, True, cluster="a"),
        _pair("b1", True, False, cluster="b"),
        _pair("b2", True, False, cluster="b"),
    ]

    deltas = bootstrap_area_deltas(outcomes, resamples=6, seed=9)

    assert deltas == [-100.0, 0.0, 100.0, -100.0, 0.0, 0.0]
    assert set(deltas) <= {-100.0, 0.0, 100.0}


def test_one_zero_discordance_area_switches_all_five_to_tango() -> None:
    variable = [_pair(f"v-{index}", index % 2 == 0, index % 3 == 0) for index in range(12)]
    areas = {area: list(variable) for area in AREA_NAMES}
    areas["math"] = [_pair("m-1", True, True), _pair("m-2", False, False)]

    result = simultaneous_intervals(areas, resamples=200, seed=20260802)

    assert result["method"] == "bonferroni-tango-paired-score"
    interval_rows = result["areas"]
    assert isinstance(interval_rows, dict)
    assert all(isinstance(row, dict) and row["method"] == "bonferroni-tango-paired-score" for row in interval_rows.values())


def test_bootstrap_is_deterministic_and_uses_shared_max_statistic() -> None:
    areas = {
        area: [_pair(f"{area}-{index}", index % 3 != 0, index % 4 != 0) for index in range(24)]
        for area in AREA_NAMES
    }

    first = simultaneous_intervals(areas, resamples=400, seed=20260802)
    second = simultaneous_intervals(areas, resamples=400, seed=20260802)

    assert first == second
    assert first["method"] == "centered-studentized-two-sided-simultaneous-max-statistic"
    critical = first["critical_value"]
    assert isinstance(critical, (int, float)) and critical >= 1.96
