from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from localbench._types import JsonObject


def _module() -> ModuleType:
    path = Path(__file__).parents[2] / "scratchpad" / "rescore_v42_records.py"
    spec = importlib.util.spec_from_file_location("rescore_v42_records", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v42_rescore_diff_gate_rejects_non_protocol_changes() -> None:
    module = _module()
    before: JsonObject = {
        "index_version": "index-v4.1",
        "model": {"name": "model"},
        "season2_rescore": {"axes": {"tool_use": {"n": 146}}},
    }
    allowed: JsonObject = {
        "index_version": "index-v4.2",
        "model": {"name": "model"},
        "season2_rescore": {"axes": {"tool_use": {"n": 96}}},
    }
    disallowed: JsonObject = {
        **allowed,
        "model": {"name": "changed"},
    }

    assert module.disallowed_diffs(before, allowed) == []
    assert module.disallowed_diffs(before, disallowed) == ["$.model.name"]


def test_v42_rescore_bfcl_snapshot_preserves_aggregate_and_items() -> None:
    module = _module()
    record: JsonObject = {
        "benches": {"bfcl_multi_turn_base": {"n": 50, "raw_accuracy": 0.24}},
        "items": [
            {"bench": "appworld_c", "id": "appworld-1", "correct": True},
            {"bench": "bfcl_multi_turn_base", "id": "bfcl-1", "correct": False},
        ],
        "agentic_run": {"ordered_task_ids": ["appworld-1"]},
    }

    snapshot = module.bfcl_snapshot(record)
    record["benches"]["bfcl_multi_turn_base"]["n"] = 49

    assert snapshot["aggregate"] == {"n": 50, "raw_accuracy": 0.24}
    assert snapshot["items"] == [
        {"bench": "bfcl_multi_turn_base", "id": "bfcl-1", "correct": False}
    ]
    assert list(module.ordered_task_id_lists(record)) == [["appworld-1"]]
