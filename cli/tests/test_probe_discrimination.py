from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from localbench.probe.discrimination import analyze_discrimination


def test_analyze_discrimination_when_axes_vary_applies_keep_and_drop_rules() -> None:
    # Given synthetic anchor and local run records with one saturated axis,
    # one discriminating axis, and one locals-floor axis.
    axis_map = _axis_map()
    records = _records(
        {
            "anchor-a.json": {
                "saturated": 0.99,
                "discriminating": 0.90,
                "locals_floor": 0.80,
            },
            "anchor-b.json": {
                "saturated": 1.00,
                "discriminating": 0.78,
                "locals_floor": 0.68,
            },
            "local-a.json": {
                "saturated": 0.86,
                "discriminating": 0.38,
                "locals_floor": 0.05,
            },
            "local-b.json": {
                "saturated": 0.82,
                "discriminating": 0.22,
                "locals_floor": 0.01,
            },
        },
    )
    labels = _labels()

    # When the probe discrimination analysis runs.
    results = {
        result["axis"]: result
        for result in analyze_discrimination(records, axis_map, labels)
    }

    # Then saturated frontier scores are dropped, locals-floor axes are dropped,
    # and the measured discriminating axis is kept with all kept weight.
    assert results["saturated"]["verdict"] == "drop:frontier-flat"
    assert results["locals_floor"]["verdict"] == "drop:locals-floor"
    assert results["discriminating"]["verdict"] == "keep"
    assert results["discriminating"]["anchor_spread"] == pytest.approx(0.12)
    assert results["discriminating"]["overall_spread"] == pytest.approx(0.68)
    assert results["discriminating"]["suggested_weight"] == pytest.approx(1.0)
    kept_weight = sum(
        result["suggested_weight"]
        for result in results.values()
        if result["verdict"] == "keep"
    )
    assert kept_weight == pytest.approx(1.0)


def test_probe_cli_when_synthetic_runs_writes_json_and_prints_table(
    tmp_path: Path,
) -> None:
    # Given a temporary suite, labels file, and synthetic local run records.
    suite_dir = tmp_path / "suite" / "v1"
    runs_dir = tmp_path / "runs"
    suite_dir.mkdir(parents=True)
    runs_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps({"axes": _axis_map()}),
        encoding="utf-8",
    )
    for filename, record in _records(
        {
            "anchor-a.json": {
                "saturated": 0.99,
                "discriminating": 0.90,
                "locals_floor": 0.80,
            },
            "anchor-b.json": {
                "saturated": 1.00,
                "discriminating": 0.78,
                "locals_floor": 0.68,
            },
            "local-a.json": {
                "saturated": 0.86,
                "discriminating": 0.38,
                "locals_floor": 0.05,
            },
            "local-b.json": {
                "saturated": 0.82,
                "discriminating": 0.22,
                "locals_floor": 0.01,
            },
        },
    ).items():
        (runs_dir / filename).write_text(json.dumps(record), encoding="utf-8")
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps(_labels()), encoding="utf-8")
    out_path = tmp_path / "probe-legA.json"

    # When invoking the probe package CLI through its module entrypoint.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "localbench.probe",
            "--runs",
            str(runs_dir),
            "--labels",
            str(labels_path),
            "--suite-dir",
            str(suite_dir),
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # Then the table is readable and the JSON contains normalized kept weights.
    assert "axis" in completed.stdout
    assert "discriminating" in completed.stdout
    assert "weak/indicative" in completed.stdout
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    results = {result["axis"]: result for result in payload["axes"]}
    assert payload["schema"] == "localbench-probe-legA-v1"
    assert results["discriminating"]["verdict"] == "keep"
    assert results["discriminating"]["suggested_weight"] == pytest.approx(1.0)
    assert results["saturated"]["verdict"] == "drop:frontier-flat"
    assert results["locals_floor"]["verdict"] == "drop:locals-floor"


def test_analyze_discrimination_when_inputs_are_incomplete_records_notes() -> None:
    # Given one unlabeled run and one labeled run missing the requested bench/items.
    records = {
        "unlabeled.json": {
            "benches": {"missing": _bench(0.50)},
            "composite": 0.50,
            "items": [],
        },
        "anchor-a.json": {"benches": {}, "composite": 0.75},
    }

    # When the probe analysis sees missing labels, benches, and items.
    result = analyze_discrimination(
        records,
        {"fragile": {"benches": ["missing"], "weight": None}},
        {"anchor-a.json": {"label": "anchor", "model_name": "anchor-a"}},
    )[0]

    # Then it records notes and returns a drop verdict instead of crashing.
    notes = result["notes"]
    assert result["verdict"] == "drop:frontier-flat"
    assert any("missing label" in note for note in notes)
    assert any("skipped missing bench missing" in note for note in notes)
    assert any("missing items list" in note for note in notes)


def test_analyze_discrimination_reference_anchored_axis_judges_via_published_ceiling() -> None:
    # Given an axis with NO measured anchors but a published reference ceiling (the math
    # case: frontier scores are cited from the source, not re-measured by local-bench).
    labels = {
        "local-a.json": {"label": "local", "model_name": "local-a"},
        "local-b.json": {"label": "local", "model_name": "local-b"},
    }
    axis_map = {"refmath": {"benches": ["m"], "weight": None, "reference_score": 0.58}}

    # When locals floor far below the published ceiling, the axis is KEPT and anchored to it.
    floored = analyze_discrimination(
        {
            "local-a.json": {"benches": {"m": _bench(0.02)}, "composite": 0.30, "items": [_item("m", "m-1", False)]},
            "local-b.json": {"benches": {"m": _bench(0.05)}, "composite": 0.20, "items": [_item("m", "m-1", False)]},
        },
        axis_map,
        labels,
    )[0]
    # REPORTED ceiling -> triage (never weighted): a published number can't promote an axis.
    assert floored["verdict"] == "triage"
    assert floored["suggested_weight"] == 0.0
    assert floored["anchor_max"] == pytest.approx(0.58)
    assert floored["overall_spread"] == pytest.approx(0.56)
    assert any("reference-anchored" in note for note in floored["notes"])

    # When locals already sit near the published ceiling, the axis does not discriminate.
    saturated = analyze_discrimination(
        {
            "local-a.json": {"benches": {"m": _bench(0.56)}, "composite": 0.55, "items": [_item("m", "m-1", True)]},
            "local-b.json": {"benches": {"m": _bench(0.57)}, "composite": 0.55, "items": [_item("m", "m-1", True)]},
        },
        axis_map,
        labels,
    )[0]
    assert saturated["verdict"] == "drop:locals-floor"


def test_ci_gate_refuses_to_promote_on_thin_evidence() -> None:
    # A MODERATE floor->frontier spread (0.45 vs 0.30) on only ~12 items: the CI straddles
    # the keep bound, so the axis is inconclusive rather than a confident keep or drop.
    # (A huge spread would still keep even at small N — it's the marginal case that needs N.)
    axis_map = {"disc": {"benches": ["disc"], "weight": None}}
    thin = analyze_discrimination(
        {
            "anchor-a.json": {"benches": {"disc": _bench(0.45, n=12)}, "composite": 0.45, "items": []},
            "anchor-b.json": {"benches": {"disc": _bench(0.40, n=12)}, "composite": 0.40, "items": []},
            "local-a.json": {"benches": {"disc": _bench(0.32, n=12)}, "composite": 0.32, "items": []},
            "local-b.json": {"benches": {"disc": _bench(0.30, n=12)}, "composite": 0.30, "items": []},
        },
        axis_map,
        _labels(),
    )[0]
    assert thin["verdict"] == "inconclusive:wide-ci"
    assert thin["suggested_weight"] == 0.0
    assert thin["n_anchors"] == 2


def test_single_anchor_axis_is_triage_only() -> None:
    # A single anchor can never promote (one lab's idiosyncrasies) -> triage, even with a
    # huge apparent spread. (Spread 0 on one anchor must NOT read as frontier-flat.)
    axis_map = {"disc": {"benches": ["disc"], "weight": None}}
    labels = {
        "anchor-a.json": {"label": "anchor", "model_name": "anchor-a"},
        "local-a.json": {"label": "local", "model_name": "local-a"},
        "local-b.json": {"label": "local", "model_name": "local-b"},
    }
    one_anchor = analyze_discrimination(
        {
            "anchor-a.json": {"benches": {"disc": _bench(0.90)}, "composite": 0.90, "items": []},
            "local-a.json": {"benches": {"disc": _bench(0.30)}, "composite": 0.30, "items": []},
            "local-b.json": {"benches": {"disc": _bench(0.20)}, "composite": 0.20, "items": []},
        },
        axis_map,
        labels,
    )[0]
    assert one_anchor["verdict"] == "triage"
    assert one_anchor["n_anchors"] == 1
    assert one_anchor["suggested_weight"] == 0.0


def test_high_extraction_failure_axis_is_not_weighted() -> None:
    # Even a clean keep is excluded from weighting if its parse/extraction-failure upper
    # bound breaches the ceiling (the scores are unreliable).
    axis_map = {"disc": {"benches": ["disc"], "weight": None}}
    bad = _bench(0.90)
    bad["n_extraction_failures"] = 80  # 80/400 = 20% on the frontier
    failing = analyze_discrimination(
        {
            "anchor-a.json": {"benches": {"disc": bad}, "composite": 0.90, "items": []},
            "anchor-b.json": {"benches": {"disc": _bench(0.80)}, "composite": 0.80, "items": []},
            "local-a.json": {"benches": {"disc": _bench(0.30)}, "composite": 0.30, "items": []},
            "local-b.json": {"benches": {"disc": _bench(0.20)}, "composite": 0.20, "items": []},
        },
        axis_map,
        _labels(),
    )[0]
    assert failing["verdict"] == "keep"  # it discriminates...
    assert failing["parse_fail_ok"] is False  # ...but extraction is failing...
    assert failing["suggested_weight"] == 0.0  # ...so it is not weighted.


def test_anchor_only_axis_is_triage_not_promoted_on_anchor_vs_anchor_spread() -> None:
    # No local scores -> an anchor-vs-anchor spread is NOT local->frontier discrimination.
    # Even a huge 0.50 anchor spread must triage, never keep/weight (autoreview blocker).
    axis_map = {"disc": {"benches": ["disc"], "weight": None}}
    anchors_only = analyze_discrimination(
        {
            "anchor-a.json": {"benches": {"disc": _bench(0.90)}, "composite": 0.90, "items": []},
            "anchor-b.json": {"benches": {"disc": _bench(0.40)}, "composite": 0.40, "items": []},
        },
        axis_map,
        {
            "anchor-a.json": {"label": "anchor", "model_name": "anchor-a"},
            "anchor-b.json": {"label": "anchor", "model_name": "anchor-b"},
        },
    )[0]
    assert anchors_only["verdict"] == "triage"
    assert anchors_only["suggested_weight"] == 0.0


def _axis_map() -> dict[str, dict[str, list[str] | None]]:
    return {
        "saturated": {"benches": ["sat"], "weight": None},
        "discriminating": {"benches": ["disc"], "weight": None},
        "locals_floor": {"benches": ["floor"], "weight": None},
    }


def _labels() -> dict[str, dict[str, str]]:
    return {
        "anchor-a.json": {"label": "anchor", "model_name": "anchor-a"},
        "anchor-b.json": {"label": "anchor", "model_name": "anchor-b"},
        "local-a.json": {"label": "local", "model_name": "local-a"},
        "local-b.json": {"label": "local", "model_name": "local-b"},
    }


def _records(
    scores_by_file: dict[str, dict[str, float]],
) -> dict[str, dict[str, object]]:
    composites = {
        "anchor-a.json": 0.95,
        "anchor-b.json": 0.84,
        "local-a.json": 0.36,
        "local-b.json": 0.18,
    }
    records: dict[str, dict[str, object]] = {}
    for filename, scores in scores_by_file.items():
        records[filename] = {
            "benches": {
                "sat": _bench(scores["saturated"]),
                "disc": _bench(scores["discriminating"]),
                "floor": _bench(scores["locals_floor"]),
            },
            "composite": composites[filename],
            "items": [
                _item("sat", "sat-1", scores["saturated"] >= 0.85),
                _item("disc", "disc-1", scores["discriminating"] >= 0.50),
                _item("floor", "floor-1", scores["locals_floor"] >= 0.50),
            ],
        }
    return records


def _bench(chance_corrected: float, *, n: int = 400) -> dict[str, float | int]:
    # n defaults to a realistic ranked-run size; the CI-bound spread gate needs real sample
    # sizes (a 2-model +/-5pp decision needs ~770 items), so tiny n -> inconclusive by design.
    return {
        "raw_accuracy": chance_corrected,
        "chance_corrected": chance_corrected,
        "n": n,
        "n_errors": 0,
        "n_extraction_failures": 0,
    }


def _item(bench: str, item_id: str, correct: bool) -> dict[str, str | bool]:
    return {"id": item_id, "bench": bench, "correct": correct}
