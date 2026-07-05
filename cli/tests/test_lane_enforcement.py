from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from board_fixtures import (
    FROZEN_AT,
    JsonObject,
    bool_value,
    object_value,
    objects_value,
    run_record,
    source,
    string_value,
    write_inputs,
    write_run,
)
from localbench.scoring.axes import AXES, Axis
from localbench.scoring.board_support import LANE_SCOPE


def _board(tmp_path: Path, sources: list[JsonObject]) -> JsonObject:
    from localbench.scoring.board import build_board

    paths = write_inputs(tmp_path, sources)
    for item in sources:
        file_name = string_value(item["file"])
        lane = string_value(item["reasoning_lane"])
        write_run(paths["runs"] / file_name, _exec_run_record(lane=lane))
    return build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )


def _exec_run_record(**kwargs: object) -> JsonObject:
    return run_record(
        lcb_correct=None,
        bigcode_correct=(True, False),
        math_correct=(True, False),
        **kwargs,
    )


def _models_by_label(board: JsonObject) -> dict[str, JsonObject]:
    return {string_value(model["model_label"]): model for model in objects_value(board["models"])}


def test_duplicate_catalog_id_across_scopes_dedupes_to_one_ranked_entry(tmp_path: Path) -> None:
    # Given: two headline-comparable rows in different curated families share one catalog id.
    catalog_id = "fixture/duplicate-model"
    sources = [
        source(
            "Duplicate Model A",
            "scope-a.json",
            family="Scope A",
            model_id=catalog_id,
            quant_label="Q4_K_M",
        ),
        source(
            "Duplicate Model B",
            "scope-b.json",
            family="Scope B",
            model_id=catalog_id,
            quant_label="Q5_K_M",
        ),
    ]

    # When: the board publishes model rows.
    board = _board(tmp_path, sources)

    # Then: the shared catalog id produces one family row and one ranked board entry.
    models = objects_value(board["models"])
    ranked = [model for model in models if bool_value(model["ranked"])]
    assert len(models) == 1
    assert len(ranked) == 1
    assert models[0]["catalog_id"] == catalog_id
    assert models[0]["n_runs"] == 2
    assert len(objects_value(models[0]["systems"])) == 2


@pytest.mark.parametrize("lane", ["answer-only", "api-uncapped"])
def test_non_headline_lanes_are_unranked_with_null_rank(tmp_path: Path, lane: str) -> None:
    # Given: a measured conformance-pass row outside the capped-thinking headline lane.
    sources = [source(f"{lane} Model", f"{lane}.json", lane=lane)]

    # When: the board is built through the scorer-side publish surface.
    board = _board(tmp_path, sources)

    # Then: non-headline lanes publish as unranked and carry no numeric rank.
    model = objects_value(board["models"])[0]
    assert model["lane"] == lane
    assert bool_value(model["ranked"]) is False
    assert model.get("rank") is None


def test_anchor_frontier_is_never_ranked_with_headline_conformance_and_axes(tmp_path: Path) -> None:
    # Given: an anchor/frontier row that otherwise satisfies lane, conformance, and axes.
    sources = [source("Anchor Model", "anchor.json", kind="anchor")]

    # When: the board is built through the real row scoring path.
    board = _board(tmp_path, sources)

    # Then: kind=anchor blocks ranking even with measured headline axes.
    model = objects_value(board["models"])[0]
    assert model["kind"] == "anchor"
    assert model["lane"] == LANE_SCOPE
    assert object_value(model["axes"])
    assert bool_value(model["ranked"]) is False
    assert model.get("rank") is None


def test_every_ranked_row_is_capped_thinking(tmp_path: Path) -> None:
    # Given: ranked, non-headline-lane, anchor, and conformance-fail candidate rows.
    from localbench.scoring.board import build_board

    sources = [
        source("Ranked Model", "ranked.json"),
        source("Answer Only Model", "answer-only.json", lane="answer-only"),
        source("Uncapped Model", "api-uncapped.json", lane="api-uncapped"),
        source("Anchor Model", "anchor.json", kind="anchor"),
        source("Failed Model", "failed.json"),
    ]
    paths = write_inputs(tmp_path, sources)
    write_run(paths["runs"] / "ranked.json", _exec_run_record())
    write_run(paths["runs"] / "answer-only.json", _exec_run_record(lane="answer-only"))
    write_run(paths["runs"] / "api-uncapped.json", _exec_run_record(lane="api-uncapped"))
    write_run(paths["runs"] / "anchor.json", _exec_run_record())
    write_run(paths["runs"] / "failed.json", _exec_run_record(conformance_status="failed"))

    # When: the board publishes all rows together.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: every ranked row is exactly in the capped-thinking scope.
    models = objects_value(board["models"])
    ranked = [model for model in models if bool_value(model["ranked"])]
    assert {string_value(model["model_label"]) for model in ranked} == {"Ranked Model"}
    assert all(model["lane"] == LANE_SCOPE for model in ranked)


def test_scorecard_id_changes_when_headline_weight_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the real scorecard function and a copied registry with one headline weight moved.
    import localbench.scoring.scorecard as scorecard_module

    base = scorecard_module.scorecard_identity()
    moved = tuple(replace(axis, weight=axis.weight + 0.01) if axis.key == "knowledge" else axis for axis in AXES)
    monkeypatch.setattr(scorecard_module, "AXES", moved)

    # When: the scorecard identity is recomputed from the changed registry.
    changed = scorecard_module.scorecard_identity()

    # Then: headline scoring changes move both the registry digest and scorecard id.
    assert changed["registry_digest"] != base["registry_digest"]
    assert changed["scorecard_id"] != base["scorecard_id"]


@pytest.mark.xfail(
    reason="Current scorecard hashes every Axis field, so adding a 0-weight candidate axis still changes scorecard_id.",
)
def test_scorecard_id_ignores_added_zero_weight_candidate_axis(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the real scorecard function and a copied registry with a new zero-weight candidate axis.
    import localbench.scoring.scorecard as scorecard_module

    base = scorecard_module.scorecard_identity()
    candidate_axis = Axis(
        "candidate_gap_probe",
        "Candidate Gap Probe",
        "candidate_gap_probe",
        ("candidate_gap_probe",),
        (),
        "candidate",
        0.0,
        False,
    )
    monkeypatch.setattr(scorecard_module, "AXES", (*AXES, candidate_axis))

    # When: the scorecard identity is recomputed from the candidate-only registry addition.
    changed = scorecard_module.scorecard_identity()

    # Then: a 0-weight candidate addition should not version the headline scorecard.
    assert changed["scorecard_id"] == base["scorecard_id"]


@pytest.mark.parametrize(
    ("model_id", "label"),
    [
        ("google/gemma-4-31b", "Gemma 4 31B"),
        ("qwen/qwen3-6-27b", "Qwen3 6 27B"),
    ],
)
def test_gemma_and_qwen_rows_obey_lane_scope_and_anchor_gate(
    tmp_path: Path,
    model_id: str,
    label: str,
) -> None:
    # Given: one model family is published through ranked, non-headline, and anchor gates.
    sources = [
        source(f"{label} Ranked", "ranked.json", model_id=f"{model_id}-ranked"),
        source(f"{label} Answer Only", "answer-only.json", lane="answer-only", model_id=f"{model_id}-answer"),
        source(f"{label} Uncapped", "api-uncapped.json", lane="api-uncapped", model_id=f"{model_id}-uncapped"),
        source(f"{label} Anchor", "anchor.json", kind="anchor", model_id=f"{model_id}-anchor"),
    ]

    # When: all variants are scored under the same board gate.
    board = _board(tmp_path, sources)

    # Then: only capped-thinking non-anchor rows are ranked.
    by_label = _models_by_label(board)
    assert bool_value(by_label[f"{label} Ranked"]["ranked"]) is True
    assert by_label[f"{label} Ranked"]["lane"] == LANE_SCOPE
    assert bool_value(by_label[f"{label} Answer Only"]["ranked"]) is False
    assert bool_value(by_label[f"{label} Uncapped"]["ranked"]) is False
    assert bool_value(by_label[f"{label} Anchor"]["ranked"]) is False
    ranked = [model for model in by_label.values() if bool_value(model["ranked"])]
    assert all(model["lane"] == LANE_SCOPE for model in ranked)
