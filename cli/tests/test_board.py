from __future__ import annotations

import json
from pathlib import Path

import pytest

from board_fixtures import (
    FROZEN_AT,
    assert_axis,
    assert_score,
    appworld_report,
    bool_value,
    float_value,
    object_value,
    objects_value,
    run_record,
    source,
    string_value,
    write_agentic,
    write_inputs,
    write_run,
)
from localbench.scoring.axes import web_composite_weights


def test_board_json_matches_index_schema_shape(tmp_path: Path) -> None:
    # Given: a curated capped-thinking run with headline axis measurements.
    from localbench.scoring.board import build_board

    paths = write_inputs(tmp_path, [source("Fixture Model", "fixture.json")])
    write_run(paths["runs"] / "fixture.json", run_record())

    # When: the scorer-side board is built.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: the output mirrors the IndexData/IndexModel contract plus v2 metadata.
    assert {"generated_note", "schema_version", "index_version", "suite_version"} <= set(board)
    assert {"scoring_version", "dataset_version", "lane_scope", "generated_at", "models", "manifest"} <= set(board)
    assert board["schema_version"] == "board-v2"
    assert board["scoring_version"] == "5"
    # The board's scope label is the live headline lane (bounded-final-v2), independent of
    # the legacy LANE_SCOPE constant that gates pre-v3 rows.
    assert board["lane_scope"] == "bounded-final-v2"
    manifest = object_value(board["manifest"])
    assert object_value(manifest["item_set_hashes"]) == {
        "ifbench.jsonl": "ifbench-items",
        "mmlu_pro.jsonl": "mmlu-items",
    }
    models = objects_value(board["models"])
    assert len(models) == 1
    model = models[0]
    assert {
        "slug",
        "model_label",
        "family",
        "kind",
        "best_run_id",
        "composite",
        "axes",
        "tier",
        "lane",
        "n_runs",
        "ranked",
        "tokens_to_answer_median",
        "est_cost_usd",
        "replicated",
        "score_status",
    } <= set(model)
    assert_score(object_value(model["composite"]))
    for axis in object_value(model["axes"]).values():
        assert_axis(object_value(axis))


def test_only_headline_lane_conformance_pass_measured_rows_are_ranked(tmp_path: Path) -> None:
    # Given: measured capped, measured anchor, answer-only, and conformance-fail rows.
    from localbench.scoring.board import build_board

    sources = [
        source("Ranked Model", "ranked.json"),
        source("Anchor Model", "anchor.json", kind="anchor"),
        source("Answer Only Model", "answer-only.json", lane="answer-only"),
        source("Failed Model", "failed.json"),
    ]
    paths = write_inputs(tmp_path, sources)
    write_run(
        paths["runs"] / "ranked.json",
        run_record(
            appworld_inline=(True, False),
            agentic_run=_inline_agentic_provenance((True, False)),
            tc_json_correct=(True, False),
            lcb_correct=None,
            bigcode_correct=(True, False),
            math_correct=(True, False),
        ),
    )
    write_run(paths["runs"] / "anchor.json", run_record())
    write_run(paths["runs"] / "answer-only.json", run_record(lane="answer-only"))
    write_run(paths["runs"] / "failed.json", run_record(conformance_status="failed"))

    # When: the board is built from all rows.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: only the community capped-thinking conformance-pass row is ranked.
    ranked_by_label = {
        string_value(model["model_label"]): bool_value(model["ranked"])
        for model in objects_value(board["models"])
    }
    assert ranked_by_label == {
        "Ranked Model": True,
        "Anchor Model": False,
        "Answer Only Model": False,
        "Failed Model": False,
    }


def test_v3_board_does_not_rank_legacy_lane_rows(tmp_path: Path) -> None:
    from localbench.scoring.board import build_board
    from localbench.scoring.board_scoring import INDEX_VERSION_V3

    paths = write_inputs(tmp_path, [source("Legacy Model", "legacy.json")])
    legacy = run_record()
    legacy["index_version"] = INDEX_VERSION_V3
    write_run(paths["runs"] / "legacy.json", legacy)

    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    model = objects_value(board["models"])[0]
    assert model["ranked"] is False


def test_v3_ranked_predicate_requires_allowlisted_profile_and_exact_audits(
    tmp_path: Path,
) -> None:
    from localbench.scoring.board import build_board

    paths = write_inputs(
        tmp_path,
        [
            source("Valid V3", "valid.json", lane="bounded-final-v2"),
            source("Unverified Budget", "unverified.json", lane="bounded-final-v2"),
            source("Bad Profile", "bad-profile.json", lane="bounded-final-v2"),
        ],
    )
    valid = _bounded_final_v3_run()
    unverified = _bounded_final_v3_run()
    object_value(unverified["budget_audit"])["status"] = "unverified"
    bad_profile = _bounded_final_v3_run()
    scorecard = object_value(object_value(bad_profile["manifest"])["scorecard"])
    scorecard["execution_profile_digest"] = "0" * 64
    write_run(paths["runs"] / "valid.json", valid)
    write_run(paths["runs"] / "unverified.json", unverified)
    write_run(paths["runs"] / "bad-profile.json", bad_profile)

    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    ranked_by_label = {
        string_value(model["model_label"]): bool_value(model["ranked"])
        for model in objects_value(board["models"])
    }
    assert ranked_by_label == {
        "Valid V3": True,
        "Unverified Budget": False,
        "Bad Profile": False,
    }


def test_v3_missing_suite_item_scores_zero_in_axis_denominator(tmp_path: Path) -> None:
    from localbench.scoring.board import build_board

    paths = write_inputs(tmp_path, [source("Missing Item", "missing.json", lane="bounded-final-v2")])
    run = _bounded_final_v3_run()
    run["items"] = [
        item
        for item in objects_value(run["items"])
        if not (item.get("bench") == "mmlu_pro" and item.get("id") == "mmlu_pro-2")
    ]
    object_value(run["suite_coverage"])["status"] = "incomplete"
    write_run(paths["runs"] / "missing.json", run)

    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    model = objects_value(board["models"])[0]
    knowledge = object_value(object_value(model["axes"])["knowledge"])
    assert knowledge["n"] == 2
    assert knowledge["raw_accuracy"] == pytest.approx(0.5)
    assert model["ranked"] is False


def test_composite_uses_registry_weighted_axis_combination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: registry weights are changed at the board boundary for this test.
    import localbench.scoring.board as board_module

    custom_weights = {"knowledge": 0.25, "instruction": 0.75, "math": 0.0, "agentic": 0.0}
    monkeypatch.setattr(board_module, "web_composite_weights", lambda: custom_weights)
    paths = write_inputs(tmp_path, [source("Weighted Model", "weighted.json")])
    write_run(paths["runs"] / "weighted.json", run_record(mmlu_correct=(True, True), if_correct=(False, False)))

    # When: the board computes the composite.
    board = board_module.build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: the point follows the registry weights, not a literal equal average.
    model = objects_value(board["models"])[0]
    composite = object_value(model["composite"])
    assert composite["point_raw"] == pytest.approx(custom_weights["knowledge"])
    assert composite["point_raw"] != pytest.approx(0.5)
    assert set(web_composite_weights()) >= {"knowledge", "instruction"}


def test_appworld_c_agentic_facet_contributes_to_tool_use_macro_axis(tmp_path: Path) -> None:
    # Given: a curated model with K/I run data and a separate AppWorld-C scored run1 file.
    from localbench.scoring.board import build_board
    from localbench.scoring.metadata import cluster_for_item, stratum_for_item

    paths = write_inputs(
        tmp_path,
        [source("Agentic Model", "agentic.json", agentic_file="appworld.scored.run1.json")],
    )
    write_run(
        paths["runs"] / "agentic.json",
        run_record(mmlu_correct=(True, True), if_correct=(False, False), appworld_inline=None),
    )
    write_agentic(paths["runs"] / "appworld.scored.run1.json", appworld_report((True, False, True, False)))

    # When: the scorer-side board is built through the public surface.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: AppWorld-C is a real agentic axis and the composite follows the registry weights.
    model = objects_value(board["models"])[0]
    axes = object_value(model["axes"])
    tool_use = object_value(axes["tool_use"])
    knowledge = object_value(axes["knowledge"])
    instruction = object_value(axes["instruction"])
    coding = object_value(axes["coding"])
    composite = object_value(model["composite"])
    weights = web_composite_weights()
    expected = (
        (weights["tool_use"] * float_value(tool_use["point_raw"]))
        + (weights["knowledge"] * float_value(knowledge["point_raw"]))
        + (weights["instruction"] * float_value(instruction["point_raw"]))
        + (weights["coding"] * float_value(coding["point_raw"]))
    ) / (weights["tool_use"] + weights["knowledge"] + weights["instruction"] + weights["coding"])
    assert tool_use["n"] == 6
    assert tool_use["raw_accuracy"] == pytest.approx(0.5)
    assert composite["point_raw"] == pytest.approx(expected)
    # AppWorld-C uses a SINGLE stratum + scenario cluster so the bootstrap resamples
    # scenarios (honest CI). Per-scenario strata (1-3 items each) collapse the variance.
    assert stratum_for_item("appworld_c", "calendar_17", {}) == "appworld_c"
    assert cluster_for_item("appworld_c", "calendar_17", {"cluster": "ignored"}) == "calendar"


def test_board_coding_axis_uses_sandbox_scoreable_items(tmp_path: Path) -> None:
    from localbench.scoring.board import build_board

    paths = write_inputs(tmp_path, [source("Coding Model", "coding.json")])
    run = run_record(appworld_inline=None, bigcode_correct=(True, True), lcb_correct=None)
    coding_rows = [
        item
        for item in objects_value(run["items"])
        if object_value(item)["bench"] == "bigcodebench_hard"
    ]
    for item, item_id in zip(coding_rows, ("bcbh-001", "bcbh-002"), strict=True):
        item["id"] = item_id
    coding_failure = dict(coding_rows[0])
    coding_failure["id"] = "bcbh-006"
    coding_failure["correct"] = False
    coding_failure["extracted"] = None
    run_items = run["items"]
    assert isinstance(run_items, list)
    run_items.append(coding_failure)
    object_value(object_value(run["benches"])["bigcodebench_hard"])["n_unscoreable"] = 1
    object_value(run["totals"])["n_items"] = 7
    write_run(paths["runs"] / "coding.json", run)

    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    model = objects_value(board["models"])[0]
    coding = object_value(object_value(model["axes"])["coding"])
    assert coding["n"] == 2
    assert coding["n_unscoreable"] == 1
    assert coding["raw_accuracy"] == pytest.approx(1.0)
    assert coding["point_raw"] == pytest.approx(1.0)


def test_board_emits_static_and_full_composites_without_changing_rank_composite(tmp_path: Path) -> None:
    # Given: one static-exec row and one full-exec row.
    from localbench.scoring.board import build_board

    paths = write_inputs(
        tmp_path,
        [
            source("Static Model", "static.json"),
            source("Full Model", "full.json"),
        ],
    )
    write_run(
        paths["runs"] / "static.json",
        run_record(
            appworld_inline=None,
            tc_json_correct=(True, False),
            lcb_correct=None,
            bigcode_correct=(True, True),
            math_correct=(True, False),
        ),
    )
    write_run(
        paths["runs"] / "full.json",
        run_record(
            appworld_inline=(True, False),
            tc_json_correct=(True, False),
            lcb_correct=None,
            bigcode_correct=(True, True),
            math_correct=(True, False),
        ),
    )

    # When: the board is built through the public board surface.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: additive static/full fields are present without changing the existing composite.
    rows = {string_value(model["model_label"]): model for model in objects_value(board["models"])}
    static_row = rows["Static Model"]
    static_axes = object_value(static_row["axes"])
    expected_static = (
        0.30 * float_value(object_value(static_axes["knowledge"])["point_raw"])
        + 0.30 * float_value(object_value(static_axes["instruction"])["point_raw"])
        + 0.30 * float_value(object_value(static_axes["coding"])["point_raw"])
        + 0.10 * float_value(object_value(static_axes["math"])["point_raw"])
    )
    weights = web_composite_weights()
    expected_headline_static = (
        weights["knowledge"] * float_value(object_value(static_axes["knowledge"])["point_raw"])
        + weights["instruction"] * float_value(object_value(static_axes["instruction"])["point_raw"])
        + weights["coding"] * float_value(object_value(static_axes["coding"])["point_raw"])
        + weights["math"] * float_value(object_value(static_axes["math"])["point_raw"])
    ) / (weights["knowledge"] + weights["instruction"] + weights["coding"] + weights["math"])
    assert object_value(static_row["composite_static"])["point_raw"] == pytest.approx(expected_static)
    assert static_row["static_index_version"] == "static-suite-v3"
    assert static_row["composite_full"] is None
    assert object_value(static_row["composite"])["point_raw"] == pytest.approx(expected_headline_static)

    full_row = rows["Full Model"]
    assert object_value(full_row["composite_static"])["point_raw"] == pytest.approx(expected_static)
    assert full_row["static_index_version"] == "static-suite-v3"
    assert object_value(full_row["composite_full"])["point_raw"] == pytest.approx(
        float_value(object_value(full_row["composite"])["point_raw"]),
    )


def test_inline_agentic_campaign_wins_over_sidecar(tmp_path: Path) -> None:
    # Given: a run with INLINE appworld_c (campaign mean 0.75) + agentic_run provenance, AND a curated
    # agentic_file sidecar reporting a DIFFERENT (lower) ASR of 0.25.
    from localbench.scoring.board import build_board

    campaign = _inline_agentic_provenance((True, True, True, False))
    paths = write_inputs(
        tmp_path,
        [source("Inline Agentic", "inline.json", agentic_file="appworld.scored.run1.json")],
    )
    write_run(
        paths["runs"] / "inline.json",
        run_record(
            mmlu_correct=(True, True),
            if_correct=(False, False),
            appworld_inline=(True, True, True, False),  # inline campaign mean = 0.75
            agentic_run=campaign,
        ),
    )
    # The sidecar reports a DIFFERENT, lower ASR (0.25) — it MUST be ignored in favour of inline.
    write_agentic(paths["runs"] / "appworld.scored.run1.json", appworld_report((True, False, False, False)))

    # When: the board is built.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: the macro-axis reflects the INLINE AppWorld facet, not the sidecar, and the campaign
    # provenance is surfaced on the row.
    model = objects_value(board["models"])[0]
    tool_use = object_value(object_value(model["axes"])["tool_use"])
    assert tool_use["n"] == 6
    assert tool_use["raw_accuracy"] == pytest.approx(11 / 17)
    provenance = object_value(model["agentic_run"])
    assert provenance["mean_asr"] == pytest.approx(0.75)
    assert provenance["campaign"] is True
    assert objects_value(provenance["runs"])


def test_inline_agentic_campaign_without_diagnostics_is_skipped(tmp_path: Path) -> None:
    # Given: a suspicious inline AppWorld-C row with score/items but no durable rerun diagnostics.
    from localbench.scoring.board import build_board

    stale_campaign = {
        "campaign": True,
        "single_pass": False,
        "asr_series": [0.0, 0.0],
        "mean_asr": 0.0,
        "max_abs_delta_pp": 0.0,
        "triggered_third_run": False,
        "subset_size": 2,
        "subset_hash": "deadbeefcafe",
        "stage": "scored",
    }
    paths = write_inputs(tmp_path, [source("Stale Inline Agentic", "inline-zero.json")])
    write_run(
        paths["runs"] / "inline-zero.json",
        run_record(
            mmlu_correct=(True, True),
            if_correct=(True, True),
            appworld_inline=(False, False),
            agentic_run=stale_campaign,
        ),
    )

    # When: the board is built.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: the row is quarantined instead of ranked as a clean measured zero.
    assert objects_value(board["models"]) == []
    skipped = objects_value(object_value(board["manifest"])["skipped_runs"])
    inline_skip = next(skip for skip in skipped if skip["file"] == "inline-zero.json")
    assert "inline appworld_c is missing durable agentic diagnostics" in string_value(inline_skip["reason"])


def test_inline_agentic_campaign_with_harness_dominated_diagnostics_is_skipped(tmp_path: Path) -> None:
    # Given: an inline AppWorld-C row whose persisted diagnostics show no model task attempt landed.
    from localbench.scoring.board import build_board

    paths = write_inputs(tmp_path, [source("Harness Agentic", "inline-harness.json")])
    write_run(
        paths["runs"] / "inline-harness.json",
        run_record(
            mmlu_correct=(True, True),
            if_correct=(True, True),
            appworld_inline=(False, False),
            agentic_run=_inline_agentic_provenance((False, False), harness_dominated=True),
        ),
    )

    # When: the board is built.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: the row is quarantined instead of ranked as a valid agentic zero.
    assert objects_value(board["models"]) == []
    skipped = objects_value(object_value(board["manifest"])["skipped_runs"])
    inline_skip = next(skip for skip in skipped if skip["file"] == "inline-harness.json")
    assert "inline appworld_c diagnostics are harness dominated" in string_value(inline_skip["reason"])


def test_tool_use_axis_surfaces_from_complete_inline_facets(tmp_path: Path) -> None:
    # Given: a run carrying the inline tc_json_v1 bench (Stage 3b tool-calling axis).
    from localbench.scoring.board import build_board

    paths = write_inputs(tmp_path, [source("Tool Model", "tool.json")])
    write_run(
        paths["runs"] / "tool.json",
        run_record(tc_json_correct=(True, True, False, True)),  # tool-calling raw = 0.75
    )

    # When: the board is built.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: tool_use surfaces from both headline facets with declared weights.
    model = objects_value(board["models"])[0]
    axes = object_value(model["axes"])
    assert "tool_use" in axes
    tool = object_value(axes["tool_use"])
    assert_axis(tool)
    assert tool["n"] == 4
    assert tool["raw_accuracy"] == pytest.approx(0.5)


def test_missing_gemma_run_is_skipped_gracefully(tmp_path: Path) -> None:
    # Given: the curation asks for a missing Gemma file plus one valid Qwen file.
    from localbench.scoring.board import build_board

    sources = [
        source("Qwen Model", "qwen.json"),
        source("Gemma 4 31B IT", "ladder-gemma4-31b-Q4_K_M.json", model_id="google/gemma-4-31B-it"),
    ]
    paths = write_inputs(tmp_path, sources)
    write_run(paths["runs"] / "qwen.json", run_record())

    # When: the board is built.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: the valid row remains and the absent Gemma row is omitted.
    labels = {string_value(model["model_label"]) for model in objects_value(board["models"])}
    assert labels == {"Qwen Model"}


def test_agentic_only_curation_sources_without_core_text_file_are_skipped(tmp_path: Path) -> None:
    # Given: a valid Core Text source plus agentic-only distill sources with no boardable run.
    from localbench.scoring.board import build_board

    agentic_null_file = source("Qwopus Distill", "placeholder.json", agentic_file="agentic/qwopus.json")
    agentic_null_file["file"] = None
    agentic_missing_file = source("Qwable Distill", "placeholder.json")
    del agentic_missing_file["file"]
    paths = write_inputs(
        tmp_path,
        [
            source("Qwen Model", "qwen.json"),
            agentic_null_file,
            agentic_missing_file,
        ],
    )
    write_run(paths["runs"] / "qwen.json", run_record())

    # When: the board is built from mixed Core Text and agentic-only curation.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    # Then: only rows with a Core Text run are eligible for the board.
    labels = {string_value(model["model_label"]) for model in objects_value(board["models"])}
    assert labels == {"Qwen Model"}


def test_parity_check_accepts_matching_web_index_points(tmp_path: Path) -> None:
    # Given: a generated board and a minimal web index with matching measured points.
    from localbench.scoring.board import build_board, check_board_parity

    paths = write_inputs(tmp_path, [source("Fixture Model", "fixture.json")])
    write_run(paths["runs"] / "fixture.json", run_record())
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )
    model = objects_value(board["models"])[0]
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps({"generated_note": "fixture", "index_version": "index-v2.1", "suite_version": "suite-v1", "models": [model]}),
        encoding="utf-8",
    )

    # When: parity compares score objects against score objects.
    result = check_board_parity(board, index_path=index_path)

    # Then: no false divergence is reported.
    assert result.checked is True
    assert result.divergences == ()


def test_family_row_emits_best_first_systems_with_curated_recommended_quant(tmp_path: Path) -> None:
    # Given: one family has a Q6/Q4 plateau and Q4 is the curated value pick.
    from localbench.scoring.board import build_board, check_board_parity

    sources = [
        source("Plateau Model", "q6.json", family="Plateau", model_id="plateau/model", quant_label="Q6_K"),
        source(
            "Plateau Model",
            "q4.json",
            family="Plateau",
            model_id="plateau/model",
            quant_label="Q4_K_M",
            recommended=True,
        ),
        source("Plateau Model", "q3.json", family="Plateau", model_id="plateau/model", quant_label="Q3_K_M"),
    ]
    paths = write_inputs(tmp_path, sources)
    plateau_correct = (True, True, True, True, False)
    lower_correct = (True, True, False, False, False)
    write_run(paths["runs"] / "q6.json", run_record(mmlu_correct=plateau_correct, if_correct=plateau_correct))
    write_run(paths["runs"] / "q4.json", run_record(mmlu_correct=plateau_correct, if_correct=plateau_correct))
    write_run(paths["runs"] / "q3.json", run_record(mmlu_correct=lower_correct, if_correct=lower_correct))

    # When: the scorer-side board is built and compared to a family-level web index row.
    board = build_board(
        runs_dir=paths["runs"],
        curation_path=paths["curation"],
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )
    model = objects_value(board["models"])[0]
    index_model = dict(model)
    index_model.pop("systems")
    index_model.pop("best_system_run_id")
    index_model.pop("recommended_system_run_id")
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps({"models": [index_model]}), encoding="utf-8")
    result = check_board_parity(board, index_path=index_path)

    # Then: the family row is still singular, ranked by best, with quant systems attached.
    systems = objects_value(model["systems"])
    assert len(objects_value(board["models"])) == 1
    assert len(systems) == 3
    assert model["n_runs"] == 3
    assert model["best_run_id"] == "plateau-model__q6"
    assert model["best_system_run_id"] == "plateau-model__q6"
    assert model["recommended_system_run_id"] == "plateau-model__q4"
    assert [system["quant_label"] for system in systems] == ["Q6_K", "Q4_K_M", "Q3_K_M"]
    assert [system["run_id"] for system in systems] == ["plateau-model__q6", "plateau-model__q4", "plateau-model__q3"]
    assert [bool_value(system["is_best"]) for system in systems] == [True, False, False]
    assert [bool_value(system["is_recommended"]) for system in systems] == [False, True, False]
    assert all(system["n_runs"] == 1 for system in systems)
    assert float_value(object_value(systems[0]["composite"])["point_raw"]) == pytest.approx(
        float_value(object_value(systems[1]["composite"])["point_raw"]),
    )
    assert float_value(object_value(systems[2]["composite"])["point_raw"]) < float_value(
        object_value(systems[1]["composite"])["point_raw"],
    )
    assert result.checked is True
    assert result.divergences == ()


def test_board_rejects_multiple_recommended_quants_in_one_family(tmp_path: Path) -> None:
    # Given: two quants in the same family are curated as recommended.
    from localbench.scoring.board import BoardBuildError, build_board

    sources = [
        source("Duplicate Model", "q6.json", family="Duplicate", model_id="duplicate/model", quant_label="Q6_K", recommended=True),
        source("Duplicate Model", "q4.json", family="Duplicate", model_id="duplicate/model", quant_label="Q4_K_M", recommended=True),
    ]
    paths = write_inputs(tmp_path, sources)
    write_run(paths["runs"] / "q6.json", run_record())
    write_run(paths["runs"] / "q4.json", run_record())

    # When/Then: board generation rejects the ambiguous recommendation.
    with pytest.raises(BoardBuildError, match="at most one recommended"):
        build_board(
            runs_dir=paths["runs"],
            curation_path=paths["curation"],
            generated_at=FROZEN_AT,
            bootstrap_iters=50,
        )


def _inline_agentic_provenance(successes: tuple[bool, ...], *, harness_dominated: bool = False) -> dict[str, object]:
    n = len(successes)
    succeeded = sum(1 for success in successes if success)
    asr = succeeded / n if n else 0.0
    outcome_counts = {
        "success": 0 if harness_dominated else succeeded,
        "failure": 0 if harness_dominated else n - succeeded,
        "cap_exceeded": n if harness_dominated else 0,
        "no_final_answer": 0,
        "harness_error": 0,
    }
    diagnostics = {
        "tasks_total": n,
        "tasks_succeeded": 0 if harness_dominated else succeeded,
        "agentic_success_rate": 0.0 if harness_dominated else asr,
        "asr_excluding_infra": 0.0 if harness_dominated else asr,
        "collateral_damage_rate": 0.0,
        "cap_exceeded_rate": 1.0 if harness_dominated else 0.0,
        "no_final_answer_rate": 0.0,
        "harness_error_rate": 0.0,
        "infra_timeout_rate": 0.0,
        "infra_sandbox_rate": 0.0,
        "model_failure_rate": (n - succeeded) / n if n else 0.0,
        "model_no_progress_rate": 0.0,
        "harness_error_subclass_rate": 0.0,
        "format_failure_rate": 0.0,
        "syntax_error_rate": 0.0,
        "runtime_error_rate": 0.0,
        "observation_truncation_rate": 0.0,
        "api_docs_usage_rate": 0.0,
        "mean_turns_used": 1.0,
        "mean_blocks_run": 1.0,
        "mean_api_calls": 0.0,
        "mean_output_tokens": 1.0,
        "outcome_counts": outcome_counts,
    }
    return {
        "campaign": True,
        "single_pass": False,
        "asr_series": [asr, asr],
        "mean_asr": asr,
        "max_abs_delta_pp": 0.0,
        "triggered_third_run": False,
        "subset_size": n,
        "subset_hash": "deadbeefcafe",
        "stage": "scored",
        "diagnostics": diagnostics,
        "runs": [
            {"run_index": 1, "results_path": "agentic/inline.scored.run1.json", **diagnostics},
            {"run_index": 2, "results_path": "agentic/inline.scored.run2.json", **diagnostics},
        ],
    }


def _bounded_final_v3_run() -> dict:
    from localbench.lane_spec import BOUNDED_FINAL_V2_LANE_SPEC_ID
    from localbench.scoring.board_scoring import INDEX_VERSION_V3
    from localbench.scoring.scorecard import scorecard_identity

    record = run_record(
        lane=BOUNDED_FINAL_V2_LANE_SPEC_ID,
        lcb_correct=None,
        bigcode_correct=(True, False),
        math_correct=(True, False),
    )
    record["index_version"] = INDEX_VERSION_V3
    manifest = object_value(record["manifest"])
    suite = object_value(manifest["suite"])
    suite["lane"] = BOUNDED_FINAL_V2_LANE_SPEC_ID
    suite["tier"] = "standard"
    manifest["scorecard"] = scorecard_identity(
        "answer_only_v1",
        lane_spec_id=BOUNDED_FINAL_V2_LANE_SPEC_ID,
    )
    record["prompt_audit"] = {"status": "canonical"}
    record["budget_audit"] = {"status": "exact"}
    record["sampler_audit"] = {"status": "deterministic"}
    record["suite_coverage"] = {"status": "complete"}
    return record
