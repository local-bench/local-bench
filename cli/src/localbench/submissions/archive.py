from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from localbench._types import JsonObject
from localbench.submissions.canon import sha256_bytes
from localbench.submissions.validate import SubmissionValidationError

ALLOWED_MEMBERS: Final = frozenset({"manifest.json", "items.jsonl", "run.original.json", "environment.json", "attestations.jsonl"})
MAX_MANIFEST_BYTES: Final = 262_144
MAX_MEMBER_BYTES: Final = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UnpackedBundle:
    manifest: JsonObject
    items: list[JsonObject]
    attestations: list[JsonObject]
    run_original: JsonObject | None
    files: dict[str, bytes]
    bundle_sha256: str


def unpack_bundle(path: Path) -> UnpackedBundle:
    bundle_bytes = path.read_bytes()
    members: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for info in archive.infolist():
                _check_member(info)
                if info.filename in members:
                    raise SubmissionValidationError(f"duplicate archive path: {info.filename}")
                data = archive.read(info)
                if len(data) > MAX_MEMBER_BYTES:
                    raise SubmissionValidationError(f"archive member too large: {info.filename}")
                members[info.filename] = data
    except zipfile.BadZipFile as error:
        raise SubmissionValidationError("invalid submission zip") from error
    manifest_bytes = members.get("manifest.json")
    if manifest_bytes is None:
        raise SubmissionValidationError("manifest.json missing from bundle")
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise SubmissionValidationError("manifest too large")
    item_bytes = members.get("items.jsonl", b"")
    return UnpackedBundle(
        manifest=json_object_from_bytes(manifest_bytes, "manifest.json"),
        items=_jsonl_objects(item_bytes, "items.jsonl"),
        attestations=_jsonl_objects(members.get("attestations.jsonl", b""), "attestations.jsonl"),
        run_original=optional_json_object(members.get("run.original.json"), "run.original.json"),
        files=members,
        bundle_sha256=sha256_bytes(bundle_bytes),
    )


def json_object_from_bytes(data: bytes, label: str) -> JsonObject:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise SubmissionValidationError(f"invalid JSON in {label}") from error
    if not isinstance(parsed, dict):
        raise SubmissionValidationError(f"{label} must be a JSON object")
    return parsed


def optional_json_object(data: bytes | None, label: str) -> JsonObject | None:
    return None if data is None else json_object_from_bytes(data, label)


def _check_member(info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    if path.is_absolute() or ".." in path.parts or info.filename not in ALLOWED_MEMBERS:
        raise SubmissionValidationError(f"unsafe archive path: {info.filename}")


def _jsonl_objects(data: bytes, label: str) -> list[JsonObject]:
    records: list[JsonObject] = []
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise SubmissionValidationError(f"{label} rows must be JSON objects")
        records.append(parsed)
    return records
