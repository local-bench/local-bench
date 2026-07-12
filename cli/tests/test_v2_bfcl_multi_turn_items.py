from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from localbench._scoring import score_bench
from localbench._suite import RenderedBench, read_json_object, render_benches
from localbench._types import ItemResult, Usage
from localbench.scorers.bfcl_multi_turn import (
    BFCL_MULTI_TURN_BENCHES,
    build_bfcl_multi_turn_prompt,
    score_bfcl_multi_turn,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v2"
_V1_ITEM_FILE = _REPO_ROOT / "suite" / "v1" / "bfcl_multi_turn.jsonl"
_BENCH_CATEGORIES = {
    "bfcl_multi_turn_base": "multi_turn_base",
    "bfcl_multi_turn_long_context": "multi_turn_long_context",
}
_COPIED_ITEMSETS = (
    "mmlu_pro.jsonl",
    "ifbench.jsonl",
    "tc_json_v1.jsonl",
    "bigcodebench_hard.jsonl",
    "olymmath_hard.jsonl",
    "amo.jsonl",
    "ruler_32k.jsonl",
    "bfcl.jsonl",
)


def test_v2_suite_replaces_combined_bench_and_preserves_partition() -> None:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    assert suite["version"] == "suite-v2"
    assert "bfcl_multi_turn" not in suite["benches"]
    assert set(_BENCH_CATEGORIES) <= set(suite["benches"])

    original = _load_jsonl(_V1_ITEM_FILE)
    split = [
        row
        for bench in _BENCH_CATEGORIES
        for row in _load_jsonl(_SUITE_DIR / f"{bench}.jsonl")
    ]
    assert len(split) == 100
    assert len({str(row["source_id"]) for row in split}) == 100
    assert _by_source_id(split) == _by_source_id(original)


def test_v2_unchanged_itemsets_and_templates_are_byte_for_byte_copies() -> None:
    for relative_path in _COPIED_ITEMSETS:
        assert (_SUITE_DIR / relative_path).read_bytes() == (
            _REPO_ROOT / "suite" / "v1" / relative_path
        ).read_bytes()

    v1_templates = _REPO_ROOT / "suite" / "v1" / "templates"
    v2_templates = _SUITE_DIR / "templates"
    assert {path.name for path in v2_templates.iterdir()} == {
        path.name for path in v1_templates.iterdir()
    }
    for source in v1_templates.iterdir():
        assert (v2_templates / source.name).read_bytes() == source.read_bytes()


@pytest.mark.parametrize(("bench", "category"), _BENCH_CATEGORIES.items())
def test_v2_split_items_self_score_and_match_manifest(
    bench: str,
    category: str,
) -> None:
    item_file = _SUITE_DIR / f"{bench}.jsonl"
    items = _load_jsonl(item_file)
    suite = read_json_object(_SUITE_DIR / "suite.json")
    lock = read_json_object(_SUITE_DIR / "itemsets.lock.json")
    digest = hashlib.sha256(item_file.read_bytes()).hexdigest()

    assert len(items) == 50
    assert Counter(str(item["category"]) for item in items) == {category: 50}
    assert all(build_bfcl_multi_turn_prompt(item).strip() for item in items)
    assert all(
        score_bfcl_multi_turn(item, json.dumps(item["ground_truth"]))["correct"] is True
        for item in items
    )
    itemset = suite["benches"][bench]["itemsets"]["standard"]
    assert itemset["item_count"] == 50
    assert itemset["sha256"] == digest
    assert lock["files"][f"{bench}.jsonl"]["sha256"] == digest


@pytest.mark.parametrize("bench", _BENCH_CATEGORIES)
def test_v2_split_bench_routes_prompt_readiness_and_scoring_through_shared_impl(
    bench: str,
) -> None:
    rendered = _render(bench)
    item = rendered.source_items[0]
    result = _result(rendered.benchmark_items[0]["id"], json.dumps(item["ground_truth"]))

    scored = score_bench(rendered, [result])

    assert bench in BFCL_MULTI_TURN_BENCHES
    assert "Return only a JSON array" in rendered.benchmark_items[0]["messages"][0]["content"]
    assert scored[0]["bench"] == bench
    assert scored[0]["correct"] is True
    assert scored[0]["failure_kind"] is None


def _render(bench: str) -> RenderedBench:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    warnings: list[str] = []
    rendered = render_benches(bench, "standard", 1, _SUITE_DIR, suite, warnings)
    assert warnings == []
    assert len(rendered) == 1
    return rendered[0]


def _result(item_id: str, response_text: str) -> ItemResult:
    usage: Usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "id": item_id,
        "response_text": response_text,
        "reasoning_text": None,
        "finish_reason": "stop",
        "usage": usage,
        "latency_seconds": 0.0,
        "started_at": "2026-07-12T00:00:00+10:00",
        "finished_at": "2026-07-12T00:00:00+10:00",
        "attempts": 1,
        "error": None,
    }


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _by_source_id(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["source_id"]): row for row in rows}
