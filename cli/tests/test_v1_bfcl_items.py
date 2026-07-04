from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypeAlias

from localbench.scorers.bfcl import build_bfcl_prompt, score_bfcl

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_ITEM_FILE: Final = _REPO_ROOT / "suite" / "v1" / "bfcl.jsonl"
_EXPECTED_COUNT: Final = 300
_EXPECTED_KEYS: Final = {"id", "source_id", "category", "question", "function", "possible_answer"}
_EXPECTED_COUNTS: Final = {"simple": 75, "multiple": 75, "parallel": 75, "parallel_multiple": 75}


def test_v1_bfcl_items_are_valid_jsonl_rows_when_loaded() -> None:
    # Given the frozen suite-v1 BFCL item file.
    items = _load_jsonl(_ITEM_FILE)

    # When validating row shape, ids, and category distribution.
    offenders: list[str] = []
    ids: set[str] = set()
    counts = dict.fromkeys(_EXPECTED_COUNTS, 0)
    for index, item in enumerate(items, start=1):
        item_id = _item_id(item, index, offenders)
        if item_id in ids:
            offenders.append(f"{item_id}: duplicate id")
        ids.add(item_id)
        if set(item) != _EXPECTED_KEYS:
            offenders.append(f"{item_id}: keys {sorted(item)} != {sorted(_EXPECTED_KEYS)}")
        category = _category(item, item_id, offenders)
        if category in counts:
            counts[category] += 1
        _required_str(item, "source_id", item_id, offenders)
        _question(item, item_id, offenders)
        _functions(item, item_id, offenders)
        _possible_answer(item, item_id, offenders)

    # Then the itemset is stable, unique, and balanced.
    assert len(items) == _EXPECTED_COUNT
    assert counts == _EXPECTED_COUNTS
    assert offenders == []


def test_v1_bfcl_items_are_prompt_buildable_and_self_score_correct() -> None:
    # Given all frozen BFCL rows.
    items = _load_jsonl(_ITEM_FILE)

    # When building prompts and scoring the deterministic expected call for each row.
    offenders: list[str] = []
    for item in items:
        item_id = str(item.get("id", "<missing-id>"))
        prompt = build_bfcl_prompt(item)
        if not prompt.strip():
            offenders.append(f"{item_id}: build_bfcl_prompt returned blank prompt")
        response = _expected_response(item)
        score = score_bfcl(item, response)
        if score["correct"] is not True:
            offenders.append(f"{item_id}: expected answer did not self-score correct; response={response}")

    # Then every frozen item is AST-scorable by the runtime scorer.
    assert offenders == []
    assert len(items) == _EXPECTED_COUNT


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{path.name}:{line_number} is not a JSON object")
            rows.append(parsed)
    return rows


def _item_id(row: Mapping[str, JsonValue], index: int, offenders: list[str]) -> str:
    expected = f"bfcl-{index:03d}"
    value = row.get("id")
    if not isinstance(value, str):
        offenders.append(f"row {index}: id must be a string")
        return f"row-{index}"
    if value != expected:
        offenders.append(f"{value}: expected id {expected}")
    return value


def _category(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> str:
    value = row.get("category")
    if not isinstance(value, str) or value not in _EXPECTED_COUNTS:
        offenders.append(f"{item_id}: category must be one of {sorted(_EXPECTED_COUNTS)}")
        return ""
    return value


def _required_str(row: Mapping[str, JsonValue], key: str, item_id: str, offenders: list[str]) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        offenders.append(f"{item_id}: {key} must be a non-empty string")
        return ""
    return value


def _question(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    value = row.get("question")
    if not isinstance(value, list) or not value:
        offenders.append(f"{item_id}: question must be a non-empty BFCL message list")


def _functions(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    value = row.get("function")
    if not isinstance(value, list) or not value:
        offenders.append(f"{item_id}: function must be a non-empty list")


def _possible_answer(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    value = row.get("possible_answer")
    if not isinstance(value, list) or not value:
        offenders.append(f"{item_id}: possible_answer must be a non-empty list")


def _expected_response(item: Mapping[str, JsonValue]) -> str:
    possible_answer = item["possible_answer"]
    if not isinstance(possible_answer, list):
        raise AssertionError(f"{item['id']}: possible_answer must be a list")
    required_by_function = _required_by_function(item)
    calls = [_call_text(call, required_by_function) for call in possible_answer if isinstance(call, dict)]
    return "[" + ", ".join(calls) + "]"


def _required_by_function(item: Mapping[str, JsonValue]) -> dict[str, set[str]]:
    functions = item["function"]
    if not isinstance(functions, list):
        return {}
    required: dict[str, set[str]] = {}
    for function in functions:
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        parameters = function.get("parameters")
        if not isinstance(name, str) or not isinstance(parameters, dict):
            continue
        required_params = parameters.get("required")
        if isinstance(required_params, list):
            required[name] = {param for param in required_params if isinstance(param, str)}
    return required


def _call_text(call: Mapping[str, JsonValue], required_by_function: Mapping[str, set[str]]) -> str:
    function_name, params = next(iter(call.items()))
    if not isinstance(params, dict):
        raise AssertionError(f"{function_name}: params must be an object")
    required = required_by_function.get(function_name, set())
    args = [
        f"{key}={_repr_value(values)}"
        for key, values in params.items()
        if isinstance(values, list) and (key in required or "" not in values)
    ]
    return f"{function_name}(" + ", ".join(args) + ")"


def _repr_value(values: list[JsonValue]) -> str:
    value = next(item for item in values if item != "")
    return repr(_materialize(value))


def _materialize(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_materialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _materialize_list(item) if isinstance(item, list) else _materialize(item) for key, item in value.items()}
    return value


def _materialize_list(values: list[JsonValue]) -> JsonValue:
    value = next(item for item in values if item != "")
    return _materialize(value)
