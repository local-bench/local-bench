"""Regression for the 2026-07-11 sha256_file MemoryError (18.3 GB GGUF, read_bytes)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from localbench.submissions import canon


def test_sha256_file_streams_multiple_chunks(tmp_path: Path, monkeypatch) -> None:
    # Shrink the chunk size so a small file exercises the multi-chunk loop the
    # 18 GB case relies on; the digest must equal a whole-buffer reference.
    monkeypatch.setattr(canon, "_SHA256_FILE_CHUNK", 1024)
    data = os.urandom(5 * 1024 + 37)  # deliberately not chunk-aligned
    target = tmp_path / "artifact.bin"
    target.write_bytes(data)

    assert canon.sha256_file(target) == hashlib.sha256(data).hexdigest()


def test_sha256_file_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.bin"
    target.write_bytes(b"")

    assert canon.sha256_file(target) == hashlib.sha256(b"").hexdigest()
