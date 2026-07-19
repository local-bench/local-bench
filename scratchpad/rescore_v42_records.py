from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from localbench._types import JsonObject, JsonValue
from localbench.persistence import atomic_write_json
from localbench.scoring.agentic_exec.task_pool import ordered_task_ids_sha256
from localbench.scoring.editorial import (
    INDEX_VERSION_V4_2,
    SEASON_2_COVERAGE_PROFILE_ID,
    index_version_for_coverage_profile,
)
from localbench.scoring.season2_rescore import rescore_record_season2

REPO: Final = Path(__file__).resolve().parents[1]
RECORDS_DIR: Final = REPO / "runs" / "bench" / "season-2-backfill"
PROTOCOL_PATH: Final = REPO / "protocol" / "index-v4.2.json"

EXPECTED: Final = {
    "gemma-4-12b-it-qat-ud-q4-k-xl": (4.17, 39.99),
    "gemma-4-31b-it-q4-k-m": (10.42, 51.31),
    "qwen3-6-27b-q4-k-m": (8.33, 42.94),
    "qwen3-6-35b-a3b-ud-q4-k-m": (6.25, 40.71),
    "qwopus3-6-27b-v2-mtp-q4-k-m": (9.38, 41.76),
}

ALLOWED_POINTERS: Final = {
    "$.index_version",
    "$.season2_rescore.source_index_version",
    "$.season2_rescore.index_version",
    "$.season2_rescore.axes.tool_use",
    "$.season2_rescore.composite_v4",
    "$.season2_rescore.scorecard_id",
    "$.season2_rescore.registry_digest",
}


def walk_diffs(old: Any, new: Any, path: str = "$") -> Iterable[str]:
    if type(old) is not type(new):
        yield path
        return
    if isinstance(old, dict):
        for key in sorted(set(old) | set(new)):
            child = f"{path}.{key}"
            if key not in old or key not in new:
                yield child
            else:
                yield from walk_diffs(old[key], new[key], child)
    elif old != new:
        yield path


def disallowed_diffs(old: JsonObject, new: JsonObject) -> list[str]:
    return [
        pointer
        for pointer in walk_diffs(old, new)
        if not any(
            pointer == allowed or pointer.startswith(f"{allowed}.")
            for allowed in ALLOWED_POINTERS
        )
    ]


def appworld_items(record: Mapping[str, JsonValue]) -> list[JsonObject]:
    items = record.get("items")
    if not isinstance(items, list):
        raise AssertionError("record.items must be a list")
    return [
        dict(item)
        for item in items
        if isinstance(item, dict) and item.get("bench") == "appworld_c"
    ]


def bfcl_snapshot(record: Mapping[str, JsonValue]) -> JsonObject:
    benches = record.get("benches")
    items = record.get("items")
    if not isinstance(benches, dict) or not isinstance(items, list):
        raise AssertionError("record benches/items have the wrong shape")
    return {
        "aggregate": copy.deepcopy(benches.get("bfcl_multi_turn_base")),
        "items": copy.deepcopy(
            [
                item
                for item in items
                if isinstance(item, dict)
                and item.get("bench") == "bfcl_multi_turn_base"
            ]
        ),
    }


def ordered_task_id_lists(value: JsonValue) -> Iterable[list[str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if (
                key == "ordered_task_ids"
                and isinstance(child, list)
                and all(isinstance(item, str) for item in child)
            ):
                yield child
            else:
                yield from ordered_task_id_lists(child)
    elif isinstance(value, list):
        for child in value:
            yield from ordered_task_id_lists(child)


def load_head_record(path: Path) -> JsonObject:
    relative = path.relative_to(REPO).as_posix()
    payload = subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{relative}"],
        capture_output=True,
        check=True,
    ).stdout
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise AssertionError(f"{relative}: expected a JSON object")
    return value


def prepare_records(
    paths: list[Path],
) -> list[tuple[Path, JsonObject, float | None, float]]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    agentic_protocol = protocol["agentic_protocol"]
    assert protocol["protocol_id"] == INDEX_VERSION_V4_2
    assert (
        index_version_for_coverage_profile(SEASON_2_COVERAGE_PROFILE_ID)
        == INDEX_VERSION_V4_2
    )
    assert len(paths) == len(EXPECTED) == 5, [path.name for path in paths]

    loaded: list[tuple[Path, JsonObject, JsonObject]] = []
    ordered_ids_by_record: list[list[str]] = []
    for path in paths:
        before = load_head_record(path)
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record == before, f"{path.name}: working tree differs from HEAD"
        items = appworld_items(record)
        ordered_ids = [str(item["id"]) for item in items]
        assert len(ordered_ids) == agentic_protocol["task_denominator"] == 96
        assert len(set(ordered_ids)) == len(ordered_ids)
        assert (
            ordered_task_ids_sha256(ordered_ids)
            == agentic_protocol["ordered_task_ids_sha256"]
        )
        for carried_ids in ordered_task_id_lists(record):
            assert carried_ids == ordered_ids, (
                f"{path.name}: carried ordered_task_ids drifted"
            )
        agentic_run = record.get("agentic_run")
        assert isinstance(agentic_run, dict)
        assert agentic_run.get("subset_hash") == agentic_protocol["subset_sha256"]
        ordered_ids_by_record.append(ordered_ids)
        loaded.append((path, before, record))

    canonical_ids = ordered_ids_by_record[0]
    canonical_set = set(canonical_ids)
    assert all(ids == canonical_ids for ids in ordered_ids_by_record)
    assert all(set(ids) == canonical_set for ids in ordered_ids_by_record)

    prepared: list[tuple[Path, JsonObject, float | None, float]] = []
    for path, before, record in loaded:
        model = record.get("model")
        assert isinstance(model, dict) and isinstance(model.get("name"), str)
        model_name = model["name"]
        expected_agentic, expected_composite = EXPECTED[model_name]
        items = appworld_items(record)
        point = 100 * sum(item.get("correct") is True for item in items) / len(items)
        assert round(point, 2) == expected_agentic

        bfcl_before = bfcl_snapshot(record)
        old_block = record.get("season2_rescore")
        old_composite = None
        if isinstance(old_block, dict) and isinstance(
            old_block.get("composite_v4"), dict
        ):
            old_composite = old_block["composite_v4"].get("point")

        rescored = rescore_record_season2(record)
        assert rescored["index_version"] == INDEX_VERSION_V4_2
        assert rescored["source_index_version"] == "index-v4.1"
        assert rescored["missing_headline_axes"] == []
        tool_use = rescored["axes"]["tool_use"]
        assert tool_use["n"] == 96
        assert round(tool_use["point"], 2) == expected_agentic
        assert round(rescored["composite_v4"]["point"], 2) == expected_composite

        record["season2_rescore"] = rescored
        record["index_version"] = INDEX_VERSION_V4_2
        assert bfcl_snapshot(record) == bfcl_before, (
            f"{path.name}: BFCL evidence changed"
        )
        residual = disallowed_diffs(before, record)
        assert residual == [], f"{path.name}: disallowed diffs: {residual}"
        prepared.append(
            (path, record, old_composite, rescored["composite_v4"]["point"])
        )
    return prepared


def main() -> None:
    paths = sorted(RECORDS_DIR.glob("*-s2v5.json"))
    prepared = prepare_records(paths)
    for path, record, old_composite, new_composite in prepared:
        atomic_write_json(record, path)
        print(
            f"{path.stem}: composite {old_composite} -> {new_composite} | diff scoped OK"
        )
    print("RESCORE COMPLETE: 5/5 records; all v4.2 assertions passed")


if __name__ == "__main__":
    main()
