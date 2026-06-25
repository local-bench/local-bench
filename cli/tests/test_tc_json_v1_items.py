from __future__ import annotations

import hashlib
import json
from pathlib import Path

from localbench.scorers.tc_json_v1 import build_tc_json_prompt, score_tc_json_v1

REPO_ROOT = Path(__file__).resolve().parents[2]
ITEM_FILE = REPO_ROOT / "suite" / "v1" / "tc_json_v1.jsonl"
SUITE_FILE = REPO_ROOT / "suite" / "v1" / "suite.json"
LOCK_FILE = REPO_ROOT / "suite" / "v1" / "itemsets.lock.json"
TEMPLATE_FILE = REPO_ROOT / "suite" / "v1" / "templates" / "tc_json_v1.txt"


def test_tc_json_v1_items_when_loaded_have_expected_counts_and_suite_metadata() -> None:
    items = _load_items()
    suite = json.loads(SUITE_FILE.read_text(encoding="utf-8"))
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    digest = hashlib.sha256(ITEM_FILE.read_bytes()).hexdigest()

    assert len(items) == 330
    assert sum(1 for item in items if item["stratum"] == "bfcl_backbone") == 300
    assert sum(1 for item in items if item["stratum"] == "fresh_common_tools") == 30
    assert suite["benches"]["tc_json_v1"]["chance_correction_baseline"] == 0.0
    assert suite["benches"]["tc_json_v1"]["itemsets"]["standard"]["item_count"] == 330
    assert suite["benches"]["tc_json_v1"]["itemsets"]["standard"]["sha256"] == digest
    assert lock["files"]["tc_json_v1.jsonl"]["sha256"] == digest
    assert "tc_json_v1" not in json.dumps(suite.get("axes", {}))


def test_tc_json_v1_items_when_gold_calls_are_scored_all_pass() -> None:
    items = _load_items()

    failures: list[str] = []
    for item in items:
        response = json.dumps({"schema_version": "localbench.tc.v1", "calls": item["gold"]["calls"]}, ensure_ascii=False)
        score = score_tc_json_v1(item, response)
        if not score["correct"]:
            failures.append(f"{item['id']}: {score['failure_reason']} {score['diagnostics']}")

    assert failures == []


def test_tc_json_v1_items_when_prompt_built_include_catalog_request_and_schema_rules() -> None:
    item = _load_items()[0]
    template = TEMPLATE_FILE.read_text(encoding="utf-8")

    prompt = build_tc_json_prompt(item, template)

    assert item["prompt"] in prompt
    assert item["tools"][0]["name"] in prompt
    assert "localbench.tc.v1" in prompt
    assert "Do not use markdown fences" in prompt


def _load_items() -> list[dict[str, object]]:
    return [json.loads(line) for line in ITEM_FILE.read_text(encoding="utf-8").splitlines() if line]
