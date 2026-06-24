from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Final, TypeAlias

import pytest

from localbench.scoring.axes import web_composite_weights

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
                    "kind": "community",
                    "model_label": "Fixture KI",
                    "quant_label": "Q4_K_M",
                    "reasoning_lane": "answer-only",
                    "vram_footprint_gb": 16.55,
                },
                {
                    "family": "Fixture-Math",
                    "file": str(math_run),
                    "kind": "community",
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
    measured = [model for model in models if model.get("composite") is not None]
    assert {_string(model["model_label"]) for model in measured} >= {"Fixture KI", "Fixture Math"}

    # Contract: every MEASURED model's axes ⊆ AXES with the headline always present;
    # candidate axes (math/agentic) appear only when actually measured (no synthesis).
    for model in measured:
        model_axes = _object(model["axes"])
        assert set(model_axes) <= set(AXES)
        assert {"knowledge", "instruction"} <= set(model_axes)
        _assert_interval(_object(model["composite"]))
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
    composite = _object(detail["composite"])
    chance = SOURCE_CHANCE_BASELINES["mmlu_pro"]
    assert knowledge["point_raw"] == pytest.approx((0.5 - chance) / (1.0 - chance))
    assert instruction["point_raw"] == pytest.approx(0.5)
    assert instruction["raw_accuracy"] == pytest.approx(0.5)
    assert instruction["hi_raw"] < 1.0
    assert instruction["n_no_answer"] == 1
    assert math["point_raw"] == pytest.approx(0.5)
    assert math["hi_raw"] < 1.0
    assert math["n_errors"] == 1
    # Composite is HEADLINE-only: knowledge (mmlu_pro) + instruction (ifbench).
    # The present agentic (bfcl) + math axes carry weight 0.0 (METHODOLOGY-v1.2 §3).
    assert composite["point_raw"] == pytest.approx(
        (((0.5 - chance) / (1.0 - chance)) + 0.5) / 2,
    )
    assert isinstance(detail["data_warnings"], list)
    assert any(
        "knowledge chance_corrected differs" in warning
        for warning in _strings(detail["data_warnings"])
    )


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
                    "kind": "community",
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


def _registry_weighted_composite(benches: JsonObject) -> float:
    # Mirror production: weight axes by the registry's web composite weights
    # (headline knowledge + instruction at 0.5 each; agentic + math 0.0),
    # normalized over the present headline axes (METHODOLOGY-v1.2 §3). Uses the
    # single weight source so the oracle tracks the registry, not a parallel copy.
    weights = web_composite_weights()
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
        "suite_version",
        "totals",
        "worst_axis",
    } <= set(detail)
    _assert_interval(_object(detail["composite"]))
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
