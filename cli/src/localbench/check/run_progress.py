from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from localbench._types import JsonObject
from localbench.check.run_support import read_items
from localbench.check.types import CheckError
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import jsonl_bytes, write_json_file

_EXECUTION_PROGRESS_SCHEMA = "localbench-check-execution-progress-v1"


@dataclass(frozen=True, slots=True)
class ItemJournal:
    path: Path

    def append(self, row: JsonObject) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab", buffering=0) as stream:
            _ = stream.write(jsonl_bytes([row]))
            stream.flush()
            os.fsync(stream.fileno())

    def rows(self) -> list[JsonObject]:
        if not self.path.is_file():
            return []
        ordered_ids: list[str] = []
        latest: dict[str, JsonObject] = {}
        for row in read_items(self.path):
            item_id = row.get("item_id")
            if not isinstance(item_id, str) or not item_id:
                raise CheckError("partial item row has no item_id")
            if item_id not in latest:
                ordered_ids.append(item_id)
            latest[item_id] = row
        return [latest[item_id] for item_id in ordered_ids]

    def finalize(self, rows: list[JsonObject]) -> None:
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temporary.open("wb") as stream:
            _ = stream.write(jsonl_bytes(rows))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)


@dataclass(frozen=True, slots=True)
class FullExecutionProgress:
    reference: JsonObject | None
    candidate: JsonObject | None


def read_full_execution_progress(path: Path) -> FullExecutionProgress:
    if not path.is_file():
        return FullExecutionProgress(None, None)
    document = read_json(path)
    if document.get("schema_version") != _EXECUTION_PROGRESS_SCHEMA:
        raise CheckError("partial execution record schema is invalid")
    return FullExecutionProgress(
        _optional_object(document, "reference"),
        _optional_object(document, "candidate"),
    )


def write_full_execution_progress(
    path: Path,
    *,
    reference: JsonObject | None,
    candidate: JsonObject | None,
) -> None:
    write_json_file(
        path,
        {
            "candidate": candidate,
            "reference": reference,
            "schema_version": _EXECUTION_PROGRESS_SCHEMA,
        },
    )


def _optional_object(document: JsonObject, key: str) -> JsonObject | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CheckError(f"partial execution field {key!r} must be an object or null")
    return cast(JsonObject, value)
