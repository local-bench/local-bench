from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, TypeAlias

from datasets import load_dataset

DATASET_ID: Final = "livecodebench/test_generation"
DATASET_REVISION: Final = "6f3ac40bbecf81eba15899139d279b077f2816fd"
DATASET_LICENSE: Final = "CC-BY-4.0"
DATASET_URL: Final = "https://huggingface.co/datasets/livecodebench/test_generation"
HARNESS_REPO: Final = "https://github.com/LiveCodeBench/LiveCodeBench"
HARNESS_REVISION: Final = "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"
HARNESS_LICENSE: Final = "MIT"
SOURCE_SITE: Final = "leetcode"
SOURCE_TOS_NOTE: Final = "Problem statement originates from LeetCode; retain source-site ToS awareness."
WINDOW_START: Final = "2023-12-01"
WINDOW_END: Final = "2024-03-02"
ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "lcb.jsonl"

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def main() -> int:
    rows = _load_rows()
    selected = [_normalize_item(index, row) for index, row in enumerate(rows, start=1)]
    _write_jsonl(OUT_PATH, selected)
    print(f"wrote {len(selected)} rows to {OUT_PATH}")
    return 0


def _load_rows() -> list[Mapping[str, JsonValue]]:
    dataset = load_dataset(DATASET_ID, split="test", revision=DATASET_REVISION)
    rows = [_json_object(row) for row in dataset]
    selected = [
        row
        for row in rows
        if WINDOW_START <= _contest_date(row) <= WINDOW_END
    ]
    return sorted(
        selected,
        key=lambda row: (
            _contest_date(row),
            _required_str(row, "question_id"),
            _required_int(row, "test_id"),
        ),
    )


def _normalize_item(index: int, row: Mapping[str, JsonValue]) -> JsonObject:
    question_id = _required_str(row, "question_id")
    test_id = _required_int(row, "test_id")
    test = _single_test(row)
    return {
        "id": f"lcb-{index:03d}",
        "source_id": f"{question_id}:{test_id}",
        "source_dataset": DATASET_ID,
        "source_revision": DATASET_REVISION,
        "source_url": DATASET_URL,
        "license": DATASET_LICENSE,
        "harness_repo": HARNESS_REPO,
        "harness_revision": HARNESS_REVISION,
        "harness_license": HARNESS_LICENSE,
        "source_site": SOURCE_SITE,
        "source_tos_note": SOURCE_TOS_NOTE,
        "contest_date": _contest_date(row),
        "difficulty": _required_str(row, "difficulty"),
        "question_id": question_id,
        "contest_id": _required_str(row, "contest_id"),
        "test_id": test_id,
        "question_title": _required_str(row, "question_title"),
        "question_content": _required_str(row, "question_content"),
        "starter_code": _required_str(row, "starter_code"),
        "function_name": _required_str(row, "function_name"),
        "input": _required_str(test, "input"),
        "answer": _required_str(test, "output"),
    }


def _single_test(row: Mapping[str, JsonValue]) -> JsonObject:
    tests = json.loads(_required_str(row, "test"))
    if not isinstance(tests, list) or len(tests) != 1:
        raise TypeError(f"{row.get('question_id')}: expected exactly one test case")
    test = tests[0]
    if not isinstance(test, dict):
        raise TypeError(f"{row.get('question_id')}: test case must be an object")
    return {str(key): value for key, value in test.items() if isinstance(key, str)}


def _contest_date(row: Mapping[str, JsonValue]) -> str:
    value = row.get("contest_date")
    if not isinstance(value, str):
        value = str(value)
    return value[:10]


def _json_object(row: Mapping[str, object]) -> JsonObject:
    result: JsonObject = {}
    for key, value in row.items():
        if isinstance(value, str | int | float | bool) or value is None:
            result[key] = value
        else:
            result[key] = str(value)
    return result


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _required_int(row: Mapping[str, JsonValue], key: str) -> int:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
