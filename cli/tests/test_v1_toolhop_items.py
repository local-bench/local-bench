from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeAlias

from localbench.scorers.toolhop import build_toolhop_prompt, score_toolhop

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SUITE_DIR: Final = _REPO_ROOT / "suite" / "v1"
_ITEM_FILE: Final = _SUITE_DIR / "toolhop.jsonl"
_EXPECTED_COUNT: Final = 100
_EXPECTED_KEYS: Final = {
    "id",
    "source_id",
    "question",
    "answer",
    "sub_task",
    "tools",
    "functions",
    "domain",
    "category",
    "answer_type",
    "previous_answer_type",
    "hop_count",
    "gold_calls",
    "source_dataset",
    "source_revision",
    "source_repo",
    "license",
    "code_license",
}


def test_v1_toolhop_items_are_valid_jsonl_rows_when_loaded() -> None:
    # Given the frozen suite-v1 ToolHop item file.
    items = _load_jsonl(_ITEM_FILE)

    # When validating shape, ids, provenance, and minimum stratification.
    offenders: list[str] = []
    ids: set[str] = set()
    categories: Counter[str] = Counter()
    hop_counts: Counter[int] = Counter()
    gold_trace_count = 0
    for index, item in enumerate(items, start=1):
        item_id = _item_id(item, index, offenders)
        if item_id in ids:
            offenders.append(f"{item_id}: duplicate id")
        ids.add(item_id)
        if set(item) != _EXPECTED_KEYS:
            offenders.append(f"{item_id}: keys {sorted(item)} != {sorted(_EXPECTED_KEYS)}")
        categories[_required_str(item, "category", item_id, offenders)] += 1
        hop_count = item.get("hop_count")
        if isinstance(hop_count, int):
            hop_counts[hop_count] += 1
        else:
            offenders.append(f"{item_id}: hop_count must be an integer")
        _provenance(item, item_id, offenders)
        for key in ("question", "answer", "domain", "answer_type", "previous_answer_type"):
            _required_str(item, key, item_id, offenders)
        for key in ("sub_task", "tools"):
            if not isinstance(item.get(key), dict) or not item[key]:
                offenders.append(f"{item_id}: {key} must be a non-empty object")
        for key in ("functions", "gold_calls"):
            if not isinstance(item.get(key), list):
                offenders.append(f"{item_id}: {key} must be a list")
        if item.get("gold_calls"):
            gold_trace_count += 1

    # Then the itemset is stable, unique, provenance-bearing, and multi-stratum.
    assert len(items) == _EXPECTED_COUNT
    assert len(categories) >= 12
    assert set(hop_counts) >= {3, 4, 5}
    assert gold_trace_count >= 8
    assert offenders == []


def test_v1_toolhop_items_are_prompt_buildable_and_real_gold_traces_score() -> None:
    # Given all frozen ToolHop rows.
    items = _load_jsonl(_ITEM_FILE)

    # When building prompts and scoring real emitted rows that have extracted gold calls.
    offenders: list[str] = []
    scored_gold = 0
    for item in items:
        item_id = str(item.get("id", "<missing-id>"))
        prompt = build_toolhop_prompt(item)
        if not prompt.strip():
            offenders.append(f"{item_id}: build_toolhop_prompt returned blank prompt")
        if item.get("gold_calls") and scored_gold < 5:
            score = score_toolhop(item, json.dumps(item["gold_calls"]))
            scored_gold += 1
            if score["correct"] is not True:
                offenders.append(f"{item_id}: gold_calls did not self-score correct: {score}")

    # Then prompts render for every item and a sample of real gold traces runs end-to-end.
    assert scored_gold == 5
    assert offenders == []
    assert len(items) == _EXPECTED_COUNT


def test_v1_toolhop_itemset_hash_matches_suite_and_lock() -> None:
    # Given the suite manifest, lockfile, and emitted itemset.
    suite = _read_json(_SUITE_DIR / "suite.json")
    lock = _read_json(_SUITE_DIR / "itemsets.lock.json")
    digest = hashlib.sha256(_ITEM_FILE.read_bytes()).hexdigest()

    # When reading toolhop references.
    suite_entry = _object(_object(_object(suite["benches"])["toolhop"])["itemsets"])["standard"]
    lock_entry = _object(_object(lock["files"])["toolhop.jsonl"])

    # Then suite.json and itemsets.lock.json agree on count, hash, and pinned provenance.
    assert _object(suite_entry)["item_count"] == _EXPECTED_COUNT
    assert _object(suite_entry)["sha256"] == digest
    assert lock_entry["sha256"] == digest
    assert lock_entry["item_count"] == _EXPECTED_COUNT
    assert lock_entry["source_dataset"] == "bytedance-research/ToolHop"
    assert lock_entry["source_revision"] == "b439d7279af359fda46e8117ae4f0245b75f5c6b"
    assert lock_entry["license"] == "CC-BY-4.0"
    assert lock_entry["code_license"] == "Apache-2.0"
    assert lock_entry["skipped_for_confinement"] > 0


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
    expected = f"toolhop-{index:03d}"
    value = row.get("id")
    if not isinstance(value, str):
        offenders.append(f"row {index}: id must be a string")
        return f"row-{index}"
    if value != expected:
        offenders.append(f"{value}: expected id {expected}")
    return value


def _provenance(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    expected = {
        "source_dataset": "bytedance-research/ToolHop",
        "source_revision": "b439d7279af359fda46e8117ae4f0245b75f5c6b",
        "source_repo": "https://huggingface.co/datasets/bytedance-research/ToolHop",
        "license": "CC-BY-4.0",
        "code_license": "Apache-2.0",
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
