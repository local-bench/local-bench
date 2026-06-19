from __future__ import annotations

import hashlib
import json
from pathlib import Path

_SUITE = Path(__file__).resolve().parents[2] / "suite" / "v1"
_JSONL = _SUITE / "bigcodebench_hard.jsonl"
_EXPECTED_COUNT = 148
_REQUIRED = (
    "id", "source_id", "source_dataset", "source_revision", "license", "lane",
    "entry_point", "instruct_prompt", "complete_prompt", "code_prompt", "test", "libs",
)


def _items() -> list[dict]:
    return [json.loads(line) for line in _JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_bigcodebench_items_count_and_deterministic_ids() -> None:
    items = _items()
    assert len(items) == _EXPECTED_COUNT
    ids = [item["id"] for item in items]
    assert ids == [f"bcbh-{index:03d}" for index in range(1, _EXPECTED_COUNT + 1)]


def test_bigcodebench_items_have_required_exec_fields() -> None:
    for item in _items():
        for key in _REQUIRED:
            assert isinstance(item.get(key), str) and item[key].strip(), f"{item.get('id')} missing {key}"
        assert item["lane"] == "exec"
        # Each task ships its own unit tests (which the sandbox runs against the generation).
        assert "TestCase" in item["test"]
        assert item["source_id"].startswith("BigCodeBench/")


def test_bigcodebench_hash_matches_suite_and_lock() -> None:
    digest = hashlib.sha256(_JSONL.read_bytes()).hexdigest()
    suite_entry = json.loads((_SUITE / "suite.json").read_text(encoding="utf-8"))["benches"]["bigcodebench_hard"]
    lock_entry = json.loads((_SUITE / "itemsets.lock.json").read_text(encoding="utf-8"))["files"]["bigcodebench_hard.jsonl"]
    assert suite_entry["itemsets"]["standard"]["sha256"] == digest
    assert suite_entry["itemsets"]["standard"]["item_count"] == _EXPECTED_COUNT
    assert suite_entry["lane"] == "exec"
    assert lock_entry["sha256"] == digest
    assert lock_entry["item_count"] == _EXPECTED_COUNT
