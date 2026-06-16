from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeAlias

from localbench.scorers.bfcl_multi_turn import build_bfcl_multi_turn_prompt, score_bfcl_multi_turn

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SUITE_DIR: Final = _REPO_ROOT / "suite" / "v1"
_ITEM_FILE: Final = _SUITE_DIR / "bfcl_multi_turn.jsonl"
_EXPECTED_COUNT: Final = 100
_EXPECTED_COUNTS: Final = {"multi_turn_base": 50, "multi_turn_long_context": 50}
_EXPECTED_KEYS: Final = {
    "id",
    "source_id",
    "category",
    "turn_count",
    "involved_classes",
    "question",
    "initial_config",
    "path",
    "excluded_function",
    "function",
    "ground_truth",
    "source_dataset",
    "source_revision",
    "license",
}


def test_v1_bfcl_multi_turn_items_are_valid_jsonl_rows_when_loaded() -> None:
    # Given the frozen suite-v1 BFCL multi-turn item file.
    items = _load_jsonl(_ITEM_FILE)

    # When validating shape, ids, provenance, and category distribution.
    offenders: list[str] = []
    ids: set[str] = set()
    categories: Counter[str] = Counter()
    for index, item in enumerate(items, start=1):
        item_id = _item_id(item, index, offenders)
        if item_id in ids:
            offenders.append(f"{item_id}: duplicate id")
        ids.add(item_id)
        if set(item) != _EXPECTED_KEYS:
            offenders.append(f"{item_id}: keys {sorted(item)} != {sorted(_EXPECTED_KEYS)}")
        categories[_required_str(item, "category", item_id, offenders)] += 1
        _required_str(item, "source_id", item_id, offenders)
        _provenance(item, item_id, offenders)
        for key in ("question", "function", "ground_truth", "involved_classes", "path"):
            if not isinstance(item.get(key), list) or not item[key]:
                offenders.append(f"{item_id}: {key} must be a non-empty list")
        if not isinstance(item.get("initial_config"), dict):
            offenders.append(f"{item_id}: initial_config must be an object")
        if not isinstance(item.get("turn_count"), int) or int(item["turn_count"]) < 1:
            offenders.append(f"{item_id}: turn_count must be a positive integer")

    # Then the itemset is stable, unique, balanced, and provenance-bearing.
    assert len(items) == _EXPECTED_COUNT
    assert dict(categories) == _EXPECTED_COUNTS
    assert offenders == []


def test_v1_bfcl_multi_turn_items_are_prompt_buildable_and_self_score_correct() -> None:
    # Given all frozen BFCL multi-turn rows.
    items = _load_jsonl(_ITEM_FILE)

    # When building prompts and scoring each stored trace.
    offenders: list[str] = []
    for item in items:
        item_id = str(item.get("id", "<missing-id>"))
        prompt = build_bfcl_multi_turn_prompt(item)
        if not prompt.strip():
            offenders.append(f"{item_id}: build_bfcl_multi_turn_prompt returned blank prompt")
        response = json.dumps(item["ground_truth"])
        score = score_bfcl_multi_turn(item, response)
        if score["correct"] is not True:
            offenders.append(f"{item_id}: stored trace did not self-score correct: {score}")

    # Then every frozen item is scorable under the confined runtime.
    assert offenders == []
    assert len(items) == _EXPECTED_COUNT


def test_v1_bfcl_multi_turn_itemset_hash_matches_suite_and_lock() -> None:
    # Given the suite manifest, lockfile, and emitted itemset.
    suite = _read_json(_SUITE_DIR / "suite.json")
    lock = _read_json(_SUITE_DIR / "itemsets.lock.json")
    digest = hashlib.sha256(_ITEM_FILE.read_bytes()).hexdigest()

    # When reading bfcl_multi_turn references.
    suite_entry = _object(_object(_object(suite["benches"])["bfcl_multi_turn"])["itemsets"])["standard"]
    lock_entry = _object(_object(lock["files"])["bfcl_multi_turn.jsonl"])

    # Then suite.json and itemsets.lock.json agree on count, hash, and pinned BFCL provenance.
    assert _object(suite_entry)["item_count"] == _EXPECTED_COUNT
    assert _object(suite_entry)["sha256"] == digest
    assert lock_entry["sha256"] == digest
    assert lock_entry["item_count"] == _EXPECTED_COUNT
    assert lock_entry["source_dataset"] == "vendored bfcl-eval BFCL_v4_multi_turn_base+long_context"
    assert lock_entry["source_revision"] == "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
    assert lock_entry["license"] == "Apache-2.0"


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
    expected = f"bfcl-mt-{index:03d}"
    value = row.get("id")
    if not isinstance(value, str):
        offenders.append(f"row {index}: id must be a string")
        return f"row-{index}"
    if value != expected:
        offenders.append(f"{value}: expected id {expected}")
    return value


def _provenance(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    expected = {
        "source_dataset": "vendored bfcl-eval BFCL_v4_multi_turn_base+long_context",
        "source_revision": "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8",
        "license": "Apache-2.0",
    }
    for key, expected_value in expected.items():
        if row.get(key) != expected_value:
            offenders.append(f"{item_id}: {key} must be {expected_value!r}")


def _required_str(row: Mapping[str, JsonValue], key: str, item_id: str, offenders: list[str]) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        offenders.append(f"{item_id}: {key} must be a non-empty string")
        return ""
    return value


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise AssertionError("expected object")
    return value
