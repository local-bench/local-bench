from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, TypeAlias

from localbench.scorers.mcq import score_mcq_detailed

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_ITEM_FILE: Final = _REPO_ROOT / "suite" / "v1" / "supergpqa.jsonl"
_EXPECTED_COUNT: Final = 400
_SCHEMA_KEYS: Final = {"id", "question", "options", "answer"}
_LETTERS: Final = "ABCDEFGHIJ"


def test_v1_supergpqa_items_are_valid_mcq_rows_when_loaded() -> None:
    # Given the frozen suite-v1 SuperGPQA item file.
    # When loading each JSONL row.
    items = _load_jsonl(_ITEM_FILE)

    # Then every item has the exact localbench MCQ schema and can be scored by mcq.py.
    assert len(items) == _EXPECTED_COUNT
    offenders: list[str] = []
    ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        item_id = _item_id(item, index, offenders)
        _question(item, item_id, offenders)
        options = _options(item, item_id, offenders)
        answer = _answer(item, item_id, len(options), offenders)

        if item_id in ids:
            offenders.append(f"{item_id}: duplicate id")
        ids.add(item_id)
        if options and answer:
            scored = score_mcq_detailed(f"Final answer: {answer}", answer, len(options))
            if not scored["correct"]:
                offenders.append(f"{item_id}: mcq.py cannot self-score answer {answer!r}")

    assert offenders == []


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
    if set(row) != _SCHEMA_KEYS:
        offenders.append(f"row {index}: keys {sorted(row)} != {sorted(_SCHEMA_KEYS)}")
    value = row.get("id")
    expected = f"supergpqa-{index:03d}"
    if not isinstance(value, str):
        offenders.append(f"row {index}: id must be a string")
        return f"row-{index}"
    if value != expected:
        offenders.append(f"{value}: expected id {expected}")
    return value


def _question(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> None:
    value = row.get("question")
    if not isinstance(value, str) or not value.strip():
        offenders.append(f"{item_id}: question must be a non-empty string")


def _options(row: Mapping[str, JsonValue], item_id: str, offenders: list[str]) -> Sequence[str]:
    value = row.get("options")
    if not isinstance(value, list):
        offenders.append(f"{item_id}: options must be a list")
        return ()
    if len(value) < 2 or len(value) > 10:
        offenders.append(f"{item_id}: options count {len(value)} is outside 2..10")
    bad_options = [
        option_index
        for option_index, option in enumerate(value, start=1)
        if not isinstance(option, str) or not option.strip()
    ]
    if bad_options:
        offenders.append(f"{item_id}: blank/non-string options at positions {bad_options}")
    return [option for option in value if isinstance(option, str)]


def _answer(row: Mapping[str, JsonValue], item_id: str, n_options: int, offenders: list[str]) -> str:
    value = row.get("answer")
    if not isinstance(value, str):
        offenders.append(f"{item_id}: answer must be a string")
        return ""
    answer = value.strip().upper()
    if answer != value:
        offenders.append(f"{item_id}: answer must be uppercase without surrounding whitespace")
    if len(answer) != 1 or answer not in _LETTERS[:n_options]:
        offenders.append(f"{item_id}: answer {value!r} is not in range A..{_LETTERS[n_options - 1]}")
    return answer
