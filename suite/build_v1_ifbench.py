from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeAlias

DATASET_ID: Final = "allenai/IFBench_test"
DATASET_REVISION: Final = "2e8a48de45ff3bf41242f927254ca81b59ca3ae2"
SPLIT: Final = "train"
EXPECTED_COUNT: Final = 294
EXCLUDED_INSTRUCTION_IDS: Final = frozenset({"words:start_verb"})
ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "ifbench.jsonl"

try:
    from datasets import Dataset, load_dataset
except ModuleNotFoundError as error:
    message = "Missing build dependency: run `cli/.venv/Scripts/python -m pip install -e cli[build]`."
    raise SystemExit(message) from error

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = _load_rows()
    filtered_rows = [row for row in rows if not _has_excluded_instruction(row)]
    normalized = [
        _normalize_row(row, index)
        for index, row in enumerate(sorted(filtered_rows, key=_source_key), start=1)
    ]
    if len(normalized) != EXPECTED_COUNT:
        raise ValueError(f"Expected {EXPECTED_COUNT} IFBench rows, found {len(normalized)}.")
    _write_jsonl(OUT_PATH, normalized)
    return 0


def _load_rows() -> list[Mapping[str, JsonValue]]:
    dataset = load_dataset(
        DATASET_ID,
        split=SPLIT,
        revision=DATASET_REVISION,
    )
    if not isinstance(dataset, Dataset):
        raise TypeError(f"Expected Dataset for {DATASET_ID}/{SPLIT}.")
    return [dict(row) for row in dataset]


def _normalize_row(row: Mapping[str, JsonValue], index: int) -> JsonObject:
    instruction_ids = _required_str_list(row, "instruction_id_list")
    kwargs = _required_object_list(row, "kwargs")
    if len(instruction_ids) != len(kwargs):
        raise ValueError(f"Row {row.get('key')} has mismatched instruction_id_list and kwargs lengths.")
    return {
        "id": f"ifbench-{index:03d}",
        "key": _required_str(row, "key"),
        "prompt": _required_str(row, "prompt"),
        "instruction_id_list": instruction_ids,
        "kwargs": [_clean_kwargs(item) for item in kwargs],
    }


def _has_excluded_instruction(row: Mapping[str, JsonValue]) -> bool:
    instruction_ids = _required_str_list(row, "instruction_id_list")
    return bool(EXCLUDED_INSTRUCTION_IDS.intersection(instruction_ids))


def _clean_kwargs(kwargs: Mapping[str, JsonValue]) -> JsonObject:
    cleaned: JsonObject = {}
    for key, value in sorted(kwargs.items()):
        if value is None:
            continue
        cleaned[key] = _json_value(value)
    return cleaned


def _json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in sorted(value.items()) if item is not None}
    return value


def _source_key(row: Mapping[str, JsonValue]) -> int:
    return int(_required_str(row, "key"))


def _write_jsonl(path: Path, rows: list[JsonObject]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string.")
    return value


def _required_str_list(row: Mapping[str, JsonValue], key: str) -> list[str]:
    value = row[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list.")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must contain only strings.")
    return list(value)


def _required_object_list(row: Mapping[str, JsonValue], key: str) -> list[Mapping[str, JsonValue]]:
    value = row[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list.")
    if not all(isinstance(item, dict) for item in value):
        raise TypeError(f"{key} must contain only objects.")
    return [item for item in value if isinstance(item, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
