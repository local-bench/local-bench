from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from localbench.one_shot.types import OneShotArtifact
from localbench.serving.model_artifact import sha256_file

_TOKENIZER_ALLOW_PATTERNS: Final = (
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "generation_config.json",
    "*.model",
    "vocab.*",
    "merges.txt",
)


class HfDownloadClient(Protocol):
    def download_file(self, *, repo_id: str, filename: str, revision: str, destination: Path) -> None: ...

    def resolve_model_revision(self, *, repo_id: str) -> str: ...

    def snapshot_download(self, *, repo_id: str, revision: str, destination: Path) -> Path: ...


@dataclass(frozen=True, slots=True)
class DownloadError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class TokenizerSnapshot:
    path: Path
    revision: str
    tokenizer_digest: str | None
    chat_template_digest: str | None
    snapshot_sha256: str | None


def download_artifact_atomic(
    artifact: OneShotArtifact,
    destination_dir: Path,
    *,
    hf_client: HfDownloadClient | None = None,
) -> DownloadedArtifact:
    if not artifact.filename:
        raise DownloadError("artifact filename is required before download")
    client = hf_client or HuggingFaceDownloadClient()
    destination_dir.mkdir(parents=True, exist_ok=True)
    final_path = destination_dir / artifact.filename
    partial_path = final_path.with_name(f"{final_path.name}.partial")
    if partial_path.exists():
        partial_path.unlink()
    try:
        client.download_file(
            repo_id=artifact.repo_id,
            filename=artifact.filename,
            revision=artifact.revision,
            destination=partial_path,
        )
        if not partial_path.exists():
            raise DownloadError("HF client did not create the .partial artifact")
        size_bytes = partial_path.stat().st_size
        if artifact.size_bytes is not None and size_bytes != artifact.size_bytes:
            raise DownloadError(
                f"artifact size mismatch: expected {artifact.size_bytes}, got {size_bytes}",
            )
        digest = sha256_file(partial_path)
        if artifact.sha256 is not None and digest != artifact.sha256:
            raise DownloadError(f"artifact sha256 mismatch: expected {artifact.sha256}, got {digest}")
        _fsync_file(partial_path)
        os.replace(partial_path, final_path)
    except Exception:
        if partial_path.exists():
            partial_path.unlink()
        raise
    return DownloadedArtifact(path=final_path, sha256=digest, size_bytes=size_bytes)


def download_tokenizer_snapshot(
    *,
    repo_id: str,
    revision: str,
    destination_dir: Path,
    hf_client: HfDownloadClient | None = None,
) -> TokenizerSnapshot:
    client = hf_client or HuggingFaceDownloadClient()
    snapshot_dir = destination_dir / repo_id.replace("/", "__") / revision
    snapshot_path = client.snapshot_download(repo_id=repo_id, revision=revision, destination=snapshot_dir)
    return TokenizerSnapshot(
        path=snapshot_path,
        revision=revision,
        tokenizer_digest=_optional_file_digest(snapshot_path / "tokenizer.json"),
        chat_template_digest=_chat_template_digest(snapshot_path / "tokenizer_config.json"),
        snapshot_sha256=_snapshot_digest(snapshot_path),
    )


class HuggingFaceDownloadClient:
    def download_file(self, *, repo_id: str, filename: str, revision: str, destination: Path) -> None:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as error:
            raise DownloadError("install localbench[hf] to download Hugging Face models") from error
        downloaded = Path(hf_hub_download(repo_id=repo_id, filename=filename, revision=revision))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(downloaded, destination)

    def resolve_model_revision(self, *, repo_id: str) -> str:
        try:
            from huggingface_hub import HfApi
            from huggingface_hub.errors import HfHubHTTPError, LocalEntryNotFoundError, OfflineModeIsEnabled
        except ImportError as error:
            raise DownloadError("install localbench[hf] to resolve Hugging Face tokenizer revisions") from error
        try:
            info = HfApi().model_info(repo_id)
        except (HfHubHTTPError, LocalEntryNotFoundError, OfflineModeIsEnabled, OSError) as error:
            raise DownloadError(_tokenizer_revision_resolution_error(repo_id)) from error
        revision = getattr(info, "sha", None)
        if not isinstance(revision, str) or not _full_sha(revision):
            raise DownloadError(
                f"could not resolve tokenizer repo {repo_id} to a full commit SHA; "
                "fix: connect to Hugging Face, log in for gated repos, or resume from a run "
                "whose plan.lock.json already records tokenizer_revision",
            )
        return revision.lower()

    def snapshot_download(self, *, repo_id: str, revision: str, destination: Path) -> Path:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as error:
            raise DownloadError("install localbench[hf] to download Hugging Face tokenizers") from error
        # No local_dir: the snapshot must land in the standard HF cache, because the bench
        # engine's offline (HF_HUB_OFFLINE=1) template introspection resolves the tokenizer
        # from that cache — a run-dir copy is invisible to it (rehearsal bug, 2026-07-09).
        # `destination` is part of the client seam used by fakes; the real client ignores it.
        return Path(
            snapshot_download(
                repo_id=repo_id,
                revision=revision,
                allow_patterns=list(_TOKENIZER_ALLOW_PATTERNS),
            ),
        )


def _tokenizer_revision_resolution_error(repo_id: str) -> str:
    return (
        f"could not resolve tokenizer repo {repo_id} to a pinned commit; "
        "fix: connect to Hugging Face, log in for gated repos, or resume from a run "
        "whose plan.lock.json already records tokenizer_revision"
    )


def _full_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdefABCDEF" for char in value)


def _optional_file_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256_file(path)


def _chat_template_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DownloadError(f"tokenizer_config.json is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        return None
    template = value.get("chat_template")
    if not isinstance(template, str):
        return None
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def _snapshot_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())
