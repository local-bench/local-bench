from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Final

from localbench.scorers.toolhop._types import JsonValue

_NUMBER_RE: Final = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?|[-+]?\d+(?:\.\d+)?")


def answer_matches(*, expected: str, answer_type: str, output: JsonValue | None) -> bool:
    candidates = _candidate_strings(output)
    expected_text = expected.strip()
    if not expected_text:
        return False
    match answer_type:
        case "number":
            expected_number = _number(expected_text)
            return expected_number is not None and any(
                _number(candidate) == expected_number for candidate in candidates
            )
        case "letter" | "character":
            normalized = expected_text.casefold()
            return any(candidate.strip().casefold() == normalized for candidate in candidates)
        case "date" | "datetime":
            normalized = _normalize_text(expected_text)
            return any(normalized in _normalize_text(candidate) for candidate in candidates)
        case "string":
            normalized = _normalize_text(expected_text)
            return any(normalized in _normalize_text(candidate) for candidate in candidates)
        case _:
            normalized = _normalize_text(expected_text)
            return any(normalized in _normalize_text(candidate) for candidate in candidates)


def _candidate_strings(value: JsonValue | None) -> list[str]:
    if value is None:
        return [""]
    if isinstance(value, str):
        return [value]
    if isinstance(value, int | float | bool):
        return [str(value)]
    if isinstance(value, list):
        candidates = [json.dumps(value, ensure_ascii=False, sort_keys=True)]
        for item in value:
            candidates.extend(_candidate_strings(item))
        return candidates
    candidates = [json.dumps(value, ensure_ascii=False, sort_keys=True)]
    for item in value.values():
        candidates.extend(_candidate_strings(item))
    return candidates


def _number(value: str) -> Decimal | None:
    match = _NUMBER_RE.search(value.replace(",", ""))
    if match is None:
        return None
    try:
        return Decimal(match.group(0)).normalize()
    except InvalidOperation:
        return None


def _normalize_text(value: str) -> str:
    return " ".join(value.replace(",", "").strip().casefold().split())
