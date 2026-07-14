from __future__ import annotations

import json
from dataclasses import dataclass

from localbench._types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class StrictJsonError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


def strict_json_loads(source: bytes, label: str) -> JsonValue:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StrictJsonError(f"invalid UTF-8 in {label}") from error

    def unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
        result: JsonObject = {}
        for key, value in pairs:
            if key in result:
                raise StrictJsonError(f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise StrictJsonError(f"non-standard JSON number in {label}: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise StrictJsonError(f"invalid JSON in {label}") from error


def json_values_equal(left: JsonValue, right: JsonValue) -> bool:
    if type(left) is not type(right):
        return False
    match left:
        case dict():
            if not isinstance(right, dict) or left.keys() != right.keys():
                return False
            return all(json_values_equal(value, right[key]) for key, value in left.items())
        case list():
            if not isinstance(right, list) or len(left) != len(right):
                return False
            return all(
                json_values_equal(left_value, right_value)
                for left_value, right_value in zip(left, right, strict=True)
            )
        case _:
            return left == right
