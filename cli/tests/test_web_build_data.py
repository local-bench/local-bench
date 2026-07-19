from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Final, TypeAlias

import pytest

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

ROOT = Path(__file__).resolve().parents[2]
DATA_SOURCES = ROOT / "web" / "data_sources.json"
DATA_DIR = ROOT / "web" / "public" / "data"
AXES: Final = ("knowledge", "instruction", "agentic", "math")
SOURCE_BENCHES: Final = ("mmlu_pro", "ifbench", "bfcl", "olymmath_hard", "amo")
SOURCE_BENCH_GROUPS_BY_AXIS: Final = {
    "knowledge": (("mmlu_pro",), ("supergpqa",)),
    "instruction": (("ifbench",),),
    "agentic": (("bfcl",),),
    "math": (("olymmath_hard", "amo"),),
}
SOURCE_CHANCE_BASELINES: Final = {
    "mmlu_pro": 0.10918253968253969,
    "supergpqa": 0.1,
}
FROZEN_WEB_WEIGHTS: Final = {
    "knowledge": 0.15,
    "instruction": 0.15,
    "agentic": 0.40,
    "math": 0.05,
}
QWEN_RUN_STEMS: Final = (
    "lcpp-q8_0",
    "lcpp-q6_k",
    "lcpp-q4_k_m",
    "lcpp-q3_k_m",
    "lcpp-q2_k",
)


def test_build_data_when_sources_are_curated_emits_deterministic_static_json(
    tmp_path: Path,
) -> None:
    # Decoupled from the live web/data_sources.json (which legitimately evolves as the
    # board grows) so this stays a stable determinism + contract test. The fixture
    # mirrors the post-drop-synthesis reality: a Knowledge+Instruction-only run (no
    # math/agentic measured) alongside a run that also measures math.
    builder = _build_data_module()
    ki_run = tmp_path / "ki-run.json"
    math_run = tmp_path / "math-run.json"
    ki_run.write_text(
        json.dumps(
            _synthetic_run(
                [
                    _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
                    _synthetic_item("mmlu-pro-002", "mmlu_pro", False, category="biology", template="mcq-b"),
                    _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
                    _synthetic_item("ifbench-002", "ifbench", None, template="format-list"),
                ],
            ),
        ),
        encoding="utf-8",
    )
    math_run.write_text(
        json.dumps(
            _synthetic_run(
                [
                    _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
                    _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
                    _synthetic_item("olymmath-hard-001", "olymmath_hard", True, category="geometry", template="proof"),
                    _synthetic_item("amo-001", "amo", False, category="number-theory", template="short-answer"),
                ],
            ),
        ),
        encoding="utf-8",
    )
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "family": "Fixture-KI",
                    "file": str(ki_run),
                    "kind": "anchor",
                    "origin": "project_anchor",
                    "model_label": "Fixture KI",
                    "quant_label": "Q4_K_M",
                    "reasoning_lane": "answer-only",
                    "vram_footprint_gb": 16.55,
                },
                {
                    "family": "Fixture-Math",
                    "file": str(math_run),
                    "kind": "anchor",
                    "origin": "project_anchor",
                    "model_label": "Fixture Math",
                    "quant_label": "Q8_0",
                    "reasoning_lane": "capped-thinking",
                    "vram_footprint_gb": 28.6,
                },
            ],
        ),
        encoding="utf-8",
    )

    # When the pipeline builds the static surface twice with the fixed bootstrap seed.
    out_first = tmp_path / "out-first"
    out_second = tmp_path / "out-second"
    builder.build_static_data(sources, out_first, iters=300)
    builder.build_static_data(sources, out_second, iters=300)

    # Then the emitted JSON surface is complete and byte-for-byte deterministic.
    assert _read_outputs(out_first) == _read_outputs(out_second)
    index = _object(_read_json(out_first / "index.json"))
    assert set(index) == {"generated_note", "index_version", "models", "suite_version"}
    assert _string(index["suite_version"]) == "suite-v1"
    models = _objects(index["models"])
    # The full model catalog is always emitted (unmeasured entries are shells with empty
    # axes / null composite); our two fixture runs attach as standalone measured entries.
    measured = [model for model in models if model.get("score_status") == "measured"]
    assert {_string(model["model_label"]) for model in measured} >= {"Fixture KI", "Fixture Math"}

    # Contract: every MEASURED model's axes ⊆ AXES with the headline always present;
    # candidate axes (math/agentic) appear only when actually measured (no synthesis).
    # Both fixture runs sit outside the board's headline lane, so their composites are
    # structurally quarantined: `composite` is null and the score only appears as
    # `diagnostic_composite`.
    for model in measured:
        model_axes = _object(model["axes"])
        assert set(model_axes) <= set(AXES)
        assert {"knowledge", "instruction"} <= set(model_axes)
        assert model["composite"] is None
        _assert_interval(_object(model["diagnostic_composite"]))
        assert (out_first / "models" / f"{_string(model['slug'])}.json").exists()

    # The K+I-only run carries NO fabricated math/agentic axes...
    ki_model = _model_by_label(models, "Fixture KI")
    assert set(_object(ki_model["axes"])) == {"knowledge", "instruction"}
    # ...while the run that measured math legitimately surfaces a measured math axis only.
    math_model = _model_by_label(models, "Fixture Math")
    assert "math" in set(_object(math_model["axes"]))
    assert "agentic" not in set(_object(math_model["axes"]))

    # Every measured run detail honors the same contract (well-formed intervals, no n=0 axes).
    for model in (ki_model, math_model):
        detail = _object(_read_json(out_first / "models" / f"{_string(model['slug'])}.json"))
        runs = _objects(detail["runs"])
        assert runs
        for run_row in runs:
            run_id = _string(run_row["run_id"])
            run_detail = _object(_read_json(out_first / "runs" / f"{run_id}.json"))
            assert _string(run_detail["suite_version"]) == "suite-v1"
            _assert_run_detail(run_detail)
            assert run_detail["composite"] is None
            _assert_interval(_object(run_detail["diagnostic_composite"]))
            assert _string(run_detail["score_status"]) == "measured"
            assert _string(run_detail["lane"]) in {"answer-only", "capped-thinking"}


def test_untrusted_catalog_collision_cannot_mutate_protected_build_outputs(tmp_path: Path) -> None:
    builder = _build_data_module()
    catalog_raw = _read_json(ROOT / "web" / "model_catalog.json")
    target = _objects(_object(catalog_raw)["models"])[0]
    target_id = _string(target["id"])
    target_slug = _string(target["slug"])
    quants = _objects(target["quants"])
    quant_label = _string(quants[0]["label"]) if quants else "Q4_K_M"

    empty_sources = tmp_path / "empty.json"
    empty_sources.write_text("[]", encoding="utf-8")
    baseline = tmp_path / "baseline"
    builder.build_static_data(empty_sources, baseline, iters=10)

    run_path = tmp_path / "adversary-run.json"
    run_path.write_text(json.dumps(_synthetic_run([
        _synthetic_item("mmlu-pro-001", "mmlu_pro", True),
        _synthetic_item("ifbench-001", "ifbench", True),
    ])), encoding="utf-8")
    attacked_sources = tmp_path / "attacked.json"
    attacked_sources.write_text(json.dumps([{
        "family": "Adversary",
        "file": str(run_path),
        "kind": "community",
        "model_id": target_id,
        "model_label": "Injected community run",
        "quant_label": quant_label,
        "reasoning_lane": "answer-only",
        "trust_label": "community_self_submitted",
        "vram_footprint_gb": 1,
    }]), encoding="utf-8")
    attacked = tmp_path / "attacked"
    builder.build_static_data(attacked_sources, attacked, iters=10)

    assert (attacked / "index.json").read_bytes() == (baseline / "index.json").read_bytes()
    assert (attacked / "models" / f"{target_slug}.json").read_bytes() == (baseline / "models" / f"{target_slug}.json").read_bytes()
    assert list((attacked / "runs").glob("*.json")) == []


def test_no_origin_community_source_is_excluded_from_every_protected_output(tmp_path: Path) -> None:
    builder = _build_data_module()
    run_path = tmp_path / "community-run.json"
    run_path.write_text(json.dumps(_synthetic_run([
        _synthetic_item("mmlu-pro-001", "mmlu_pro", True),
        _synthetic_item("ifbench-001", "ifbench", True),
    ])), encoding="utf-8")
    sources = tmp_path / "community-sources.json"
    sources.write_text(json.dumps([{
        "family": "Untrusted",
        "file": str(run_path),
        "kind": "community",
        "model_label": "No Origin Community",
        "quant_label": "Q4_K_M",
        "reasoning_lane": "answer-only",
        "vram_footprint_gb": 1,
    }]), encoding="utf-8")
    out = tmp_path / "out"
    builder.build_static_data(sources, out, iters=10)

    index = _object(_read_json(out / "index.json"))
    assert all(row.get("model_label") != "No Origin Community" for row in _objects(index["models"]))
    assert list((out / "runs").glob("*.json")) == []
    assert all("no-origin-community" not in path.name for path in (out / "models").glob("*.json"))


def test_build_data_when_error_or_no_answer_items_are_scored_as_incorrect(tmp_path: Path) -> None:
    # Given a synthetic run whose stored chance-corrected and raw-accuracy values are stale.
    builder = _build_data_module()
    paths = _write_synthetic_pipeline_inputs(
        tmp_path,
        [
            _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
            _synthetic_item("mmlu-pro-002", "mmlu_pro", False, category="biology", template="mcq-b"),
            _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
            _synthetic_item("ifbench-002", "ifbench", None, template="format-list"),
            _synthetic_item("bfcl-001", "bfcl", True, category="tool-use", template="single-call"),
            _synthetic_item("bfcl-002", "bfcl", False, category="tool-use", template="multi-call"),
            _synthetic_item("olymmath-hard-001", "olymmath_hard", True, category="geometry", template="proof"),
            _synthetic_item(
                "olymmath-hard-002",
                "olymmath_hard",
                False,
                category="algebra",
                template="construction",
                error="ResponseParseError: missing content",
            ),
            _synthetic_item("amo-001", "amo", True, category="number-theory", template="short-answer"),
            _synthetic_item("amo-002", "amo", False, category="combinatorics", template="counting"),
        ],
    )
    run = _object(_read_json(paths["run"]))
    _object(_object(run["benches"])["mmlu_pro"])["raw_accuracy"] = 0.55
    paths["run"].write_text(json.dumps(run), encoding="utf-8")

    # When the web data pipeline builds static JSON from scored items.
    builder.build_static_data(paths["sources"], paths["out"], iters=300)

    # Then point estimates and CIs count errors/no-answers as incorrect.
    detail = _only_run_detail(paths["out"])
    axes = _object(detail["axes"])
    knowledge = _object(axes["knowledge"])
    instruction = _object(axes["instruction"])
    math = _object(axes["math"])
    composite = _score_interval(detail)
    chance = SOURCE_CHANCE_BASELINES["mmlu_pro"]
    assert knowledge["point_raw"] == pytest.approx((0.5 - chance) / (1.0 - chance))
    assert instruction["point_raw"] == pytest.approx(0.5)
    assert instruction["raw_accuracy"] == pytest.approx(0.5)
    assert instruction["hi_raw"] < 1.0
    assert instruction["n_no_answer"] == 1
    assert math["point_raw"] == pytest.approx(0.5)
    assert math["hi_raw"] < 1.0
    assert math["n_errors"] == 1
    # Composite is HEADLINE-only: knowledge, instruction, and math are measured here.
    assert composite["point_raw"] == pytest.approx(
        ((0.15 * ((0.5 - chance) / (1.0 - chance))) + (0.15 * 0.5) + (0.05 * 0.5)) / 0.35,
    )
    assert isinstance(detail["data_warnings"], list)
    assert any(
        "knowledge chance_corrected differs" in warning
        for warning in _strings(detail["data_warnings"])
    )


def test_build_data_coding_axis_uses_sandbox_scoreable_denominator(tmp_path: Path) -> None:
    builder = _build_data_module()
    run_path = tmp_path / "coding-run.json"
    sources_path = tmp_path / "sources.json"
    out_dir = tmp_path / "out"
    run = _synthetic_run(
        [
            _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
            _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
        ],
    )
    coding_items = [
        _synthetic_item("bcbh-001", "bigcodebench_hard", True, template="exec"),
        _synthetic_item("bcbh-002", "bigcodebench_hard", True, template="exec"),
        _synthetic_item("bcbh-006", "bigcodebench_hard", False, template="exec"),
    ]
    run_items = run["items"]
    assert isinstance(run_items, list)
    run_items.extend(coding_items)
    _object(run["benches"])["bigcodebench_hard"] = {
        "n": 2,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "n_unscoreable": 1,
        "raw_accuracy": 1.0,
        "chance_corrected": 1.0,
    }
    _object(run["totals"])["n_items"] = 5
    run_path.write_text(json.dumps(run), encoding="utf-8")
    sources_path.write_text(
        json.dumps(
            [
                {
                    "family": "Synthetic",
                    "file": str(run_path),
                    "independent_replication": False,
                    "kind": "anchor",
                    "origin": "project_anchor",
                    "model_label": "Coding Synthetic",
                    "quant_label": None,
                    "reasoning_lane": "test",
                    "vram_footprint_gb": None,
                },
            ],
        ),
        encoding="utf-8",
    )

    builder.build_static_data(sources_path, out_dir, iters=300)

    detail = _only_run_detail(out_dir)
    coding = _object(_object(detail["axes"])["coding"])
    assert coding["n"] == 2
    assert coding["n_unscoreable"] == 1
    assert coding["raw_accuracy"] == pytest.approx(1.0)
    assert coding["lo_raw"] == pytest.approx(1.0)
    assert coding["hi_raw"] == pytest.approx(1.0)
    assert not any(
        "coding chance_corrected differs" in warning
        for warning in _strings(detail["data_warnings"])
    )


def test_build_data_diagnostics_follow_protocol_manifest() -> None:
    builder = _build_data_module()
    protocol = _object(_read_json(ROOT / "protocol" / "index-v4.2.json"))

    assert builder.SEASON_2_INDEX_VERSION == "index-v4.2"
    assert builder._DIAGNOSTIC_SOURCE_GROUPS == {
        _string(diagnostic["key"]): ((_string(diagnostic["bench"]),),)
        for diagnostic in _objects(protocol["diagnostics"])
    }


def test_ranked_coding_provenance_guard_blocks_self_reported_coding() -> None:
    # Enforce "community/self-reported coding never ranks" IN CODE. A ranked row whose composite
    # includes the CODING AXIS must be maintainer-verified (trust_label project_anchor AND
    # verdict_source verifier); anything else is a build-time failure. Keyed on the scored axis,
    # NOT has_code_artifacts: coding is scored from bench aggregates independent of any
    # code_artifact, so an artifact-keyed guard is bypassable
    # (docs/reports/coding-exec-framewalk-forgery-2026-07-07.md).
    builder = _build_data_module()

    CODING: JsonObject = {"coding": {"n": 1}}  # a scored coding axis; contents irrelevant to the guard

    def _run(run_id: str, *, axes: JsonObject = CODING, **index_row: JsonValue) -> JsonObject:
        return {"run_id": run_id, "index_row": {"axes": axes, **index_row}}

    # Legit maintainer-verified ranked coding row: must NOT raise.
    builder._assert_ranked_coding_provenance(
        [_run("legit", ranked=True, trust_label="project_anchor", verdict_source="verifier")]
    )

    # Ranked rows whose coding axis is scored but NOT maintainer-verified: must raise.
    for label, row in {
        "community_trust_label": _run("a", ranked=True, trust_label="community_re_scored", verdict_source="verifier"),
        "forged_submitter_source": _run("b", ranked=True, trust_label="project_anchor", verdict_source="submitter"),
        "null_source": _run("c", ranked=True, trust_label="project_anchor", verdict_source=None),
        # The bypass this closes: coding axis scored with NO code_artifact (has_code_artifacts
        # false, verdict_source None). The old has_code_artifacts-keyed guard skipped this.
        "coding_scored_without_artifact": _run("d", ranked=True, has_code_artifacts=False, trust_label="community_re_scored", verdict_source=None),
        "no_provenance_at_all": _run("e", ranked=True),
        "untrusted_static_index": _run(
            "static",
            ranked=False,
            composite_static={"point": 50.0},
            static_index_version="static-suite-v2",
            tier="standard",
            conformance_status="headline-comparable",
            trust_label="community_re_scored",
            verdict_source="submitter",
        ),
    }.items():
        with pytest.raises(builder.DataBuildError, match="not maintainer-verified"):
            builder._assert_ranked_coding_provenance([row])

    # Non-triggering rows must NOT raise: an unranked self-reported coding row, and a ranked row
    # whose composite has NO coding axis (provenance is irrelevant when coding is not scored).
    builder._assert_ranked_coding_provenance(
        [
            _run("unranked", ranked=False, trust_label="community_re_scored", verdict_source="submitter"),
            _run("nocode", axes={"knowledge": {"n": 1}}, ranked=True, trust_label="community_re_scored", verdict_source=None),
        ]
    )


def test_lineage_gate_blocks_ranked_measured_row_without_catalog_entry() -> None:
    builder = _build_data_module()
    runs = [_gate_run("local-finetune", catalog_id=None, ranked=True)]
    catalog = [_gate_catalog_entry("Base/Model", "base-model")]

    with pytest.raises(builder.DataBuildError, match="LINEAGE GATE failed") as excinfo:
        builder._enforce_integrity_gates(runs, catalog, allow_lineage_gaps=False)

    message = str(excinfo.value)
    assert "measured row without catalog entry: slug=local-finetune" in message
    assert "Pass --allow-lineage-gaps to downgrade this failure to a warning." in message


def test_lineage_gate_blocks_missing_catalog_base_chain() -> None:
    builder = _build_data_module()
    runs = [_gate_run("missing-base-tune", catalog_id="Tune/Missing-Base", ranked=True)]
    catalog = [
        _gate_catalog_entry(
            "Tune/Missing-Base",
            "missing-base-tune",
            base_model="Base/Missing",
            model_kind="finetune",
        )
    ]

    with pytest.raises(builder.DataBuildError, match="LINEAGE GATE failed") as excinfo:
        builder._enforce_integrity_gates(runs, catalog, allow_lineage_gaps=False)

    assert (
        "base-chain-missing: slug=missing-base-tune catalog_id=Tune/Missing-Base "
        "base_model=Base/Missing missing=Base/Missing"
    ) in str(excinfo.value)


def test_integrity_gates_pass_clean_catalogued_lineage(capsys: pytest.CaptureFixture[str]) -> None:
    builder = _build_data_module()
    runs = [_gate_run("clean-tune", catalog_id="Tune/Clean", ranked=True, quant_label="Q4_K_M", vram_footprint_gb=10.2)]
    catalog = [
        _gate_catalog_entry("Base/Clean", "base-clean"),
        _gate_catalog_entry(
            "Tune/Clean",
            "clean-tune",
            base_model="Base/Clean",
            model_kind="finetune",
            quants=[{"label": "Q4_K_M", "file_gb": 10.0}],
        ),
    ]

    builder._enforce_integrity_gates(runs, catalog, allow_lineage_gaps=False)

    assert capsys.readouterr().err == ""


def test_allow_lineage_gaps_downgrades_lineage_gate_to_warning(capsys: pytest.CaptureFixture[str]) -> None:
    builder = _build_data_module()
    runs = [_gate_run("local-finetune", catalog_id=None, ranked=True)]

    builder._enforce_integrity_gates(runs, [], allow_lineage_gaps=True)

    captured = capsys.readouterr()
    assert "LINEAGE GATE warning (--allow-lineage-gaps):" in captured.err
    assert "measured row without catalog entry: slug=local-finetune" in captured.err


def test_size_gate_warns_when_measured_artifact_size_diverges_from_catalog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    builder = _build_data_module()
    runs = [_gate_run("large-drift", catalog_id="Drift/Model", ranked=True, quant_label="Q4_K_M", vram_footprint_gb=12.5)]
    catalog = [
        _gate_catalog_entry(
            "Drift/Model",
            "large-drift",
            quants=[{"label": "Q4_K_M", "file_gb": 10.0}],
        )
    ]

    builder._enforce_integrity_gates(runs, catalog, allow_lineage_gaps=False)

    captured = capsys.readouterr()
    assert (
        "SIZE GATE warning:\n"
        "- slug=large-drift run_id=large-drift__run quant=Q4_K_M: "
        "measured vram_footprint_gb=12.5 (model row vram_footprint_gb from web/data_sources.json) "
        "vs catalog file_gb=10 (web/model_catalog.json quants[].file_gb), delta=25.0%"
    ) in captured.err


def test_build_data_main_passes_allow_lineage_gaps_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _build_data_module()
    sources = tmp_path / "sources.json"
    sources.write_text("[]", encoding="utf-8")
    out_dir = tmp_path / "generated"
    captured_allow: list[bool] = []

    def fake_build_static_data(
        sources_path: Path,
        output_dir: Path,
        *,
        iters: int = 0,
        benches: tuple[str, ...] = (),
        weights: dict[str, float] | None = None,
        allow_lineage_gaps: bool = False,
    ) -> None:
        assert sources_path == sources
        assert output_dir == out_dir
        assert iters == 1
        assert benches
        assert weights is not None
        captured_allow.append(allow_lineage_gaps)
        output_dir.mkdir(parents=True)
        (output_dir / "index.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(builder, "build_static_data", fake_build_static_data)
    monkeypatch.setattr(builder, "_build_agentic_column", lambda _out_dir: None)

    code = builder.main(
        [
            "--allow-lineage-gaps",
            "--sources",
            str(sources),
            "--out",
            str(out_dir),
            "--iters",
            "1",
        ],
    )

    assert code == 0
    assert captured_allow == [True]


def test_code_verdict_source_fails_closed_on_mixed_provenance() -> None:
    # A single self-reported ("submitter") coding item must taint the aggregate, so a mostly-verifier
    # run with one forged submitter item does not aggregate to "verifier" and slip past the guard.
    builder = _build_data_module()

    def _item(source: JsonValue) -> JsonObject:
        return {"bench": "bigcodebench_hard", "code_artifact": {"verdict_source": source}}

    assert builder._code_verdict_source([_item("verifier"), _item("submitter")]) == "submitter"
    assert builder._code_verdict_source([_item("verifier"), _item("verifier")]) == "verifier"
    # null items (unscoreable, like the real Gemma run) don't count as string sources; verifier wins.
    assert builder._code_verdict_source([_item("verifier"), _item(None)]) == "verifier"


def test_build_data_quarantines_invalid_inline_appworld(tmp_path: Path) -> None:
    # Given: a run with inline appworld_c scores whose diagnostics show harness-dominated failure.
    builder = _build_data_module()
    paths = _write_synthetic_pipeline_inputs(
        tmp_path,
        [
            _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
            _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
            _synthetic_item("scenario1_1", "appworld_c", False),
        ],
    )
    run = _object(_read_json(paths["run"]))
    _object(run["benches"])["appworld_c"] = {
        "n": 1,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": 0.0,
        "chance_corrected": 0.0,
        "conditional_accuracy": 0.0,
        "termination_rate": 1.0,
    }
    run["agentic_run"] = _harness_dominated_agentic_run()
    paths["run"].write_text(json.dumps(run), encoding="utf-8")

    # When: the web data pipeline builds static JSON.
    builder.build_static_data(paths["sources"], paths["out"], iters=300)

    # Then: K/I remain visible, but the invalid agentic axis is omitted and the row is unranked.
    index = _object(_read_json(paths["out"] / "index.json"))
    model = _model_by_label(_objects(index["models"]), "Synthetic Model")
    assert _object(model["axes"]).keys() == {"knowledge", "instruction"}
    assert model["ranked"] is False
    detail = _only_run_detail(paths["out"])
    assert "agentic" not in _object(detail["axes"])
    assert any("agentic appworld_c quarantined" in warning for warning in _strings(detail["data_warnings"]))


def test_build_data_carries_board_conformance_gate_to_index_and_model_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the board artifact supplies a tc_json sidecar for the generated run id.
    builder = _build_data_module()
    paths = _write_synthetic_pipeline_inputs(
        tmp_path,
        [
            _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
            _synthetic_item("mmlu-pro-002", "mmlu_pro", False, category="biology", template="mcq-b"),
            _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
            _synthetic_item("ifbench-002", "ifbench", False, template="format-list"),
        ],
    )
    gate = _tc_json_gate("red")
    interval = {"hi": 90.0, "hi_raw": 0.9, "lo": 70.0, "lo_raw": 0.7, "point": 80.0, "point_raw": 0.8}
    monkeypatch.setattr(
        builder,
        "_board_context",
        lambda: builder.BoardContext(
            headline_lane="test",
            models_by_slug={
                "synthetic-model": {
                    "ranked": True,
                    "systems": [
                        {
                            "run_id": "synthetic-model__synthetic-run",
                            "composite": interval,
                            "axes": {"knowledge": interval, "instruction": interval},
                            "conformance_gates": {"tc_json_v1": gate},
                        },
                    ],
                },
            },
        ),
    )

    # When: the static web JSON is built through the normal pipeline.
    builder.build_static_data(paths["sources"], paths["out"], iters=50)

    # Then: index, model, and run-detail rows render the board-provided gate verbatim.
    index = _object(_read_json(paths["out"] / "index.json"))
    model = _model_by_label(_objects(index["models"]), "Synthetic Model")
    model_gate = _object(_object(model["conformance_gates"])["tc_json_v1"])
    assert model_gate == gate
    model_payload = _object(_read_json(paths["out"] / "models" / "synthetic-model.json"))
    run_row = _objects(model_payload["runs"])[0]
    assert _object(_object(run_row["conformance_gates"])["tc_json_v1"]) == gate
    run_detail = _only_run_detail(paths["out"])
    assert _object(_object(run_detail["conformance_gates"])["tc_json_v1"]) == gate


def test_build_run_uses_version_matched_season2_rescore_on_every_surface(tmp_path: Path) -> None:
    builder = _build_data_module()
    run_path = tmp_path / "rescored-run.json"
    items = [
        _synthetic_item("mmlu-pro-001", "mmlu_pro", True),
        _synthetic_item("ifbench-001", "ifbench", True),
        _synthetic_item("olymmath-hard-001", "olymmath_hard", True),
        _synthetic_item("amo-001", "amo", False),
        _synthetic_item("appworld-c-001", "appworld_c", False),
        _synthetic_item("bigcodebench-hard-001", "bigcodebench_hard", True),
    ]
    run = _synthetic_run(items)
    run["index_version"] = "index-v4.2"
    run["benches"] = {
        bench: _synthetic_aggregate(items, bench)
        for bench in (
            "mmlu_pro",
            "ifbench",
            "olymmath_hard",
            "amo",
            "appworld_c",
            "bigcodebench_hard",
        )
    }
    run["composite"] = None
    run["agentic_run"] = _healthy_agentic_run()
    rescored_axis: JsonObject = {
        "n": 96,
        "n_errors": 0,
        "n_no_answer": 0,
        "point": 10.5,
        "point_raw": 0.105,
        "raw_accuracy": 0.105,
    }
    rescored_coding: JsonObject = {
        "n": 141,
        "n_errors": 0,
        "n_no_answer": 0,
        "point": 70.0,
        "point_raw": 0.7,
        "raw_accuracy": 0.7,
    }
    rescored_composite: JsonObject = {
        "hi": 54.0,
        "hi_raw": 0.54,
        "lo": 48.0,
        "lo_raw": 0.48,
        "point": 51.0,
        "point_raw": 0.51,
    }
    run["season2_rescore"] = {
        "index_version": "index-v4.2",
        "axes": {"coding": rescored_coding, "tool_use": rescored_axis},
        "composite_v4": rescored_composite,
    }
    run_path.write_text(json.dumps(run), encoding="utf-8")
    source = builder._source(
        {
            "family": "Synthetic",
            "file": str(run_path),
            "kind": "maintainer_project",
            "model_label": "Rescored Model",
            "origin": "project_anchor",
            "reasoning_lane": "test",
            "trust_label": "project_anchor",
            "vram_footprint_gb": 1.0,
        },
        0,
    )
    run_id = "rescored-model__rescored-run"
    stale_interval: JsonObject = {
        "hi": 25.0,
        "hi_raw": 0.25,
        "lo": 11.0,
        "lo_raw": 0.11,
        "point": 17.66,
        "point_raw": 0.1766,
    }
    board = builder.BoardContext(
        headline_lane="test",
        models_by_slug={
            "rescored-model": {
                "best_run_id": run_id,
                "composite_full": stale_interval,
                "systems": [
                    {
                        "axes": {
                            "coding": stale_interval | {"n": 148},
                            "tool_use": stale_interval | {"n": 146},
                        },
                        "composite": stale_interval,
                        "run_id": run_id,
                    },
                ],
            },
        },
    )

    composed = builder._build_run(
        source,
        order=0,
        iters=20,
        benches=builder.BENCHES,
        weights=builder.COMPOSITE_WEIGHTS,
        board=board,
    )

    for surface in ("detail", "model_row", "index_row"):
        row = _object(composed[surface])
        assert set(_object(row["axes"])) == {
            "coding",
            "instruction",
            "knowledge",
            "math",
            "tool_use",
        }
        assert _object(_object(row["axes"])["coding"]) == rescored_coding
        assert _object(_object(row["axes"])["tool_use"]) == rescored_axis
        assert _object(row["composite_full"]) == rescored_composite
        assert _object(row["composite"]) == rescored_composite
    assert _number(composed["composite_raw"]) == rescored_composite["point_raw"]


def test_apply_board_intervals_rejects_mixed_axis_membership() -> None:
    builder = _build_data_module()
    run_id = "mixed-model__run"
    axes: JsonObject = {
        "tool_use": {
            "n": 96,
            "point": 10.5,
            "point_raw": 0.105,
            "raw_accuracy": 0.105,
        },
    }
    composite: JsonObject = {
        "hi": 54.0,
        "hi_raw": 0.54,
        "lo": 48.0,
        "lo_raw": 0.48,
        "point": 51.0,
        "point_raw": 0.51,
    }
    stale_interval: JsonObject = {
        "hi": 25.0,
        "hi_raw": 0.25,
        "lo": 11.0,
        "lo_raw": 0.11,
        "n": 146,
        "point": 17.66,
        "point_raw": 0.1766,
    }
    board: dict[str, JsonObject] = {
        "mixed-model": {
            "systems": [
                {
                    "axes": {"tool_use": stale_interval},
                    "composite": stale_interval,
                    "run_id": run_id,
                },
            ],
        },
    }

    with pytest.raises(builder.DataBuildError, match=r"tool_use.*n=96.*n=146"):
        builder._apply_board_intervals("mixed-model", run_id, axes, composite, board)


def test_build_run_without_season2_rescore_keeps_unmatched_community_composition(tmp_path: Path) -> None:
    builder = _build_data_module()
    run_path = tmp_path / "community-run.json"
    items = [
        _synthetic_item("mmlu-pro-001", "mmlu_pro", True),
        _synthetic_item("ifbench-001", "ifbench", True),
        _synthetic_item("olymmath-hard-001", "olymmath_hard", True),
        _synthetic_item("amo-001", "amo", False),
        _synthetic_item("appworld-c-001", "appworld_c", False),
        _synthetic_item("bigcodebench-hard-001", "bigcodebench_hard", True),
    ]
    run = _synthetic_run(items)
    run["index_version"] = "index-v4.2"
    run["benches"] = {
        bench: _synthetic_aggregate(items, bench)
        for bench in (
            "mmlu_pro",
            "ifbench",
            "olymmath_hard",
            "amo",
            "appworld_c",
            "bigcodebench_hard",
        )
    }
    run["composite"] = None
    run["agentic_run"] = _healthy_agentic_run()
    run_path.write_text(json.dumps(run), encoding="utf-8")
    source = builder._source(
        {
            "family": "Synthetic",
            "file": str(run_path),
            "kind": "community",
            "model_label": "Community Model",
            "reasoning_lane": "test",
            "trust_label": "community_self_submitted",
            "vram_footprint_gb": 1.0,
        },
        0,
    )
    board = builder.BoardContext(headline_lane="test", models_by_slug={})

    composed = builder._build_run(
        source,
        order=0,
        iters=20,
        benches=builder.BENCHES,
        weights=builder.COMPOSITE_WEIGHTS,
        board=board,
    )

    tool_use = _object(_object(_object(composed["detail"])["axes"])["tool_use"])
    assert _number(tool_use["point"]) == 0.0
    assert _number(tool_use["n"]) == 1
    composite_full = _object(_object(composed["detail"])["composite_full"])
    assert _number(composite_full["point"]) == 71.25


def test_build_data_carries_runtime_to_index_model_and_run_rows(tmp_path: Path) -> None:
    # Given: a synthetic run whose manifest records the serving runtime identity.
    builder = _build_data_module()
    paths = _write_synthetic_pipeline_inputs(
        tmp_path,
        [
            _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
            _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
        ],
    )
    run = _object(_read_json(paths["run"]))
    _object(run["manifest"])["runtime"] = {
        "ctx_len_configured": 8192,
        "kv_cache_quant": "q8_0",
        "name": "llama.cpp",
        "parallel_slots": 1,
        "version": "b1234",
    }
    paths["run"].write_text(json.dumps(run), encoding="utf-8")

    # When: the static web JSON is built through the normal pipeline.
    builder.build_static_data(paths["sources"], paths["out"], iters=50)

    # Then: runtime is present on the index row, model run row, and run detail summary.
    index = _object(_read_json(paths["out"] / "index.json"))
    model = _model_by_label(_objects(index["models"]), "Synthetic Model")
    assert _object(model["runtime"]) == {
        "ctx_len_configured": 8192,
        "kv_cache_quant": "q8_0",
        "name": "llama.cpp",
        "parallel_slots": 1,
        "version": "b1234",
    }
    model_payload = _object(_read_json(paths["out"] / "models" / "synthetic-model.json"))
    run_row = _objects(model_payload["runs"])[0]
    assert _object(run_row["runtime"]) == _object(model["runtime"])
    run_detail = _only_run_detail(paths["out"])
    assert _object(_object(run_detail["manifest_summary"])["runtime"]) == _object(model["runtime"])


def test_build_data_carries_perf_to_model_run_and_run_detail(tmp_path: Path) -> None:
    builder = _build_data_module()
    paths = _write_synthetic_pipeline_inputs(
        tmp_path,
        [
            _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
            _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
        ],
    )
    perf: JsonObject = {
        "timings_source": "llama.cpp",
        "timings_coverage": 1.0,
        "prefill_tps": 500.0,
        "decode_tps": 250.0,
        "prompt_ms_median": 20.0,
        "prompt_ms_p95": 20.0,
        "predicted_ms_median": 16.0,
        "predicted_ms_p95": 16.0,
        "ttft_proxy_ms_median": 20.0,
        "per_bench": {
            "mmlu_pro": {
                "prefill_tps": 500.0,
                "decode_tps": 250.0,
                "prompt_ms_median": 20.0,
                "n": 1,
            },
        },
    }
    run = _object(_read_json(paths["run"]))
    run["perf"] = perf
    paths["run"].write_text(json.dumps(run), encoding="utf-8")

    builder.build_static_data(paths["sources"], paths["out"], iters=50)

    model_payload = _object(_read_json(paths["out"] / "models" / "synthetic-model.json"))
    run_row = _objects(model_payload["runs"])[0]
    run_detail = _only_run_detail(paths["out"])
    assert _object(run_row["perf"]) == perf
    assert _object(run_detail["perf"]) == perf


def test_build_data_when_items_have_suite_metadata_uses_real_strata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given suite-v1 math items whose metadata resolves to different source strata.
    builder = _build_data_module()
    from localbench.scoring import bootstrap, metadata

    original_ci = bootstrap.stratified_mean_ci
    original_stratum = metadata.stratum_for_item
    captured_strata: list[tuple[str, ...]] = []
    stratum_calls: list[tuple[str, str, str]] = []

    def recording_ci(values: list[float], strata: list[str], *, iters: int, seed: int) -> dict[str, float]:
        captured_strata.append(tuple(strata))
        return original_ci(values, strata, iters=iters, seed=seed)

    def recording_stratum(bench: str, item_id: str, item: JsonObject) -> str:
        stratum = original_stratum(bench, item_id, item)
        stratum_calls.append((bench, item_id, stratum))
        return stratum

    monkeypatch.setattr(bootstrap, "stratified_mean_ci", recording_ci)
    monkeypatch.setattr(metadata, "stratum_for_item", recording_stratum)
    paths = _write_synthetic_pipeline_inputs(
        tmp_path,
        [
            _synthetic_item("mmlu-pro-001", "mmlu_pro", True, category="physics", template="mcq-a"),
            _synthetic_item("mmlu-pro-002", "mmlu_pro", False, category="biology", template="mcq-b"),
            _synthetic_item("ifbench-001", "ifbench", True, template="format-json"),
            _synthetic_item("ifbench-002", "ifbench", False, template="format-list"),
            _synthetic_item("bfcl-001", "bfcl", True, category="tool-use", template="single-call"),
            _synthetic_item("bfcl-002", "bfcl", False, category="tool-use", template="multi-call"),
            _synthetic_item(
                "olymmath-hard-001",
                "olymmath_hard",
                True,
                category="geometry",
                difficulty="hard",
                template="proof",
            ),
            _synthetic_item(
                "amo-001",
                "amo",
                False,
                category="number-theory",
                difficulty="hard",
                template="short-answer",
            ),
        ],
    )

    # When the web data pipeline computes per-axis intervals.
    builder.build_static_data(paths["sources"], paths["out"], iters=50)

    # Then math uses category|difficulty|template strata from its two suite-v1 source benches.
    math_strata = next(
        strata
        for strata in captured_strata
        if any(stratum.startswith("bench=olymmath_hard|") for stratum in strata)
    )
    assert math_strata == (
        "bench=olymmath_hard|category=geometry|difficulty=hard|template=proof",
        "bench=amo|category=number-theory|difficulty=hard|template=short-answer",
    )
    assert len(set(math_strata)) == 2
    assert [call[0] for call in stratum_calls].count("olymmath_hard") == 1
    assert [call[0] for call in stratum_calls].count("amo") == 1


def test_build_data_main_reports_absolute_out_dir_when_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a dry-run caller writes generated data outside the repo tree.
    builder = _build_data_module()
    sources = tmp_path / "sources.json"
    sources.write_text("[]", encoding="utf-8")
    out_dir = tmp_path / "generated"

    def fake_build_static_data(
        sources_path: Path,
        output_dir: Path,
        *,
        iters: int = 0,
        benches: tuple[str, ...] = (),
        weights: dict[str, float] | None = None,
        allow_lineage_gaps: bool = False,
    ) -> None:
        assert sources_path == sources
        assert output_dir == out_dir
        assert iters == 1
        assert benches
        assert weights is not None
        assert allow_lineage_gaps is False
        output_dir.mkdir(parents=True)
        (output_dir / "index.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(builder, "build_static_data", fake_build_static_data)
    monkeypatch.setattr(builder, "_build_agentic_column", lambda _out_dir: None)

    # When: the CLI entrypoint completes.
    code = builder.main(["--sources", str(sources), "--out", str(out_dir), "--iters", "1"])

    # Then: it succeeds and prints the display path without crashing on relative_to(ROOT).
    captured = capsys.readouterr()
    assert code == 0
    assert f"wrote {builder._display_path(out_dir)}" in captured.out


def test_site_data_freshness_detects_inputs_newer_than_generated_index(tmp_path: Path) -> None:
    # Given: generated site data older than one run artifact.
    from web import check_data_freshness

    generated = tmp_path / "web" / "public" / "data" / "index.json"
    data_sources = tmp_path / "web" / "data_sources.json"
    runs_dir = tmp_path / "cli" / "runs"
    board_dir = runs_dir / "board"
    run_file = runs_dir / "new-run.json"
    board_file = board_dir / "board_v2.json"
    for path in (generated, data_sources, run_file, board_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    _set_mtime_ns(generated, 1_000_000_000)
    _set_mtime_ns(data_sources, 900_000_000)
    _set_mtime_ns(run_file, 1_100_000_000)
    _set_mtime_ns(board_file, 800_000_000)

    # When: the freshness checker scans the configured inputs.
    stale = check_data_freshness.stale_inputs(
        generated=generated,
        watched=(data_sources, runs_dir, board_dir),
    )

    # Then: it reports the newer run file once, even though board is also nested in cli/runs.
    assert tuple(item.path for item in stale) == (run_file,)


def _set_mtime_ns(path: Path, mtime_ns: int) -> None:
    os.utime(path, ns=(mtime_ns, mtime_ns))


def _run_pipeline(*, iters: int) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "build_data.py",
            "--sources",
            "data_sources.json",
            "--out",
            "public/data",
            "--iters",
            str(iters),
        ],
        cwd=ROOT / "web",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _build_data_module() -> ModuleType:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from web import build_data

    return build_data


def _write_synthetic_pipeline_inputs(
    tmp_path: Path,
    items: list[JsonObject],
) -> dict[str, Path]:
    run_path = tmp_path / "synthetic-run.json"
    sources_path = tmp_path / "sources.json"
    out_dir = tmp_path / "out"
    run_path.write_text(json.dumps(_synthetic_run(items)), encoding="utf-8")
    sources_path.write_text(
        json.dumps(
            [
                {
                    "family": "Synthetic",
                    "file": str(run_path),
                    "kind": "anchor",
                    "origin": "project_anchor",
                    "model_label": "Synthetic Model",
                    "quant_label": None,
                    "reasoning_lane": "test",
                    "vram_footprint_gb": None,
                },
            ],
        ),
        encoding="utf-8",
    )
    return {"run": run_path, "sources": sources_path, "out": out_dir}


def _synthetic_run(items: list[JsonObject]) -> JsonObject:
    # Only build aggregates for benches that actually have items, so a fixture can model
    # a Knowledge+Instruction-only run (the post-drop-synthesis reality) as well as a
    # full multi-axis run. Order preserved from SOURCE_BENCHES for determinism.
    present_benches = tuple(
        bench for bench in SOURCE_BENCHES if any(item["bench"] == bench for item in items)
    )
    benches = {bench: _synthetic_aggregate(items, bench) for bench in present_benches}
    return {
        "schema": "localbench-run-v0",
        "manifest": {
            "suite": {
                "suite_version": "suite-v1",
                "tier": "standard",
                "item_set_hashes": {f"{bench}.jsonl": f"synthetic-{bench}" for bench in present_benches},
            },
        },
        "benches": benches,
        "composite": _synthetic_composite(benches),
        "items": items,
        "totals": {
            "n_items": len(items),
            "n_errors": sum(1 for item in items if item.get("error") is not None),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "wall_time_seconds": 1.0,
            "completion_tokens_per_second": 0.0,
        },
        "warnings": [],
        "output_path": "synthetic-run.json",
    }


def _synthetic_aggregate(items: list[JsonObject], bench: str) -> JsonObject:
    bench_items = [item for item in items if item["bench"] == bench]
    assert bench_items
    raw_accuracy = sum(1 for item in bench_items if item.get("correct") is True) / len(bench_items)
    return {
        "n": len(bench_items),
        "n_errors": sum(1 for item in bench_items if item.get("error") is not None),
        "n_extraction_failures": 0,
        "raw_accuracy": raw_accuracy,
        "chance_corrected": _signed_score(
            raw_accuracy,
            chance=SOURCE_CHANCE_BASELINES.get(bench, 0.0),
        ),
    }


def _synthetic_item(
    item_id: str,
    bench: str,
    correct: bool | None,
    *,
    category: str | None = None,
    difficulty: str | None = None,
    error: str | None = None,
    template: str | None = None,
) -> JsonObject:
    item: JsonObject = {
        "id": item_id,
        "bench": bench,
        "correct": correct,
        "error": error,
        "extracted": "answer" if correct is not None else None,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    if category is not None:
        item["category"] = category
    if difficulty is not None:
        item["difficulty"] = difficulty
    if template is not None:
        item["template"] = template
    return item


def _tc_json_gate(band: str) -> JsonObject:
    return {
        "id": "tc_json_v1",
        "label": "Tool-calling",
        "band": band,
        "pass_rate": {"point": 82.0, "lo": 78.0, "hi": 86.0},
        "invalid_json_rate": 18.0,
        "n_items": 330,
        "threshold_version": "tc_json_v1",
        "band_reasons": ["invalid_json>15"],
    }


def _harness_dominated_agentic_run() -> JsonObject:
    diagnostics: JsonObject = {
        "tasks_total": 1,
        "tasks_succeeded": 0,
        "agentic_success_rate": 0.0,
        "outcome_counts": {
            "success": 0,
            "failure": 0,
            "cap_exceeded": 1,
            "no_final_answer": 0,
            "harness_error": 0,
        },
    }
    return {
        "campaign": True,
        "single_pass": False,
        "mean_asr": 0.0,
        "subset_size": 1,
        "diagnostics": diagnostics,
        "runs": [{"run_index": 1, "results_path": "agentic/run1.json", **diagnostics}],
    }


def _healthy_agentic_run() -> JsonObject:
    diagnostics: JsonObject = {
        "tasks_total": 1,
        "tasks_succeeded": 1,
        "infra_failure_rate": 0.0,
        "infra_timeout_rate": 0.0,
        "outcome_counts": {
            "success": 1,
            "failure": 0,
            "cap_exceeded": 0,
            "no_final_answer": 0,
            "harness_error": 0,
        },
    }
    return {
        "campaign": True,
        "single_pass": False,
        "mean_asr": 1.0,
        "subset_size": 1,
        "diagnostics": diagnostics,
        "runs": [{"run_index": 1, "results_path": "agentic/run1.json", **diagnostics}],
    }


def _gate_run(
    slug: str,
    *,
    catalog_id: str | None,
    ranked: bool,
    quant_label: str | None = "Q4_K_M",
    vram_footprint_gb: float | None = 10.0,
) -> JsonObject:
    return {
        "catalog_id": catalog_id,
        "index_row": {
            "ranked": ranked,
            "score_status": "measured",
            "slug": slug,
        },
        "model_row": {
            "quant_label": quant_label,
            "score_status": "measured",
            "vram_footprint_gb": vram_footprint_gb,
        },
        "run_id": f"{slug}__run",
        "slug": slug,
    }


def _gate_catalog_entry(
    model_id: str,
    slug: str,
    *,
    base_model: str | None = None,
    model_kind: str = "base",
    quants: list[JsonObject] | None = None,
) -> JsonObject:
    return {
        "base_model": base_model,
        "display_name": model_id.rsplit("/", 1)[-1],
        "family": "Fixture",
        "gguf_repo": None,
        "id": model_id,
        "is_moe": False,
        "license": "apache-2.0",
        "model_kind": model_kind,
        "org": model_id.split("/", 1)[0],
        "popularity": {},
        "quants": quants or [],
        "reasoning_capable": True,
        "slug": slug,
    }


def test_catalog_model_payload_exposes_pins_the_one_shot_resolver_accepts() -> None:
    # Given: a catalog entry with one fully pinned quant and one unpinned quant.
    # 2026-07-09 regression: pins existed in model_catalog.json but the served
    # models/<slug>.json projection dropped them, so `localbench bench <slug>`
    # refused every catalog model. The contract under test is projection -> resolver.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from web.build_data_catalog import catalog_model_payload

    from localbench.one_shot.catalog import resolve_one_shot_model

    entry = _gate_catalog_entry(
        "Fixture/Pinned",
        "pinned-fixture",
        quants=[
            {
                "label": "Q4_K_M",
                "file_gb": 0.5,
                "vram_gb_8k": 1.5,
                "gguf_repo": "Fixture/Pinned-GGUF",
                "filename": "pinned.Q4_K_M.gguf",
                "revision": "a" * 40,
                "file_size_bytes": 484220032,
                "file_sha256": "b" * 64,
            },
            {"label": "Q2_K", "file_gb": 0.3, "vram_gb_8k": 1.0},
        ],
    )

    payload = catalog_model_payload(entry, [])

    # Then: only the pinned quant is exposed, and the CLI resolver accepts it as publishable.
    assert [row["quant_label"] for row in payload["artifacts"]] == ["Q4_K_M"]
    assert payload["hf_model_id"] == "Fixture/Pinned"
    resolved = resolve_one_shot_model("pinned-fixture", {"models": [payload]}, quant="Q4_K_M", vram_gb=None)
    assert resolved.publishable is True
    assert resolved.tokenizer_repo == "Fixture/Pinned"
    assert resolved.artifact.repo_id == "Fixture/Pinned-GGUF"
    assert resolved.artifact.filename == "pinned.Q4_K_M.gguf"
    assert resolved.artifact.sha256 == "b" * 64
    assert resolved.artifact.size_bytes == 484220032


def _registry_weighted_composite(benches: JsonObject) -> float:
    # Mirror production: weight axes by the registry's web composite weights
    # (headline knowledge + instruction at 0.5 each; agentic + math 0.0),
    # normalized over the present headline axes (METHODOLOGY-v1.2 §3). Uses the
    # single weight source so the oracle tracks the registry, not a parallel copy.
    weights = FROZEN_WEB_WEIGHTS
    present = {
        axis: _weighted_source_value(benches, names, "chance_corrected")
        for axis in AXES
        if (names := _source_names_for_axis(axis, benches))
    }
    total = sum(weights[axis] for axis in present)
    if total <= 0:
        return 0.0
    return sum(weights[axis] * value for axis, value in present.items()) / total


def _synthetic_composite(benches: JsonObject) -> float:
    return _registry_weighted_composite(benches)


def _signed_score(raw: float, *, chance: float) -> float:
    return (raw - chance) / (1.0 - chance)


def _expected_composite(raw_run: JsonObject) -> float:
    return _registry_weighted_composite(_object(raw_run["benches"]))


def _assert_axis_matches_raw_sources(axis: str, raw_run: JsonObject, detail: JsonObject) -> None:
    raw_benches = _object(raw_run["benches"])
    source_names = _source_names_for_axis(axis, raw_benches)
    axis_detail = _object(_object(detail["axes"])[axis])
    assert _number(axis_detail["point_raw"]) == pytest.approx(
        _weighted_source_value(raw_benches, source_names, "chance_corrected"),
        abs=1e-9,
    )
    assert _number(axis_detail["raw_accuracy"]) == pytest.approx(
        _weighted_source_value(raw_benches, source_names, "raw_accuracy"),
        abs=1e-9,
    )
    assert _number(axis_detail["n"]) == pytest.approx(
        sum(_number(_object(raw_benches[bench])["n"]) for bench in source_names),
        abs=1e-9,
    )


def _weighted_source_value(raw_benches: JsonObject, source_names: tuple[str, ...], key: str) -> float:
    aggregates = [_object(raw_benches[bench]) for bench in source_names]
    n_total = sum(_number(aggregate["n"]) for aggregate in aggregates)
    return sum(_number(aggregate[key]) * _number(aggregate["n"]) for aggregate in aggregates) / n_total


def _source_names_for_axis(axis: str, raw_benches: JsonObject) -> tuple[str, ...]:
    for source_names in SOURCE_BENCH_GROUPS_BY_AXIS[axis]:
        if all(bench in raw_benches for bench in source_names):
            return source_names
    # Post-drop-synthesis contract: a run measures only some axes. An axis whose source
    # benches are absent is simply "not measured" (axes ⊆ AXES) — not an error.
    return ()


def _only_run_detail(out_dir: Path) -> JsonObject:
    run_paths = list((out_dir / "runs").glob("*.json"))
    assert len(run_paths) == 1
    return _object(_read_json(run_paths[0]))


def _read_outputs(out_dir: Path) -> dict[str, str]:
    paths = sorted(out_dir.rglob("*.json"))
    assert out_dir / "index.json" in paths
    assert any(path.parts[-2] == "models" for path in paths)
    assert any(path.parts[-2] == "runs" for path in paths)
    return {
        str(path.relative_to(out_dir)): path.read_text(encoding="utf-8")
        for path in paths
    }


def _read_generated_outputs() -> dict[str, str]:
    assert DATA_DIR.exists()
    paths = sorted(DATA_DIR.rglob("*.json"))
    assert DATA_DIR / "index.json" in paths
    assert any(path.parts[-2] == "models" for path in paths)
    assert any(path.parts[-2] == "runs" for path in paths)
    return {
        str(path.relative_to(DATA_DIR)): path.read_text(encoding="utf-8")
        for path in paths
    }


def _assert_run_detail(detail: JsonObject) -> None:
    assert {
        "axes",
        "composite",
        "est_cost_usd",
        "item_set_hashes",
        "kind",
        "manifest_summary",
        "model_label",
        "run_id",
        "score_status",
        "suite_version",
        "totals",
        "worst_axis",
    } <= set(detail)
    _assert_interval(_score_interval(detail))
    axes = _object(detail["axes"])
    # Contract: axes ⊆ AXES, headline always present, candidates only when measured.
    # Every emitted axis must be a real measurement (n > 0) — no synthesized n=0 axes.
    assert set(axes) <= set(AXES)
    assert {"knowledge", "instruction"} <= set(axes)
    for axis_value in axes.values():
        axis = _object(axis_value)
        _assert_interval(axis)
        assert {"n", "n_errors", "n_no_answer", "raw_accuracy"} <= set(axis)
        assert _number(axis["n"]) > 0


def _score_interval(detail: JsonObject) -> JsonObject:
    if detail["composite"] is not None:
        return _object(detail["composite"])
    return _object(detail["diagnostic_composite"])


def _assert_interval(interval: JsonObject) -> None:
    assert {"hi", "hi_raw", "lo", "lo_raw", "point", "point_raw"} <= set(interval)
    assert _number(interval["lo"]) <= _number(interval["point"]) <= _number(interval["hi"])
    assert _number(interval["lo_raw"]) <= _number(interval["point_raw"]) <= _number(interval["hi_raw"])


def _model_by_label(models: list[JsonObject], label: str) -> JsonObject:
    for model in models:
        if _string(model["model_label"]) == label:
            return model
    raise AssertionError(f"missing model label {label}")


def _read_json(path: Path) -> JsonValue:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _objects(value: JsonValue) -> list[JsonObject]:
    assert isinstance(value, list)
    objects: list[JsonObject] = []
    for item in value:
        objects.append(_object(item))
    return objects


def _string(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _strings(value: JsonValue) -> list[str]:
    assert isinstance(value, list)
    strings: list[str] = []
    for item in value:
        strings.append(_string(item))
    return strings


def _bool(value: JsonValue) -> bool:
    assert isinstance(value, bool)
    return value


def _number(value: JsonValue) -> float:
    assert isinstance(value, int | float)
    return float(value)
