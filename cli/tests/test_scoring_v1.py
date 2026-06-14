"""Tests for the v1 rigorous scoring analysis layer."""

from __future__ import annotations

import json
import random
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from localbench.scoring.bootstrap import per_bench_ci, stratified_mean_ci
from localbench.scoring.paired_delta import compare_runs, format_honest_delta
from localbench.scoring.signed_score import display_clamp, signed_score
from localbench.scoring.subgroups import severe_subgroup_regressions


def test_signed_score_when_below_chance_stays_negative() -> None:
    # Given a multiple-choice score below a 10% chance baseline.
    raw_accuracy = 0.05

    # When computing the inference score.
    score = signed_score(raw_accuracy, chance=0.10)

    # Then the signed value is not clamped, while the display helper is cosmetic.
    assert score == pytest.approx(-1 / 18)
    assert display_clamp(score) == 0.0
    assert display_clamp(1.2) == 1.0


def test_per_bench_ci_when_seed_is_fixed_is_deterministic() -> None:
    # Given a stratified item set with a known point estimate.
    correct = [True, True, False, False, True, False, True, True]
    strata = ["a", "a", "a", "a", "b", "b", "b", "b"]

    # When computing the same bootstrap twice with the same seed.
    first = per_bench_ci(correct, strata, iters=500, seed=321)
    second = per_bench_ci(correct, strata, iters=500, seed=321)

    # Then every reported number is reproducible.
    assert first == second
    assert first["point"] == pytest.approx(0.625)


def test_per_bench_ci_when_sampling_known_bernoulli_brackets_truth() -> None:
    # Given repeated Bernoulli samples with a known true probability.
    truth = 0.60
    sample_seeds = range(40)
    bracketed = 0

    for sample_seed in sample_seeds:
        rng = random.Random(sample_seed)
        correct = [rng.random() < truth for _ in range(180)]
        strata = ["single"] * len(correct)

        # When a seeded percentile bootstrap CI is computed for each sample.
        interval = per_bench_ci(correct, strata, iters=450, seed=10_000 + sample_seed)

        # Then the truth is bracketed at approximately the advertised rate.
        if interval["lo"] <= truth <= interval["hi"]:
            bracketed += 1

    assert bracketed >= 36


def test_compare_runs_when_identical_returns_zero_tight_delta() -> None:
    # Given two saved run records with identical item outcomes.
    record = _run_record(
        [
            _item("mmlu-0", "mmlu_pro", True, category="business"),
            _item("mmlu-1", "mmlu_pro", False, category="business"),
            _item("math-0", "genmath", True, category="algebra", difficulty="easy"),
            _item("math-1", "genmath", False, category="algebra", difficulty="hard"),
            _item("ifeval-0", "ifeval", True, template="keywords:existence"),
            _item("ifeval-1", "ifeval", True, template="keywords:existence"),
        ],
    )

    # When comparing the runs.
    comparison = compare_runs(record, record, iters=500, seed=99)

    # Then the paired fixed-suite delta is exactly zero with a tight interval.
    assert comparison["composite_delta"]["point"] == 0.0
    assert comparison["repeatability_ci"] == {"point": 0.0, "lo": 0.0, "hi": 0.0}
    assert comparison["generalization_ci"] == {"point": 0.0, "lo": 0.0, "hi": 0.0}
    assert comparison["worst_axis"]["delta"]["point"] == 0.0


def test_compare_runs_when_clusters_are_absent_matches_explicit_singletons() -> None:
    # Given existing synthetic records and the same records with singleton clusters.
    degraded = _balanced_regression_run(degraded=True)
    baseline = _balanced_regression_run(degraded=False)
    clustered_degraded = _with_singleton_clusters(degraded)
    clustered_baseline = _with_singleton_clusters(baseline)

    # When comparing both forms with the same bootstrap seed.
    absent = compare_runs(degraded, baseline, iters=700, seed=23)
    explicit = compare_runs(clustered_degraded, clustered_baseline, iters=700, seed=23)

    # Then singleton fallback preserves every reported number exactly.
    assert explicit == absent


def test_stratified_mean_ci_when_items_share_cluster_uses_block_resampling() -> None:
    # Given one passage cluster with many correlated regressions and neutral singleton clusters.
    values = [-1.0] * 12 + [0.0] * 12
    strata = ["long-context"] * len(values)
    clusters = ["shared-passage"] * 12 + [f"neutral-{index}" for index in range(12)]

    # When the same values are bootstrapped by item and by cluster block.
    naive = stratified_mean_ci(values, strata, iters=2_000, seed=11)
    clustered = stratified_mean_ci(values, strata, clusters=clusters, iters=2_000, seed=11)

    # Then the correlated regressions count as one resampling unit, widening the CI.
    assert _interval_width(clustered) > _interval_width(naive)
    assert clustered["hi"] > naive["hi"]


def test_compare_runs_when_regression_is_hidden_by_composite_flags_worst_axis() -> None:
    # Given a planted regression where instruction-following loses every item,
    # while knowledge and math improve enough for the composite to round to zero.
    degraded = _balanced_regression_run(degraded=True)
    baseline = _balanced_regression_run(degraded=False)

    # When comparing degraded run A against baseline run B.
    comparison = compare_runs(degraded, baseline, iters=800, seed=7)
    subgroup_flags = severe_subgroup_regressions(
        comparison["subgroups"],
        threshold=0.10,
    )

    # Then the composite hides the damage, but worst-axis and subgroup checks catch it.
    assert comparison["composite_delta"]["point"] == pytest.approx(0.0)
    assert abs(comparison["composite_delta"]["point"]) < 0.01
    assert comparison["worst_axis"]["domain"] == "Instruction-Following"
    assert comparison["worst_axis"]["delta"]["point"] == pytest.approx(-1.0)
    assert comparison["worst_axis"]["delta"]["hi"] < -0.90
    assert subgroup_flags
    assert subgroup_flags[0]["domain"] == "Instruction-Following"
    assert subgroup_flags[0]["ci"]["hi"] < -0.90


def test_compare_runs_when_noisy_subgroup_regressions_are_bh_suppressed() -> None:
    # Given several tiny clustered cells whose CIs are severe, plus one genuine cell.
    degraded_items: list[dict] = []
    baseline_items: list[dict] = []
    for cell_index in range(6):
        degraded_cell, baseline_cell = _discordant_cell_items(
            prefix=f"noise-{cell_index}",
            template=f"noise-{cell_index}",
            regressions=3,
            improvements=2,
            cluster=f"noise-cluster-{cell_index}",
        )
        degraded_items.extend(degraded_cell)
        baseline_items.extend(baseline_cell)
    genuine_degraded, genuine_baseline = _discordant_cell_items(
        prefix="genuine",
        template="genuine",
        regressions=20,
        improvements=0,
        cluster="genuine-cluster",
    )
    degraded_items.extend(genuine_degraded)
    baseline_items.extend(genuine_baseline)

    # When comparing the degraded run against the baseline run.
    comparison = compare_runs(
        _run_record(degraded_items),
        _run_record(baseline_items),
        iters=800,
        seed=17,
    )
    by_stratum = {subgroup["stratum"]: subgroup for subgroup in comparison["subgroups"]}

    # Then BH suppresses the noisy CI-only flags but keeps the genuine regression.
    for cell_index in range(6):
        subgroup = by_stratum[f"template=noise-{cell_index}"]
        assert subgroup["ci"]["hi"] < -0.10
        assert subgroup["b_regressions"] == 3
        assert subgroup["c_improvements"] == 2
        assert subgroup["bh_adjusted_p"] >= 0.05
        assert not subgroup["severe_subgroup_regression"]
    genuine = by_stratum["template=genuine"]
    assert genuine["mcnemar_p"] == pytest.approx(2**-20)
    assert genuine["bh_adjusted_p"] < 0.05
    assert genuine["severe_subgroup_regression"]


def test_compare_runs_when_item_sets_differ_errors() -> None:
    # Given records over different item ids.
    record_a = _run_record([_item("a", "genmath", True)])
    record_b = _run_record([_item("b", "genmath", True)])

    # When comparing them, then paired alignment rejects the comparison.
    with pytest.raises(ValueError, match="same item ids"):
        compare_runs(record_a, record_b, iters=100, seed=1)


def test_honest_delta_label_names_fixed_items() -> None:
    # Given a point estimate and interval in score units.
    interval = {"point": -0.123, "lo": -0.183, "hi": -0.063}

    # When formatting the user-facing label.
    label = format_honest_delta(interval)

    # Then the label uses fixed-suite language, not universal percent language.
    assert label == "−12.3 ± 6.0 on these items"
    assert "%" not in label


def test_cli_compare_help_exits_zero() -> None:
    # Given the module CLI entry point.
    # When requesting compare help.
    result = subprocess.run(
        [sys.executable, "-m", "localbench", "compare", "--help"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    # Then argparse exits successfully and shows compare arguments.
    assert result.returncode == 0
    assert "RUN_A.json" in result.stdout
    assert "RUN_B.json" in result.stdout
    assert "--out" in result.stdout


def test_cli_compare_when_out_is_supplied_writes_json(tmp_path: Path) -> None:
    # Given two saved run records on disk.
    run_a = tmp_path / "a.json"
    run_b = tmp_path / "b.json"
    out = tmp_path / "cmp.json"
    run_a.write_text(json.dumps(_balanced_regression_run(degraded=True)), encoding="utf-8")
    run_b.write_text(json.dumps(_balanced_regression_run(degraded=False)), encoding="utf-8")

    # When comparing through the CLI surface.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "localbench",
            "compare",
            str(run_a),
            str(run_b),
            "--out",
            str(out),
            "--iters",
            "300",
            "--seed",
            "7",
        ],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    # Then the CLI reports and writes the same planted worst-axis regression.
    assert result.returncode == 0
    assert "paired composite delta" in result.stdout
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["composite_delta"]["point"] == pytest.approx(0.0)
    assert written["worst_axis"]["domain"] == "Instruction-Following"


def _balanced_regression_run(*, degraded: bool) -> dict:
    items = [
        *_paired_items(
            bench="mmlu_pro",
            prefix="mmlu",
            category="business",
            baseline_correct=11,
            degraded_correct=20,
            count=20,
        ),
        *_paired_items(
            bench="genmath",
            prefix="math",
            category="algebra",
            difficulty="medium",
            baseline_correct=10,
            degraded_correct=20,
            count=20,
        ),
        *_paired_items(
            bench="ifeval",
            prefix="ifeval",
            template="length_constraints:number_words",
            baseline_correct=20,
            degraded_correct=0,
            count=20,
        ),
    ]
    selected = [
        item[0] if degraded else item[1]
        for item in items
    ]
    return _run_record(selected)


def _paired_items(
    *,
    bench: str,
    prefix: str,
    baseline_correct: int,
    degraded_correct: int,
    count: int,
    category: str | None = None,
    difficulty: str | None = None,
    template: str | None = None,
) -> list[tuple[dict, dict]]:
    pairs: list[tuple[dict, dict]] = []
    for index in range(count):
        item_id = f"{prefix}-{index}"
        pairs.append(
            (
                _item(
                    item_id,
                    bench,
                    index < degraded_correct,
                    category=category,
                    difficulty=difficulty,
                    template=template,
                ),
                _item(
                    item_id,
                    bench,
                    index < baseline_correct,
                    category=category,
                    difficulty=difficulty,
                    template=template,
                ),
            ),
        )
    return pairs


def _discordant_cell_items(
    *,
    prefix: str,
    template: str,
    regressions: int,
    improvements: int,
    cluster: str,
) -> tuple[list[dict], list[dict]]:
    degraded: list[dict] = []
    baseline: list[dict] = []
    for index in range(regressions):
        item_id = f"{prefix}-regression-{index}"
        degraded.append(_item(item_id, "ifeval", False, template=template, cluster=cluster))
        baseline.append(_item(item_id, "ifeval", True, template=template, cluster=cluster))
    for index in range(improvements):
        item_id = f"{prefix}-improvement-{index}"
        degraded.append(_item(item_id, "ifeval", True, template=template, cluster=cluster))
        baseline.append(_item(item_id, "ifeval", False, template=template, cluster=cluster))
    return degraded, baseline


def _item(
    item_id: str,
    bench: str,
    correct: bool,
    *,
    category: str | None = None,
    difficulty: str | None = None,
    template: str | None = None,
    cluster: str | None = None,
) -> dict:
    item = {
        "id": item_id,
        "bench": bench,
        "correct": correct,
        "extracted": None,
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "error": None,
    }
    if category is not None:
        item["category"] = category
    if difficulty is not None:
        item["difficulty"] = difficulty
    if template is not None:
        item["template"] = template
    if cluster is not None:
        item["cluster"] = cluster
    return item


def _with_singleton_clusters(record: dict) -> dict:
    return {
        **record,
        "items": [
            {
                **item,
                "cluster": str(item["id"]),
            }
            for item in record["items"]
        ],
    }


def _interval_width(interval: dict[str, float]) -> float:
    return interval["hi"] - interval["lo"]


def _run_record(items: Sequence[dict]) -> dict:
    benches = sorted({str(item["bench"]) for item in items})
    return {
        "schema": "localbench-run-v0",
        "manifest": {"suite": {"version": "suite-v0"}},
        "benches": {
            bench: {
                "n": sum(1 for item in items if item["bench"] == bench),
                "n_errors": 0,
                "n_extraction_failures": 0,
                "raw_accuracy": 0.0,
                "chance_corrected": 0.0,
            }
            for bench in benches
        },
        "composite": 0.0,
        "items": list(items),
        "totals": {
            "n_items": len(items),
            "n_errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "wall_time_seconds": 0.0,
            "completion_tokens_per_second": 0.0,
        },
        "warnings": [],
        "output_path": "synthetic.json",
    }
