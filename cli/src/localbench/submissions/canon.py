from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue

ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
ZIP_MODE: Final = 0o100644 << 16


def canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_hash(value: JsonValue) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def jsonl_bytes(records: Sequence[JsonObject]) -> bytes:
    return b"".join(canonical_json_bytes(record) + b"\n" for record in records)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json_file(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def deterministic_zip(path: Path, files: Mapping[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name in _zip_order(files):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = ZIP_MODE
            archive.writestr(info, files[name])


def _zip_order(files: Mapping[str, bytes]) -> tuple[str, ...]:
    preferred = ("manifest.json", "items.jsonl", "run.original.json", "environment.json")
    present = [name for name in preferred if name in files]
    extras = sorted(name for name in files if name not in preferred)
    return (*present, *extras)
