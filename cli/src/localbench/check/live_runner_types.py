from __future__ import annotations

from dataclasses import dataclass

from localbench._types import JsonObject


@dataclass(frozen=True, slots=True)
class LiveItem:
    item_id: str
    module: str
    source: JsonObject
