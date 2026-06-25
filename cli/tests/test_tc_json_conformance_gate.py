from __future__ import annotations

import json
from pathlib import Path

import pytest

from board_fixtures import (
    FROZEN_AT,
    float_value,
    object_value,
    objects_value,
    run_record,
    source,
    write_inputs,
    write_run,
)
from localbench.scoring.board import build_board
from localbench.scoring.tc_json_conformance import tc_json_conformance_gate


def test_tc_json_gate_maps_aggregate_percentages_and_reasons() -> None:
    # Given: a measured tc_json aggregate with a mid-band pass rate and low invalid JSON rate.
    aggregate = {
        "n": 330,
        "correct": 235,
        "raw_asr": 0.712,
        "wilson_95_ci": {"point": 0.712, "lo": 0.663, "hi": 0.758},
        "invalid_json_rate": 0.023,
        "failure_rates": {"invalid_json": 0.023},
        "band": "GREEN",
    }

    # When: the board-side gate record is built.
    gate = tc_json_conformance_gate(aggregate)

    # Then: web-ready fields are percentages and the band is recomputed, not trusted upstream.
    assert gate == {
        "id": "tc_json_v1",
        "label": "JSON tool-call gate",
        "band": "amber",
        "pass_rate": {"point": pytest.approx(71.2), "lo": pytest.approx(66.3), "hi": pytest.approx(75.8)},
        "invalid_json_rate": pytest.approx(2.3),
        "n_items": 330,
        "threshold_version": "tc_json_v1",
        "band_reasons": [],
    }


@pytest.mark.parametrize(
    ("raw_asr", "invalid_json_rate", "expected_band", "expected_reasons"),
    [
        (0.82, 0.16, "red", ["invalid_json>15"]),
        (0.59, 0.00, "red", ["pass<60"]),
        (0.80, 0.05, "green", []),
        (0.80, 0.051, "amber", ["invalid_json>5"]),
        (0.60, 0.00, "amber", []),
    ],
)
def test_tc_json_gate_recomputes_band_with_red_first_precedence(
    raw_asr: float,
    invalid_json_rate: float,
    expected_band: str,
    expected_reasons: list[str],
) -> None:
    # Given: upstream may stamp any string, including one contradicted by the canonical thresholds.
    aggregate = {
        "n": 100,
        "correct": int(raw_asr * 100),
        "raw_asr": raw_asr,
        "wilson_95_ci": {"point": raw_asr, "lo": raw_asr - 0.01, "hi": raw_asr + 0.01},
        "invalid_json_rate": invalid_json_rate,
        "failure_rates": {"invalid_json": invalid_json_rate},
        "band": "GREEN",
    }

    # When: the gate is mapped.
    gate = tc_json_conformance_gate(aggregate)

    # Then: red override wins before the green boundary is considered.
    assert gate["band"] == expected_band
    assert gate["band_reasons"] == expected_reasons


def test_board_attaches_tc_json_gate_without_changing_rank_or_composite(tmp_path: Path) -> None:
    # Given: a board fixture with a matching runs/tc-json/<run-stem>.json sidecar.
    paths = write_inputs(tmp_path, [source("Fixture Model", "fixture.json")])
    write_run(paths["runs"] / "fixture.json", run_record())
    tc_json_dir = paths["runs"] / "tc-json"
    baseline = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )
    baseline_model = objects_value(baseline["models"])[0]
    tc_json_dir.mkdir()
    (tc_json_dir / "fixture.json").write_text(
        json.dumps(
            {
                "aggregate": {
                    "n": 100,
                    "correct": 82,
                    "raw_asr": 0.82,
                    "wilson_95_ci": {"point": 0.82, "lo": 0.74, "hi": 0.88},
                    "invalid_json_rate": 0.18,
                    "failure_rates": {"invalid_json": 0.18},
                    "band": "GREEN",
                },
            },
        ),
        encoding="utf-8",
    )

    # When: the same board is built with the sidecar present.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: the gate is additive and does not alter ranking or score fields.
    model = objects_value(board["models"])[0]
    assert model["ranked"] is baseline_model["ranked"]
    assert object_value(model["composite"]) == object_value(baseline_model["composite"])
    assert object_value(model["axes"]) == object_value(baseline_model["axes"])
    gate = object_value(object_value(model["conformance_gates"])["tc_json_v1"])
    assert gate["band"] == "red"
    assert float_value(object_value(gate["pass_rate"])["point"]) == pytest.approx(82.0)
    system_gate = object_value(object_value(objects_value(model["systems"])[0]["conformance_gates"])["tc_json_v1"])
    assert system_gate == gate


def test_board_omits_tc_json_gate_when_sidecar_is_missing(tmp_path: Path) -> None:
    # Given: a board fixture with no runs/tc-json sidecar.
    paths = write_inputs(tmp_path, [source("Fixture Model", "fixture.json")])
    write_run(paths["runs"] / "fixture.json", run_record())

    # When: the board is built.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: absence is represented by omitting the gate key entirely.
    model = objects_value(board["models"])[0]
    assert "conformance_gates" not in model
    assert "conformance_gates" not in objects_value(model["systems"])[0]
