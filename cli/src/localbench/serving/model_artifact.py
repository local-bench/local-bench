from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass, replace
from enum import IntEnum, unique
from pathlib import Path
from typing import BinaryIO, Final, assert_never

from localbench._types import JsonObject, JsonValue

_GGUF_MAGIC: Final = b"GGUF"
_QUANT_RE: Final = re.compile(r"((?:[IQF]\d|BF16|FP16|FP8|Q\d)(?:_[A-Z0-9]+)*)", re.IGNORECASE)


@unique
class GgufValueType(IntEnum):
    UINT8 = 0
    INT8 = 1
    UINT16 = 2
    INT16 = 3
    UINT32 = 4
    INT32 = 5
    FLOAT32 = 6
    BOOL = 7
    STRING = 8
    ARRAY = 9
    UINT64 = 10
    INT64 = 11
    FLOAT64 = 12


@dataclass(frozen=True, slots=True)
class ModelArtifactError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    model_file: Path
    file_sha256: str
    file_size_bytes: int
    gguf_metadata_sha256: str
    tokenizer_digest: str | None
    chat_template_digest: str | None
    gguf_metadata_path: Path
    model_family: str | None
    quant_label: str | None
    model_format: str = "GGUF"
    snapshot_merkle_sha256: str | None = None
    snapshot_files: tuple[JsonObject, ...] = ()
    requested_repo: str | None = None
    requested_revision: str | None = None
    mamba_ssm_dtype: str | None = None


@dataclass(frozen=True, slots=True)
class ModelReference:
    repo_id: str
    revision: str
    filename: str


@dataclass(frozen=True, slots=True)
class SnapshotReference:
    repo_id: str
    revision: str


def resolve_model_file_artifact(model_file: Path, *, run_dir: Path) -> ModelArtifact:
    resolved = model_file.resolve()
    if not resolved.exists():
        raise ModelArtifactError(f"model file does not exist: {resolved}")
    if resolved.suffix.lower() != ".gguf":
        raise ModelArtifactError(f"model file must be a GGUF: {resolved}")
    metadata = parse_gguf_metadata(resolved)
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = run_dir / "gguf_metadata.json"
    metadata_bytes = json.dumps(metadata, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
    metadata_path.write_bytes(metadata_bytes)
    return ModelArtifact(
        model_file=resolved,
        file_sha256=sha256_file(resolved),
        file_size_bytes=resolved.stat().st_size,
        gguf_metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
        tokenizer_digest=_metadata_subset_digest(metadata, "tokenizer."),
        chat_template_digest=_metadata_value_digest(metadata.get("tokenizer.chat_template")),
        gguf_metadata_path=metadata_path,
        model_family=_metadata_text(metadata.get("general.architecture")),
        quant_label=_quant_label(resolved.name, metadata),
    )


def resolve_model_reference(ref: str, *, cache_dir: Path, run_dir: Path) -> ModelArtifact:
    parsed = parse_model_reference(ref)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as error:
        raise ModelArtifactError(
            "install the cli hf extra to use --model-ref, or pass --model-file",
        ) from error
    downloaded = hf_hub_download(
        repo_id=parsed.repo_id,
        filename=parsed.filename,
        revision=parsed.revision,
        local_dir=cache_dir,
    )
    return resolve_model_file_artifact(Path(downloaded), run_dir=run_dir)


def parse_model_reference(ref: str) -> ModelReference:
    prefix = "hf://"
    if not ref.startswith(prefix):
        raise ModelArtifactError("--model-ref must start with hf://")
    body = ref.removeprefix(prefix)
    repo_and_revision, separator, filename = body.partition("#")
    if separator == "" or filename == "":
        raise ModelArtifactError("--model-ref must include #<exact-file.gguf>")
    repo_id, at, revision = repo_and_revision.partition("@")
    if at == "" or len(revision) != 40 or not all(char in "0123456789abcdefABCDEF" for char in revision):
        raise ModelArtifactError("--model-ref revision must be a full 40-character SHA")
    if repo_id == "":
        raise ModelArtifactError("--model-ref is missing the HF repo id")
    return ModelReference(repo_id=repo_id, revision=revision, filename=filename)


def resolve_snapshot_reference(ref: str, *, cache_dir: Path, run_dir: Path) -> ModelArtifact:
    parsed = parse_snapshot_reference(ref)
    # huggingface_hub reads this setting during import on some releases.  The maintainer
    # lane deliberately materializes a Windows-native snapshot, not a symlink farm whose
    # behavior depends on Developer Mode.
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise ModelArtifactError(
            "install the cli hf extra to use the vLLM --model-ref lane",
        ) from error
    snapshot_dir = cache_dir / parsed.repo_id.replace("/", "--") / parsed.revision
    snapshot = Path(
        snapshot_download(
            repo_id=parsed.repo_id,
            revision=parsed.revision,
            local_dir=snapshot_dir,
        ),
    ).resolve()
    artifact = snapshot_artifact(snapshot, run_dir=run_dir)
    return replace(
        artifact,
        requested_repo=parsed.repo_id,
        requested_revision=parsed.revision,
    )


def parse_snapshot_reference(ref: str) -> SnapshotReference:
    if not ref.startswith("hf://"):
        raise ModelArtifactError("--model-ref must start with hf://")
    body = ref.removeprefix("hf://")
    if "#" in body:
        raise ModelArtifactError("vLLM --model-ref names a snapshot, not a #file")
    repo_id, separator, revision = body.partition("@")
    if not separator or not repo_id:
        raise ModelArtifactError("--model-ref must be hf://<repo>@<full-40-character-sha>")
    if repo_id.count("/") != 1 or any(part == "" for part in repo_id.split("/")) or "@" in revision:
        raise ModelArtifactError("--model-ref must contain one Hugging Face namespace/repo id")
    if len(revision) != 40 or not all(char in "0123456789abcdefABCDEF" for char in revision):
        raise ModelArtifactError("--model-ref revision must be a full 40-character SHA")
    return SnapshotReference(repo_id=repo_id, revision=revision.lower())


def snapshot_artifact(snapshot: Path, *, run_dir: Path) -> ModelArtifact:
    resolved = snapshot.resolve()
    if not resolved.is_dir():
        raise ModelArtifactError(f"model snapshot does not exist: {resolved}")
    files: list[JsonObject] = []
    for path in sorted(
        item
        for item in resolved.rglob("*")
        if item.is_file() and ".cache" not in item.relative_to(resolved).parts
    ):
        relative = path.relative_to(resolved).as_posix()
        files.append(
            {"path": relative, "sha256": sha256_file(path), "size_bytes": path.stat().st_size},
        )
    if not files or not any(str(row["path"]).endswith(".safetensors") for row in files):
        raise ModelArtifactError("vLLM snapshot contains no safetensors files")
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    merkle = hashlib.sha256(canonical).hexdigest()
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = run_dir / "snapshot_metadata.json"
    metadata_path.write_bytes(
        json.dumps(
            {"snapshot_merkle_sha256": merkle, "files": files},
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    config = _read_optional_object(resolved / "config.json")
    text_config = config.get("text_config")
    if not isinstance(text_config, dict):
        text_config = {}
    quant = _read_optional_object(resolved / "quantization_config.json")
    if not quant and isinstance(config.get("quantization_config"), dict):
        quant = dict(config["quantization_config"])
    template = resolved / "chat_template.jinja"
    tokenizer_names = (
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "vocab.json",
        "merges.txt",
        "tokenizer.model",
    )
    tokenizer_files = [resolved / name for name in tokenizer_names if (resolved / name).is_file()]
    return ModelArtifact(
        model_file=resolved,
        file_sha256=merkle,
        file_size_bytes=sum(int(row["size_bytes"]) for row in files),
        gguf_metadata_sha256=merkle,
        tokenizer_digest=_files_digest(tokenizer_files),
        chat_template_digest=sha256_file(template) if template.is_file() else None,
        gguf_metadata_path=metadata_path,
        model_family=_metadata_text(config.get("model_type")),
        quant_label=_snapshot_quant_label(quant),
        model_format="safetensors",
        snapshot_merkle_sha256=merkle,
        snapshot_files=tuple(files),
        mamba_ssm_dtype=(
            _metadata_text(text_config.get("mamba_ssm_dtype"))
            or _metadata_text(config.get("mamba_ssm_dtype"))
        ),
    )


def _read_optional_object(path: Path) -> JsonObject:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelArtifactError(f"invalid snapshot metadata: {path.name}") from error
    return value if isinstance(value, dict) else {}


def _files_digest(paths: list[Path]) -> str | None:
    if not paths:
        return None
    rows = [{"name": path.name, "sha256": sha256_file(path)} for path in paths]
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()


def _snapshot_quant_label(config: JsonObject) -> str | None:
    rendered = json.dumps(config, sort_keys=True).lower()
    if "nvfp4" in rendered:
        return "NVFP4"
    method = config.get("quant_method")
    return method.upper() if isinstance(method, str) and method else None


def parse_gguf_metadata(path: Path) -> JsonObject:
    with path.open("rb") as stream:
        if stream.read(4) != _GGUF_MAGIC:
            raise ModelArtifactError(f"model file is not GGUF: {path}")
        version = _read_u32(stream)
        if version not in {2, 3}:
            raise ModelArtifactError(f"unsupported GGUF version {version}: {path}")
        _read_u64(stream)
        metadata_count = _read_u64(stream)
        metadata: JsonObject = {}
        for _ in range(metadata_count):
            key = _read_string(stream)
            value_type = _read_value_type(stream)
            metadata[key] = _read_value(stream, value_type)
        return metadata


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_value(stream: BinaryIO, value_type: GgufValueType) -> JsonValue:
    match value_type:
        case GgufValueType.UINT8:
            return _read_struct(stream, "<B")
        case GgufValueType.INT8:
            return _read_struct(stream, "<b")
        case GgufValueType.UINT16:
            return _read_struct(stream, "<H")
        case GgufValueType.INT16:
            return _read_struct(stream, "<h")
        case GgufValueType.UINT32:
            return _read_u32(stream)
        case GgufValueType.INT32:
            return _read_struct(stream, "<i")
        case GgufValueType.FLOAT32:
            return _read_struct(stream, "<f")
        case GgufValueType.BOOL:
            return bool(_read_struct(stream, "<?"))
        case GgufValueType.STRING:
            return _read_string(stream)
        case GgufValueType.ARRAY:
            item_type = _read_value_type(stream)
            return [_read_value(stream, item_type) for _ in range(_read_u64(stream))]
        case GgufValueType.UINT64:
            return _read_u64(stream)
        case GgufValueType.INT64:
            return _read_struct(stream, "<q")
        case GgufValueType.FLOAT64:
            return _read_struct(stream, "<d")
        case _ as unreachable:
            assert_never(unreachable)


def _read_value_type(stream: BinaryIO) -> GgufValueType:
    raw = _read_u32(stream)
    try:
        return GgufValueType(raw)
    except ValueError as error:
        raise ModelArtifactError(f"unknown GGUF metadata value type {raw}") from error


def _read_string(stream: BinaryIO) -> str:
    size = _read_u64(stream)
    data = stream.read(size)
    if len(data) != size:
        raise ModelArtifactError("truncated GGUF string")
    return data.decode("utf-8")


def _read_u32(stream: BinaryIO) -> int:
    return int(_read_struct(stream, "<I"))


def _read_u64(stream: BinaryIO) -> int:
    return int(_read_struct(stream, "<Q"))


def _read_struct(stream: BinaryIO, fmt: str) -> int | float | bool:
    size = struct.calcsize(fmt)
    data = stream.read(size)
    if len(data) != size:
        raise ModelArtifactError("truncated GGUF metadata")
    value = struct.unpack(fmt, data)[0]
    if isinstance(value, int | float | bool):
        return value
    raise ModelArtifactError("unsupported GGUF scalar")


def _metadata_subset_digest(metadata: JsonObject, prefix: str) -> str | None:
    subset = {
        key: value
        for key, value in metadata.items()
        if key.startswith(prefix) and key != "tokenizer.chat_template"
    }
    if not subset:
        return None
    return hashlib.sha256(
        json.dumps(subset, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
    ).hexdigest()


def _metadata_value_digest(value: JsonValue | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
    ).hexdigest()


def _metadata_text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _quant_label(file_name: str, metadata: JsonObject) -> str | None:
    direct = _metadata_text(metadata.get("general.file_type"))
    if direct is not None:
        return direct
    match = _QUANT_RE.search(file_name)
    return match.group(1).upper() if match is not None else None
