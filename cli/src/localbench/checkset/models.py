from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ChecksetBuildError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ChecksetTypeError(TypeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ItemRecord:
    item_id: str
    content_sha256: str

    def as_json(self) -> JsonObject:
        return {"content_sha256": self.content_sha256, "item_id": self.item_id}


@dataclass(frozen=True, slots=True)
class ModuleRecord:
    name: str
    scored: int
    items: tuple[ItemRecord, ...]
    status: str = "ready"
    source: JsonObject | None = None
    scorer: JsonObject | None = None
    selection: JsonObject | None = None

    def as_json(self) -> JsonObject:
        document: JsonObject = {
            "items": [item.as_json() for item in self.items],
            "name": self.name,
            "scored": self.scored,
            "status": self.status,
        }
        if self.source is not None:
            document["source"] = dict(self.source)
        if self.scorer is not None:
            document["scorer"] = dict(self.scorer)
        if self.selection is not None:
            document["selection"] = dict(self.selection)
        return document
