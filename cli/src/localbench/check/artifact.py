from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.check.types import CheckError
from localbench.serving.model_artifact import (
    ModelArtifactError,
    parse_gguf_metadata,
    sha256_file,
)
from localbench.submissions.canon import canonical_json_hash

ARTIFACT_CLASSES: Final = frozenset({"exact-quant", "fine-tune", "distill", "merge", "unverified-lineage"})
_QUANT_RE: Final = re.compile(r"(?:^|[-_.])((?:[IQF]\d|BF16|FP16|FP8|Q\d)(?:_[A-Z0-9]+)*)(?:[-_.]|$)", re.IGNORECASE)


def identify_artifact(path: Path, *, parent: str | None) -> JsonObject:
    resolved = path.resolve()
    if not resolved.is_file():
        raise CheckError(f"artifact does not exist: {resolved}")
    try:
        metadata = parse_gguf_metadata(resolved)
    except ModelArtifactError as error:
        raise CheckError(str(error)) from error
    artifact_class = _artifact_class(metadata, file_name=resolved.name, parent=parent)
    template = metadata.get("tokenizer.chat_template")
    tokenizer_metadata: JsonObject = {
        key: value for key, value in metadata.items() if key.startswith("tokenizer.") and key != "tokenizer.chat_template"
    }
    result: JsonObject = {
        "artifact_class": artifact_class,
        "file_name": resolved.name,
        "file_size_bytes": resolved.stat().st_size,
        "format": "GGUF",
        "gguf_metadata": metadata,
        "gguf_metadata_sha256": canonical_json_hash(metadata),
        "lineage": {
            "evidence": "explicit-parent" if parent else "gguf-metadata-only",
            "parent": parent,
        },
        "model_family": _text(metadata.get("general.architecture")),
        "record_type": _record_type(artifact_class),
        "sha256": sha256_file(resolved),
        "template_sha256": canonical_json_hash(template) if template is not None else None,
        "tokenizer_sha256": canonical_json_hash(tokenizer_metadata) if tokenizer_metadata else None,
    }
    return result


def _artifact_class(metadata: JsonObject, *, file_name: str, parent: str | None) -> str:
    declared = metadata.get("localbench.artifact_class")
    if isinstance(declared, str) and declared in ARTIFACT_CLASSES:
        return declared
    searchable = json.dumps(metadata, sort_keys=True).lower()
    if "distill" in searchable:
        return "distill"
    if "merge" in searchable or _positive_int(metadata.get("general.base_model.count")) > 1:
        return "merge"
    if "finetune" in searchable or "fine-tune" in searchable or "adapter" in searchable:
        return "fine-tune"
    quant = metadata.get("general.file_type")
    has_quant = isinstance(quant, str) and bool(quant) or _QUANT_RE.search(file_name) is not None
    if parent is not None and has_quant:
        return "exact-quant"
    return "unverified-lineage"


def _record_type(artifact_class: str) -> str:
    if artifact_class == "exact-quant":
        return "quant-comparison-v1"
    if artifact_class in {"fine-tune", "distill", "merge"}:
        return "tune-profile-v1"
    return "unverified-lineage-v1"


def _positive_int(value: JsonValue | None) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None
