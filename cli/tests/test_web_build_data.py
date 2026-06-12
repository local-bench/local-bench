from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
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
    assert _number(qwen["n_runs"]) == 4
    assert _bool(qwen["replicated"])
    assert _string(qwen["best_run_id"])
    _assert_interval(_object(qwen["composite"]))
    for bench in BENCHES:
        _assert_interval(_object(_object(qwen["axes"])[bench]))

    slug = _string(qwen["slug"])
    model_path = DATA_DIR / "models" / f"{slug}.json"
    assert model_path.exists()
    model_detail = _object(_read_json(model_path))
    model_runs = _objects(model_detail["runs"])
    assert len(model_runs) == 4

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


def _run_pipeline(*, iters: int) -> None:
    result = subprocess.run(
        [sys.executable, "web/build_data.py", "--iters", str(iters)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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
