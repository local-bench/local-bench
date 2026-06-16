from __future__ import annotations

from collections import Counter
from typing import TypeAlias

from suite import build_v1_toolhop as builder

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def test_toolhop_row_validation_when_tool_needs_unsafe_import_returns_skip_reason() -> None:
    # Given a source row whose tool imports a forbidden module.
    row = _row(
        7,
        functions=["def unsafe_tool():\n    import os\n    return os.system('echo x')\n"],
        tool_names=["unsafe_tool"],
    )

    # When validating the row for confined execution.
    result = builder._validate_candidate(row)

    # Then it is skipped instead of relaxing the executor.
    assert result.accepted is False
    assert "unsafe_module:os" in result.reasons


def test_toolhop_row_validation_when_gold_examples_are_literal_extracts_calls() -> None:
    # Given a row with a top-level literal example call after each function.
    row = _row(
        8,
        functions=[
            "def first_tool(name):\n    return name\n\nresult = first_tool('Ada')\n",
            "def second_tool(number):\n    return number\n\nprint(second_tool(15))\n",
        ],
        tool_names=["first_tool", "second_tool"],
    )

    # When normalizing the candidate.
    item = builder._normalize_item(1, row, gold_calls=["first_tool('Ada')", "second_tool(15)"])

    # Then the emitted item carries the scorer fields and optional golden trace.
    assert item["id"] == "toolhop-001"
    assert item["source_id"] == 8
    assert item["hop_count"] == 2
    assert item["category"] == "history"
    assert item["gold_calls"] == ["first_tool('Ada')", "second_tool(15)"]
    assert item["source_revision"] == builder.TOOLHOP_REVISION
    assert item["license"] == "CC-BY-4.0"


def test_stratified_sample_when_fixed_seed_is_stable_by_hop_and_category() -> None:
    # Given rows across hop/category strata in arbitrary order.
    rows = [
        _normalized("toolhop-src-1", "history", 3),
        _normalized("toolhop-src-2", "history", 3),
        _normalized("toolhop-src-3", "film", 3),
        _normalized("toolhop-src-4", "film", 4),
        _normalized("toolhop-src-5", "math", 4),
        _normalized("toolhop-src-6", "math", 5),
    ]

    # When sampling twice with reversed input order.
    first = builder._stratified_sample(rows, target_count=4, sample_seed="fixed")
    second = builder._stratified_sample(list(reversed(rows)), target_count=4, sample_seed="fixed")

    # Then output order is deterministic and covers hop/category strata.
    assert [row["source_id"] for row in first] == [row["source_id"] for row in second]
    assert len(first) == 4
    assert len({(row["category"], row["hop_count"]) for row in first}) == 4


def test_datasheet_when_given_selected_and_skipped_items_reports_distribution() -> None:
    # Given selected rows and skip reasons from validation.
    items = [
        _normalized("toolhop-src-1", "history", 3),
        _normalized("toolhop-src-2", "film", 4),
        _normalized("toolhop-src-3", "film", 4),
    ]
    skipped = Counter({"missing_module:pytz": 2, "unsafe_module:os": 1})

    # When building datasheet lines.
    datasheet = builder._datasheet_lines(items, skipped=skipped, itemset_sha256="abc123")

    # Then provenance, hash, distribution, and skipped counts are reported.
    assert "source_dataset=bytedance-research/ToolHop" in datasheet
    assert f"toolhop_revision={builder.TOOLHOP_REVISION}" in datasheet
    assert "emitted=3" in datasheet
    assert "itemset_sha256=abc123" in datasheet
    assert "history: 1" in datasheet
    assert "hop_4: 2" in datasheet
    assert "missing_module:pytz: 2" in datasheet
    assert "unsafe_module:os: 1" in datasheet


def _row(row_id: int, *, functions: list[str], tool_names: list[str]) -> JsonObject:
    return {
        "id": row_id,
        "question": "Synthetic ToolHop question?",
        "answer": "15",
        "sub_task": {
            "First subtask?": "Ada",
            "Second subtask?": "15",
        },
        "tools": {
            name: {
                "name": name,
                "description": f"Synthetic {name} tool.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
            for name in tool_names
        },
        "functions": functions,
        "domain": "History",
        "answer_type": "number",
        "previous_answer_type": "string",
    }


def _normalized(source_id: str, category: str, hop_count: int) -> JsonObject:
    return {
        "id": "placeholder",
        "source_id": source_id,
        "question": "Synthetic?",
        "answer": "1",
        "sub_task": {},
        "tools": {},
        "functions": [],
        "domain": category,
        "category": category,
        "answer_type": "number",
        "previous_answer_type": "string",
        "hop_count": hop_count,
        "gold_calls": [],
        "source_dataset": builder.SOURCE_DATASET,
        "source_revision": builder.TOOLHOP_REVISION,
        "source_repo": builder.TOOLHOP_REPO,
        "license": "CC-BY-4.0",
        "code_license": "Apache-2.0",
    }
