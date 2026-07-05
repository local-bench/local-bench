from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TypeAlias

import pytest

from localbench.scorers.math_symbolic import verify_math

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ITEM_FILES = (
    (_REPO_ROOT / "suite" / "v1" / "amo.jsonl", "amo", 39),
    (_REPO_ROOT / "suite" / "v1" / "olymmath_hard.jsonl", "olymmath-hard", 100),
)
_SCHEMA_KEYS = {"id", "statement", "answer", "max_tokens", "sampling_params"}


@pytest.mark.parametrize(("path", "id_prefix", "expected_count"), _ITEM_FILES)
def test_v1_math_items_match_schema_when_loaded(path: Path, id_prefix: str, expected_count: int) -> None:
    # Given a frozen suite-v1 math item file.
    # When loading each JSONL row.
    items = _load_jsonl(path)

    # Then every row has the exact localbench math item schema and stable unique ids.
    assert len(items) == expected_count
    ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        assert set(item) == _SCHEMA_KEYS
        item_id = _required_str(item, "id")
        assert item_id == f"{id_prefix}-{index:03d}"
        assert item_id not in ids
        ids.add(item_id)
        assert _required_str(item, "statement")
        assert _required_str(item, "answer")
        assert item["max_tokens"] == 16_384
        assert item["sampling_params"] == {"temperature": 0}


@pytest.mark.parametrize(("path", "id_prefix", "expected_count"), _ITEM_FILES)
def test_v1_math_gold_answers_self_verify_when_checked_by_symbolic_scorer(
    path: Path,
    id_prefix: str,
    expected_count: int,
) -> None:
    # Given frozen suite-v1 math gold answers.
    items = _load_jsonl(path)

    # When each gold answer is routed through the production symbolic scorer.
    failures = [
        _required_str(item, "id")
        for item in items
        if not verify_math(f"Final answer: {_required_str(item, 'answer')}", _required_str(item, "answer"))
    ]

    # Then every committed gold is parseable and equivalent to itself.
    assert len(items) == expected_count
    assert failures == [], f"{id_prefix} gold self-verify failures: {failures}"


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{path.name}:{line_number} is not a JSON object")
            rows.append(parsed)
    return rows


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise AssertionError(f"{key} must be a string")
    return value
