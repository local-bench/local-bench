from __future__ import annotations

from typing import TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
AstValue: TypeAlias = JsonScalar | list["AstValue"] | dict[str, "AstValue"] | tuple["AstValue", ...]
AstCall: TypeAlias = dict[str, dict[str, AstValue]]


class BFCLScore(TypedDict):
    correct: bool
    extracted: str | None


class CheckResult(TypedDict):
    valid: bool
    error: list[JsonValue]
    error_type: str
