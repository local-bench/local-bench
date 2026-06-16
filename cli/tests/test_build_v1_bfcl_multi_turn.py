from __future__ import annotations

from collections import Counter
from typing import TypeAlias

from suite import build_v1_bfcl_multi_turn as builder

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def test_stratified_sample_when_fixed_seed_is_stable_by_category() -> None:
    # Given source rows from two multi-turn sub-categories in arbitrary order.
    rows = [
        _row("multi_turn_base_1", "multi_turn_base"),
        _row("multi_turn_base_2", "multi_turn_base"),
        _row("multi_turn_base_3", "multi_turn_base"),
        _row("multi_turn_long_context_1", "multi_turn_long_context"),
        _row("multi_turn_long_context_2", "multi_turn_long_context"),
        _row("multi_turn_long_context_3", "multi_turn_long_context"),
    ]

    # When selecting a fixed-size subset twice with different input order.
    first = builder._stratified_sample(rows, per_category=2, sample_seed="fixed")
    second = builder._stratified_sample(list(reversed(rows)), per_category=2, sample_seed="fixed")

    # Then selection and ordering are deterministic and balanced.
    assert [row["source_id"] for row in first] == [row["source_id"] for row in second]
    assert Counter(row["category"] for row in first) == {
        "multi_turn_base": 2,
        "multi_turn_long_context": 2,
    }


def test_normalize_item_when_given_source_and_answer_carries_runtime_fields() -> None:
    # Given a minimal source row and matching answer row.
    source = {
        "id": "multi_turn_base_7",
        "question": [[{"role": "user", "content": "Do the task."}]],
        "initial_config": {"MathAPI": {}},
        "path": ["MathAPI.add"],
        "involved_classes": ["MathAPI"],
        "excluded_function": [],
    }
    answer = {"id": "multi_turn_base_7", "ground_truth": [["add(a=1,b=2)"]]}

    # When normalizing into a suite item.
    item = builder._normalize_item(3, source, answer, function_docs=[{"name": "add"}])

    # Then the item keeps the data required by the confined scorer and provenance.
    assert item["id"] == "bfcl-mt-003"
    assert item["source_id"] == "multi_turn_base_7"
    assert item["category"] == "multi_turn_base"
    assert item["ground_truth"] == [["add(a=1,b=2)"]]
    assert item["function"] == [{"name": "add"}]
    assert item["source_revision"] == builder.BFCL_EVAL_REVISION


def test_datasheet_when_given_selected_items_reports_distribution() -> None:
    # Given a small selected item set.
    items = [
        _row("multi_turn_base_1", "multi_turn_base"),
        _row("multi_turn_long_context_1", "multi_turn_long_context"),
        _row("multi_turn_long_context_2", "multi_turn_long_context"),
    ]

    # When building the datasheet lines.
    datasheet = builder._datasheet_lines(items, itemset_sha256="abc123")

    # Then it reports count, hash, revision, and category distribution.
    assert "emitted=3" in datasheet
    assert "itemset_sha256=abc123" in datasheet
    assert builder.BFCL_EVAL_REVISION in datasheet
    assert "multi_turn_base: 1" in datasheet
    assert "multi_turn_long_context: 2" in datasheet


def _row(source_id: str, category: str) -> JsonObject:
    return {
        "id": source_id.replace("multi_turn", "bfcl-mt"),
        "source_id": source_id,
        "category": category,
        "turn_count": 1,
        "involved_classes": ["MathAPI"],
        "question": [[{"role": "user", "content": source_id}]],
        "initial_config": {"MathAPI": {}},
        "path": ["MathAPI.add"],
        "excluded_function": [],
        "function": [{"name": "add"}],
        "ground_truth": [["add(a=1,b=2)"]],
        "source_dataset": builder.SOURCE_DATASET,
        "source_revision": builder.BFCL_EVAL_REVISION,
        "license": builder.BFCL_EVAL_LICENSE,
    }
