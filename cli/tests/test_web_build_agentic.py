from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    path = ROOT / "web" / "build_agentic.py"
    spec = importlib.util.spec_from_file_location("build_agentic", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agentic_bake_uses_ranked_record_item_verdicts() -> None:
    builder = _module()
    payload = builder.build_agentic(
        records_dir=ROOT / "runs" / "bench" / "season-2-backfill",
        index_path=ROOT / "web" / "public" / "data" / "index.json",
    )

    assert payload["schema"] == "localbench-agentic-column/v2"
    assert {
        slug: model["asr_pct"]
        for slug, model in payload["models"].items()
    } == {
        "gemma-4-12b-it": 4.17,
        "gemma-4-31b-it": 10.42,
        "qwen3-6-27b": 8.33,
        "qwen3-6-35b-a3b": 6.25,
        "qwopus3-6-27b-v2-mtp": 9.38,
    }
    assert all(model["n_tasks"] == 96 for model in payload["models"].values())
    assert all(model["asr_series"] == [model["asr"]] for model in payload["models"].values())
