from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import TypeAlias

import pytest

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

ROOT = Path(__file__).resolve().parents[2]
DATA_SOURCES = ROOT / "web" / "data_sources.json"
DATA_DIR = ROOT / "web" / "public" / "data"
BENCHES = ("genmath", "ifeval", "mmlu_pro")


def test_build_data_when_sources_are_curated_emits_deterministic_static_json() -> None:
    # Given the committed web data-source curation.
    assert DATA_SOURCES.exists()

    # When the pipeline is run twice with a fixed bootstrap seed.
    _run_pipeline(iters=2_000)
    first_outputs = _read_generated_outputs()
    _run_pipeline(iters=2_000)
    second_outputs = _read_generated_outputs()

    # Then the static JSON surface is complete and deterministic.
    assert first_outputs == second_outputs
    index = _object(_read_json(DATA_DIR / "index.json"))
    assert set(index) == {"generated_note", "models", "suite_version"}
    models = _objects(index["models"])
    assert models

    qwen = _model_by_label(models, "Qwen3.5 9B")
    assert _string(qwen["family"]) == "Qwen3.5"
    assert _string(qwen["kind"]) == "community"
    assert _number(qwen["n_runs"]) >= 3  # repeatability triplet is the floor; quant runs may add more
    assert _string(qwen["best_run_id"])
    _assert_interval(_object(qwen["composite"]))
    for bench in BENCHES:
        _assert_interval(_object(_object(qwen["axes"])[bench]))

    # At least one frontier anchor is present, on the native-reasoning lane, with a valid composite.
    anchors = [model for model in models if _string(model["kind"]) == "anchor"]
    assert anchors
    for anchor in anchors:
        assert _string(anchor["lane"]) == "api-uncapped"
        _assert_interval(_object(anchor["composite"]))

    slug = _string(qwen["slug"])
    model_path = DATA_DIR / "models" / f"{slug}.json"
    assert model_path.exists()
    model_detail = _object(_read_json(model_path))
    model_runs = _objects(model_detail["runs"])
    assert len(model_runs) >= 3

    for run_row in model_runs:
        run_id = _string(run_row["run_id"])
        run_path = DATA_DIR / "runs" / f"{run_id}.json"
        assert run_path.exists()
        detail = _object(_read_json(run_path))
        raw_run = _object(_read_json(ROOT / "runs" / f"{run_id.split('__', 1)[1]}.json"))
        assert _object(detail["composite"])["point_raw"] == pytest.approx(
            _number(raw_run["composite"]),
            abs=1e-6,
        )
        _assert_run_detail(detail)

    best_run = _string(qwen["best_run_id"])
    best_detail = _object(_read_json(DATA_DIR / "runs" / f"{best_run}.json"))
    assert _object(qwen["composite"])["point_raw"] == pytest.approx(
        _number(_object(best_detail["composite"])["point_raw"]),
        abs=1e-6,
    )


def test_build_data_when_error_or_no_answer_items_are_scored_as_incorrect(tmp_path: Path) -> None:
    # Given a synthetic run whose stored chance-corrected values are stale and clamped.
    builder = _build_data_module()
    paths = _write_synthetic_pipeline_inputs(tmp_path, [_synthetic_item("genmath-v0-product_minus_offset-1", "genmath", True), _synthetic_item("genmath-v0-average_of_five-1", "genmath", False, error="ResponseParseError: missing content"), _synthetic_item("102", "ifeval", True), _synthetic_item("127", "ifeval", None), _synthetic_item("136", "mmlu_pro", True), _synthetic_item("221", "mmlu_pro", False)])

    # When the web data pipeline builds static JSON from scored items.
    builder.build_static_data(paths["sources"], paths["out"], iters=300)

    # Then point estimates and CIs count errors/no-answers as incorrect.
    detail = _only_run_detail(paths["out"])
    axes = _object(detail["axes"])
    genmath = _object(axes["genmath"])
    ifeval = _object(axes["ifeval"])
    composite = _object(detail["composite"])
    assert genmath["point_raw"] == pytest.approx(0.5)
    assert genmath["hi_raw"] < 1.0
    assert ifeval["point_raw"] == pytest.approx(0.5)
    assert ifeval["hi_raw"] < 1.0
    assert ifeval["n_no_answer"] == 1
    assert genmath["n_errors"] == 1
    assert composite["point_raw"] == pytest.approx((0.5 + 0.5 + (0.5 - 0.1) / 0.9) / 3)
    assert isinstance(detail["data_warnings"], list)
    assert detail["data_warnings"]


def test_build_data_when_items_have_suite_metadata_uses_real_strata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given genmath items whose suite metadata resolves to different difficulty strata.
    builder = _build_data_module()
    from localbench.scoring import bootstrap, metadata

    original_ci = bootstrap.per_bench_ci
    original_stratum = metadata.stratum_for_item
    captured_strata: list[tuple[str, ...]] = []
    stratum_calls: list[tuple[str, str, str]] = []

    def recording_ci(correct: list[bool], strata: list[str], *, iters: int, seed: int) -> dict[str, float]:
        captured_strata.append(tuple(strata))
        return original_ci(correct, strata, iters=iters, seed=seed)

    def recording_stratum(bench: str, item_id: str, item: JsonObject) -> str:
        stratum = original_stratum(bench, item_id, item)
        stratum_calls.append((bench, item_id, stratum))
        return stratum

    monkeypatch.setattr(bootstrap, "per_bench_ci", recording_ci)
    monkeypatch.setattr(metadata, "stratum_for_item", recording_stratum)
    paths = _write_synthetic_pipeline_inputs(tmp_path, [_synthetic_item("genmath-v0-product_minus_offset-1", "genmath", True), _synthetic_item("genmath-v0-average_of_five-1", "genmath", False), _synthetic_item("102", "ifeval", True), _synthetic_item("127", "ifeval", False), _synthetic_item("136", "mmlu_pro", True), _synthetic_item("221", "mmlu_pro", False)])

    # When the web data pipeline computes per-bench intervals.
    builder.build_static_data(paths["sources"], paths["out"], iters=50)

    # Then genmath uses category|difficulty|template strata from scoring metadata.
    genmath_strata = captured_strata[0]
    assert genmath_strata == (
        "category=arithmetic|difficulty=easy|template=product_minus_offset",
        "category=arithmetic|difficulty=medium|template=average_of_five",
    )
    assert len(set(genmath_strata)) == 2
    assert [call[0] for call in stratum_calls].count("genmath") == 2


def _run_pipeline(*, iters: int) -> None:
    result = subprocess.run(
        [sys.executable, "web/build_data.py", "--iters", str(iters)],
        cwd=ROOT,
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
    sources_path.write_text(json.dumps([{"family": "Synthetic", "file": str(run_path), "kind": "community", "model_label": "Synthetic Model", "quant_label": None, "reasoning_lane": "test", "vram_footprint_gb": None}]), encoding="utf-8")
    return {"sources": sources_path, "out": out_dir}


def _synthetic_run(items: list[JsonObject]) -> JsonObject:
    benches = {bench: _synthetic_aggregate(items, bench) for bench in BENCHES}
    return {
        "schema": "localbench-run-v0",
        "manifest": {"suite": {"suite_version": "suite-v0", "tier": "quick"}},
        "benches": benches,
        "composite": 1.0,
        "items": items,
        "totals": {"n_items": len(items), "n_errors": sum(1 for item in items if item.get("error") is not None), "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "wall_time_seconds": 1.0, "completion_tokens_per_second": 0.0},
        "warnings": [],
        "output_path": "synthetic-run.json",
    }


def _synthetic_aggregate(items: list[JsonObject], bench: str) -> JsonObject:
    bench_items = [item for item in items if item["bench"] == bench]
    raw_accuracy = sum(1 for item in bench_items if item.get("correct") is True) / len(bench_items)
    return {
        "n": len(bench_items),
        "n_errors": sum(1 for item in bench_items if item.get("error") is not None),
        "n_extraction_failures": 0,
        "raw_accuracy": raw_accuracy,
        "chance_corrected": 1.0,
    }


def _synthetic_item(
    item_id: str,
    bench: str,
    correct: bool | None,
    *,
    error: str | None = None,
) -> JsonObject:
    return {
        "id": item_id,
        "bench": bench,
        "correct": correct,
        "error": error,
        "extracted": "answer" if correct is not None else None,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _only_run_detail(out_dir: Path) -> JsonObject:
    run_paths = list((out_dir / "runs").glob("*.json"))
    assert len(run_paths) == 1
    return _object(_read_json(run_paths[0]))


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
    for bench in BENCHES:
        axis = _object(axes[bench])
        _assert_interval(axis)
        assert {"n", "n_errors", "n_no_answer", "raw_accuracy"} <= set(axis)


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


def _number(value: JsonValue) -> float:
    assert isinstance(value, int | float)
    return float(value)


def _bool(value: JsonValue) -> bool:
    assert isinstance(value, bool)
    return value
