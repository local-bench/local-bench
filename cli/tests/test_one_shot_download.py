from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.one_shot.download import (
    DownloadError,
    download_artifact_atomic,
    download_tokenizer_snapshot,
)
from one_shot_fixtures import REV_A, one_shot_artifact, sha256


def test_download_artifact_atomic_uses_partial_file_and_pinned_revision(tmp_path: Path) -> None:
    payload = b"GGUF fixture bytes"
    artifact = one_shot_artifact(size_bytes=len(payload), sha256=sha256(payload))
    hf = _FakeHfClient(artifact_bytes=payload)

    downloaded = download_artifact_atomic(artifact, tmp_path, hf_client=hf)

    assert downloaded.path == tmp_path / "model-q4.gguf"
    assert downloaded.path.read_bytes() == payload
    assert downloaded.sha256 == sha256(payload)
    assert downloaded.size_bytes == len(payload)
    assert not (tmp_path / "model-q4.gguf.partial").exists()
    assert hf.file_calls == [
        {
            "repo_id": "owner/model-gguf",
            "filename": "model-q4.gguf",
            "revision": REV_A,
            "destination": tmp_path / "model-q4.gguf.partial",
        },
    ]


def test_download_artifact_atomic_never_promotes_digest_mismatch(tmp_path: Path) -> None:
    artifact = one_shot_artifact(size_bytes=4, sha256="0" * 64)
    hf = _FakeHfClient(artifact_bytes=b"bad!")

    with pytest.raises(DownloadError, match="sha256 mismatch"):
        download_artifact_atomic(artifact, tmp_path, hf_client=hf)

    assert not (tmp_path / "model-q4.gguf").exists()
    assert not (tmp_path / "model-q4.gguf.partial").exists()


def test_download_tokenizer_snapshot_uses_artifact_revision_and_hashes_template(tmp_path: Path) -> None:
    hf = _FakeHfClient(
        tokenizer_files={
            "tokenizer.json": b'{"model":"fixture"}\n',
            "tokenizer_config.json": json.dumps({"chat_template": "{{ bos_token }}{{ messages }}"}).encode("utf-8"),
        },
    )

    snapshot = download_tokenizer_snapshot(
        repo_id="owner/base-model",
        revision=REV_A,
        destination_dir=tmp_path,
        hf_client=hf,
    )

    assert snapshot.path == tmp_path / "owner__base-model" / REV_A
    assert snapshot.revision == REV_A
    assert snapshot.tokenizer_digest == sha256(b'{"model":"fixture"}\n')
    assert snapshot.chat_template_digest == sha256(b"{{ bos_token }}{{ messages }}")
    assert snapshot.snapshot_sha256 is not None
    assert hf.snapshot_calls == [
        {
            "repo_id": "owner/base-model",
            "revision": REV_A,
            "destination": tmp_path / "owner__base-model" / REV_A,
        },
    ]


class _FakeHfClient:
    def __init__(
        self,
        *,
        artifact_bytes: bytes = b"",
        tokenizer_files: dict[str, bytes] | None = None,
    ) -> None:
        self._artifact_bytes = artifact_bytes
        self._tokenizer_files = tokenizer_files or {}
        self.file_calls: list[dict[str, object]] = []
        self.snapshot_calls: list[dict[str, object]] = []

    def download_file(self, *, repo_id: str, filename: str, revision: str, destination: Path) -> None:
        self.file_calls.append(
            {
                "repo_id": repo_id,
                "filename": filename,
                "revision": revision,
                "destination": destination,
            },
        )
        assert destination.name.endswith(".partial")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._artifact_bytes)

    def snapshot_download(self, *, repo_id: str, revision: str, destination: Path) -> Path:
        self.snapshot_calls.append({"repo_id": repo_id, "revision": revision, "destination": destination})
        destination.mkdir(parents=True, exist_ok=True)
        for name, data in self._tokenizer_files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return destination
