from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Final

from localbench._types import JsonValue

_DEFAULT_REPLACE_ATTEMPTS: Final = 5
_DEFAULT_RETRY_DELAY_SECONDS: Final = 0.05


def atomic_write_json(
    obj: JsonValue,
    path: str | Path,
    *,
    retry_attempts: int = _DEFAULT_REPLACE_ATTEMPTS,
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> None:
    data = json.dumps(obj, indent=2) + "\n"
    atomic_write_bytes(
        data.encode("utf-8"),
        path,
        retry_attempts=retry_attempts,
        retry_delay_seconds=retry_delay_seconds,
    )


def atomic_write_bytes(
    data: bytes,
    path: str | Path,
    *,
    retry_attempts: int = _DEFAULT_REPLACE_ATTEMPTS,
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.parent / f".{output_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with tmp_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(
            tmp_path,
            output_path,
            retry_attempts=retry_attempts,
            retry_delay_seconds=retry_delay_seconds,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _replace_with_retry(
    source: Path,
    target: Path,
    *,
    retry_attempts: int,
    retry_delay_seconds: float,
) -> None:
    attempts = max(1, retry_attempts)
    for attempt in range(1, attempts + 1):
        try:
            os.replace(source, target)
            return
        except (PermissionError, OSError):
            if attempt == attempts:
                raise
            time.sleep(max(0.0, retry_delay_seconds))
