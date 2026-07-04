from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeAlias

from localbench.scorers.ifbench import INSTRUCTION_DICT, score_ifbench

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_ITEM_FILE: Final = _REPO_ROOT / "suite" / "v1" / "ifbench.jsonl"
_EXPECTED_COUNT: Final = 294
_SCHEMA_KEYS: Final = {"id", "key", "prompt", "instruction_id_list", "kwargs"}


def test_v1_ifbench_items_are_valid_jsonl_rows_when_loaded() -> None:
    # Given the frozen suite-v1 IFBench item file.
    # When loading each JSONL row.
    items = _load_jsonl(_ITEM_FILE)

    # Then every row has the localbench IFBench schema and stable unique ids.
    assert len(items) == _EXPECTED_COUNT
    offenders: list[str] = []
    ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        item_id = _item_id(item, index, offenders)
        if item_id in ids:
            offenders.append(f"{item_id}: duplicate id")
        ids.add(item_id)
        if set(item) != _SCHEMA_KEYS:
            offenders.append(f"{item_id}: keys {sorted(item)} != {sorted(_SCHEMA_KEYS)}")
        _required_str(item, "key", item_id, offenders)
        _required_str(item, "prompt", item_id, offenders)
        instruction_ids = _instruction_ids(item, item_id, offenders)
        kwargs = _kwargs(item, item_id, offenders)
        if len(instruction_ids) != len(kwargs):
            offenders.append(f"{item_id}: instruction_id_list and kwargs lengths differ")

    assert offenders == []


def test_v1_ifbench_items_are_all_recognized_by_score_ifbench() -> None:
    # Given all frozen IFBench rows.
    items = _load_jsonl(_ITEM_FILE)

    # When checking each instruction id against the vendored scorer registry and scorer boundary.
    offenders: list[str] = []
    for item in items:
        item_id = str(item.get("id", "<missing-id>"))
        instruction_ids = _instruction_ids(item, item_id, offenders)
        unknown = [instruction_id for instruction_id in instruction_ids if instruction_id not in INSTRUCTION_DICT]
        if unknown:
            offenders.append(f"{item_id}: unsupported IFBench instruction ids {unknown}")
            continue
        result = score_ifbench(item, "")
        if len(result["per_instruction"]) != len(instruction_ids):
            offenders.append(
                f"{item_id}: score_ifbench returned {len(result['per_instruction'])} results "
                f"for {len(instruction_ids)} instructions",
            )

    # Then the itemset cannot contain any unscorable IFBench constraint IDs.
    assert offenders == []


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{path.name}:{line_number} is not a JSON object")
            rows.append(parsed)
    return rows


def _item_id(row: Mapping[str, JsonValue], index: int, offenders: list[str]) -> str:
    expected = f"ifbench-{index:03d}"
    value = row.get("id")
    if not isinstance(value, str):
        offenders.append(f"row {index}: id must be a string")
        return f"row-{index}"
    if value != expected:
        offenders.append(f"{value}: expected id {expected}")
    return value


def _required_str(row: Mapping[str, JsonValue], key: str, item_id: str, offenders: list[str]) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        offenders.append(f"{item_id}: {key} must be a non-empty string")
        return ""
    return value


def _instruction_ids(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> list[str]:
    value = row.get("instruction_id_list")
    if not isinstance(value, list):
        offenders.append(f"{item_id}: instruction_id_list must be a list")
        return []
    ids = [instruction_id for instruction_id in value if isinstance(instruction_id, str) and instruction_id]
    if len(ids) != len(value):
        offenders.append(f"{item_id}: instruction_id_list contains non-string/blank entries")
    return ids


def _kwargs(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> list[Mapping[str, JsonValue]]:
    value = row.get("kwargs")
    if not isinstance(value, list):
        offenders.append(f"{item_id}: kwargs must be a list")
        return []
    kwargs = [item for item in value if isinstance(item, dict)]
    if len(kwargs) != len(value):
        offenders.append(f"{item_id}: kwargs contains non-object entries")
    return kwargs
