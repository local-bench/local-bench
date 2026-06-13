from __future__ import annotations

from typing import NoReturn, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class DataBuildError(ValueError):
    pass


def fail(message: str) -> NoReturn:
    raise DataBuildError(message)


def object_value(value: JsonValue | None, context: str) -> JsonObject:
    return value if isinstance(value, dict) else fail(f"{context} must be an object")


def object_or_empty(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def list_value(value: JsonValue | None, context: str) -> list[JsonValue]:
    return value if isinstance(value, list) else fail(f"{context} must be a list")


def string_value(value: JsonValue | None, context: str) -> str:
    return value if isinstance(value, str) and value else fail(f"{context} must be a non-empty string")


def nullable_text(value: JsonValue | None, index: int, key: str) -> str | None:
    return value if value is None or isinstance(value, str) else fail(f"data_sources[{index}].{key} must be a string or null")


def nullable_number(value: JsonValue | None, index: int, key: str) -> float | None:
    number = number_or_none(value)
    if value is None or number is not None:
        return number
    raise DataBuildError(f"data_sources[{index}].{key} must be a number or null")


def text_value(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


def number_value(value: JsonValue | None, context: str) -> float:
    number = number_or_none(value)
    return number if number is not None else fail(f"{context} must be a number")


def number_or_none(value: JsonValue | None) -> float | None:
    return None if isinstance(value, bool) else float(value) if isinstance(value, int | float) else None


def int_value(value: JsonValue | None, context: str) -> int:
    parsed = int_or_none(value)
    return parsed if parsed is not None else fail(f"{context} must be an integer")


def int_or_none(value: JsonValue | None) -> int | None:
    return None if isinstance(value, bool) else int(value) if isinstance(value, int) else None


def bool_value(value: JsonValue | None, context: str) -> bool:
    return value if isinstance(value, bool) else fail(f"{context} must be a bool")
