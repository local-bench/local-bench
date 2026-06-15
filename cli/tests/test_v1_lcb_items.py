from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeAlias

from localbench.scorers.lcb import build_lcb_prompt, score_lcb

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SUITE_DIR: Final = _REPO_ROOT / "suite" / "v1"
_ITEM_FILE: Final = _SUITE_DIR / "lcb.jsonl"
_EXPECTED_COUNT: Final = 129
_EXPECTED_KEYS: Final = {
    "id",
    "source_id",
    "source_dataset",
    "source_revision",
    "source_url",
    "license",
    "harness_repo",
    "harness_revision",
    "harness_license",
    "source_site",
    "source_tos_note",
    "contest_date",
    "difficulty",
    "question_id",
    "contest_id",
    "test_id",
    "question_title",
    "question_content",
    "starter_code",
    "function_name",
    "input",
    "answer",
}
_EXPECTED_DIFFICULTIES: Final = {"easy": 41, "medium": 65, "hard": 23}


def test_v1_lcb_items_are_valid_jsonl_rows_when_loaded() -> None:
    # Given the frozen suite-v1 LCB item file.
    items = _load_jsonl(_ITEM_FILE)

    # When validating row shape, provenance, ids, and date-window distribution.
    offenders: list[str] = []
    ids: set[str] = set()
    difficulties: Counter[str] = Counter()
    for index, item in enumerate(items, start=1):
        item_id = _item_id(item, index, offenders)
        if item_id in ids:
            offenders.append(f"{item_id}: duplicate id")
        ids.add(item_id)
        if set(item) != _EXPECTED_KEYS:
            offenders.append(f"{item_id}: keys {sorted(item)} != {sorted(_EXPECTED_KEYS)}")
        difficulty = _required_str(item, "difficulty", item_id, offenders)
        difficulties[difficulty] += 1
        _provenance(item, item_id, offenders)
        _date_window(item, item_id, offenders)
        for key in (
            "source_id",
            "question_id",
            "contest_id",
            "question_title",
            "question_content",
            "starter_code",
            "function_name",
            "input",
            "answer",
        ):
            _required_str(item, key, item_id, offenders)
        if not isinstance(item.get("test_id"), int):
            offenders.append(f"{item_id}: test_id must be an integer")

    # Then the itemset is stable, recent-windowed, unique, and provenance-bearing.
    assert len(items) == _EXPECTED_COUNT
    assert dict(difficulties) == _EXPECTED_DIFFICULTIES
    assert offenders == []


def test_v1_lcb_items_are_prompt_buildable_and_self_score_correct() -> None:
    # Given all frozen LCB rows.
    items = _load_jsonl(_ITEM_FILE)

    # When building prompts and scoring each stored expected output.
    offenders: list[str] = []
    for item in items:
        item_id = str(item.get("id", "<missing-id>"))
        prompt = build_lcb_prompt(item)
        if not prompt.strip():
            offenders.append(f"{item_id}: build_lcb_prompt returned blank prompt")
        score = score_lcb(item, str(item.get("answer", "")))
        if score["correct"] is not True:
            offenders.append(f"{item_id}: stored answer did not self-score correct")

    # Then every frozen item is executable-free scorable by the runtime scorer.
    assert offenders == []
    assert len(items) == _EXPECTED_COUNT


def test_v1_lcb_itemset_hash_matches_suite_and_lock() -> None:
    # Given the suite manifest and lockfile.
    suite = _read_json(_SUITE_DIR / "suite.json")
    lock = _read_json(_SUITE_DIR / "itemsets.lock.json")

    # When reading the lcb itemset references.
    suite_entry = _object(_object(_object(suite["benches"])["lcb"])["itemsets"])["standard"]
    lock_entry = _object(_object(lock["files"])["lcb.jsonl"])

    # Then suite.json and itemsets.lock.json agree on count, hash, and provenance.
    assert _object(suite_entry)["item_count"] == _EXPECTED_COUNT
    assert _object(suite_entry)["sha256"] == lock_entry["sha256"]
    assert lock_entry["item_count"] == _EXPECTED_COUNT
    assert lock_entry["source_dataset"] == "livecodebench/test_generation"
    assert lock_entry["source_revision"] == "6f3ac40bbecf81eba15899139d279b077f2816fd"
    assert lock_entry["license"] == "CC-BY-4.0"
    assert lock_entry["date_window"] == "2023-12-01..2024-03-02"
    assert lock_entry["source_tos_note"] == (
        "Problem statements originate from LeetCode; retain source-site ToS awareness."
    )


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{path.name}:{line_number} is not a JSON object")
            rows.append(parsed)
    return rows


def _read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path.name} must contain a JSON object")
    return data


def _item_id(row: Mapping[str, JsonValue], index: int, offenders: list[str]) -> str:
    expected = f"lcb-{index:03d}"
    value = row.get("id")
    if not isinstance(value, str):
        offenders.append(f"row {index}: id must be a string")
        return f"row-{index}"
    if value != expected:
        offenders.append(f"{value}: expected id {expected}")
    return value


def _provenance(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    expected = {
        "source_dataset": "livecodebench/test_generation",
        "source_revision": "6f3ac40bbecf81eba15899139d279b077f2816fd",
        "source_url": "https://huggingface.co/datasets/livecodebench/test_generation",
        "license": "CC-BY-4.0",
        "harness_repo": "https://github.com/LiveCodeBench/LiveCodeBench",
        "harness_revision": "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24",
        "harness_license": "MIT",
        "source_site": "leetcode",
        "source_tos_note": "Problem statement originates from LeetCode; retain source-site ToS awareness.",
    }
    for key, expected_value in expected.items():
        if row.get(key) != expected_value:
            offenders.append(f"{item_id}: {key} must be {expected_value!r}")


def _date_window(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    value = row.get("contest_date")
    if not isinstance(value, str) or not ("2023-12-01" <= value <= "2024-03-02"):
        offenders.append(f"{item_id}: contest_date must be in the selected recent window")


def _required_str(
    row: Mapping[str, JsonValue],
    key: str,
    item_id: str,
    offenders: list[str],
) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        offenders.append(f"{item_id}: {key} must be a non-empty string")
        return ""
    return value


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise AssertionError(f"expected object, got {type(value).__name__}")
    return value
