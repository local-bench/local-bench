from __future__ import annotations

import hashlib
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.task_journal_types import (
    JournalCorruptionError,
    JournalDurabilityError,
    SCHEMA_ID,
    SCHEMA_VERSION,
)
from localbench.scoring.agentic_exec.task_journal_lock import (
    JournalLock,
    fsync_directory,
    write_all,
)
from localbench.submissions.canon import canonical_json_bytes

_FILE_MAGIC: Final = b"LBATJ1\n"
_FRAME_MAGIC: Final = b"JREC"
_LENGTH: Final = struct.Struct(">Q")
_CHECKSUM_BYTES: Final = hashlib.sha256().digest_size
_MAX_PAYLOAD_BYTES: Final = 256 * 1024 * 1024
_ZERO_DIGEST: Final = "0" * 64

@dataclass(frozen=True, slots=True)
class RecoveredFrame:
    document: JsonObject
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class OpenJournal:
    handle: BinaryIO
    lock: JournalLock
    header: JsonObject
    frames: tuple[RecoveredFrame, ...]


def open_journal(path: Path, resume_identity: JsonObject) -> OpenJournal:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = JournalLock.acquire(path.with_suffix(path.suffix + ".lock"))
    try:
        if not path.exists():
            handle = path.open("w+b")
            header = {
                "schema": SCHEMA_ID,
                "version": SCHEMA_VERSION,
                "resume_identity": resume_identity,
            }
            write_all(handle, _FILE_MAGIC + encode_frame(header))
            _flush_and_sync(handle, path)
            return OpenJournal(handle=handle, lock=lock, header=header, frames=())
        handle = path.open("r+b")
        header, frames, truncate_at = recover(handle)
        if truncate_at is not None:
            handle.truncate(truncate_at)
            _flush_and_sync(handle, path)
        handle.seek(0, os.SEEK_END)
        return OpenJournal(handle=handle, lock=lock, header=header, frames=frames)
    except (OSError, JournalCorruptionError, JournalDurabilityError):
        lock.close()
        raise


def recover(handle: BinaryIO) -> tuple[JsonObject, tuple[RecoveredFrame, ...], int | None]:
    handle.seek(0)
    data = handle.read()
    if not data.startswith(_FILE_MAGIC):
        raise JournalCorruptionError("journal file magic is invalid")
    header_frame, offset, torn = _decode_frame(data, len(_FILE_MAGIC), allow_torn=False)
    if torn or header_frame is None:
        raise JournalCorruptionError("journal header is torn")
    header = header_frame.document
    if header.get("schema") != SCHEMA_ID or header.get("version") != SCHEMA_VERSION:
        raise JournalCorruptionError("journal schema/version header is invalid")

    frames: list[RecoveredFrame] = []
    previous = _ZERO_DIGEST
    truncate_at: int | None = None
    while offset < len(data):
        frame_start = offset
        frame, offset, torn = _decode_frame(data, offset, allow_torn=True)
        if torn:
            truncate_at = frame_start
            break
        if frame is None:
            raise JournalCorruptionError("journal frame decode returned no record")
        document = frame.document
        expected_sequence = len(frames) + 1
        if document.get("sequence") != expected_sequence:
            raise JournalCorruptionError(
                f"journal sequence chain is invalid at record {expected_sequence}"
            )
        if document.get("previous_sha256") != previous:
            raise JournalCorruptionError(
                f"journal checksum chain is invalid at record {expected_sequence}"
            )
        frames.append(frame)
        previous = frame.payload_sha256
    return header, tuple(frames), truncate_at


def append_frame(
    handle: BinaryIO,
    path: Path,
    document: JsonObject,
) -> RecoveredFrame:
    payload = canonical_json_bytes(document)
    frame = _FRAME_MAGIC + _LENGTH.pack(len(payload)) + payload + hashlib.sha256(payload).digest()
    handle.seek(0, os.SEEK_END)
    start = handle.tell()
    try:
        _write_append_bytes(handle, frame)
        _flush_and_sync(handle, path)
    except OSError as error:
        try:
            handle.truncate(start)
            handle.flush()
            os.fsync(handle.fileno())
        except OSError as rollback_error:
            raise JournalDurabilityError(
                f"journal append failed and rollback could not be made durable: {rollback_error}"
            ) from error
        raise JournalDurabilityError(f"journal append was not committed: {error}") from error
    return RecoveredFrame(
        document=document,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


def encode_frame(document: JsonObject) -> bytes:
    payload = canonical_json_bytes(document)
    return _FRAME_MAGIC + _LENGTH.pack(len(payload)) + payload + hashlib.sha256(payload).digest()


def _decode_frame(
    data: bytes,
    offset: int,
    *,
    allow_torn: bool,
) -> tuple[RecoveredFrame | None, int, bool]:
    frame_start = offset
    prefix_end = offset + len(_FRAME_MAGIC) + _LENGTH.size
    if prefix_end > len(data):
        if allow_torn and data[offset:].startswith(_FRAME_MAGIC[: len(data) - offset]):
            return None, frame_start, True
        raise JournalCorruptionError("unexpected bytes where journal frame prefix was required")
    if data[offset : offset + len(_FRAME_MAGIC)] != _FRAME_MAGIC:
        raise JournalCorruptionError("unexpected bytes where journal frame magic was required")
    offset += len(_FRAME_MAGIC)
    (payload_length,) = _LENGTH.unpack(data[offset : offset + _LENGTH.size])
    offset += _LENGTH.size
    if payload_length > _MAX_PAYLOAD_BYTES:
        if allow_torn and _FRAME_MAGIC not in data[offset:]:
            return None, frame_start, True
        raise JournalCorruptionError("non-final journal frame has a corrupt length")
    frame_end = offset + payload_length + _CHECKSUM_BYTES
    if frame_end > len(data):
        if allow_torn:
            return None, frame_start, True
        raise JournalCorruptionError("journal header frame is torn")
    payload = data[offset : offset + payload_length]
    checksum = data[offset + payload_length : frame_end]
    actual_checksum = hashlib.sha256(payload).digest()
    if checksum != actual_checksum:
        if allow_torn and frame_end == len(data):
            return None, frame_start, True
        raise JournalCorruptionError("checksum corruption in a non-final journal record")
    try:
        parsed = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise JournalCorruptionError(f"journal record JSON is invalid: {error}") from error
    if not isinstance(parsed, dict):
        raise JournalCorruptionError("journal frame payload is not an object")
    return (
        RecoveredFrame(document=parsed, payload_sha256=actual_checksum.hex()),
        frame_end,
        False,
    )


def _write_append_bytes(handle: BinaryIO, data: bytes) -> None:
    write_all(handle, data)


def _flush_and_sync(handle: BinaryIO, path: Path) -> None:
    handle.flush()
    os.fsync(handle.fileno())
    fsync_directory(path.parent)
