from __future__ import annotations

import hashlib
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from localbench.check.artifact import identify_artifact
from localbench.check.reference import (
    ReferenceEditionError,
    create_reference_bundle,
    load_reference_bundle,
    store_reference_bundle,
)
from localbench.check.types import ReferenceEdition
from localbench.submissions.keys import write_private_key


def _gguf(path: Path, metadata: dict[str, str]) -> Path:
    entries: list[bytes] = []
    for key, value in metadata.items():
        key_bytes = key.encode("utf-8")
        value_bytes = value.encode("utf-8")
        entries.append(
            struct.pack("<Q", len(key_bytes))
            + key_bytes
            + struct.pack("<I", 8)
            + struct.pack("<Q", len(value_bytes))
            + value_bytes
        )
    _ = path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, len(entries)) + b"".join(entries))
    return path


def test_artifact_identity_hashes_gguf_metadata_and_classifies_explicit_parent(tmp_path: Path) -> None:
    artifact_path = _gguf(
        tmp_path / "fixture-Q5_K_M.gguf",
        {"general.architecture": "qwen3", "general.name": "fixture", "general.file_type": "Q5_K_M"},
    )

    identity = identify_artifact(artifact_path, parent="qwen3-reference-v1")

    metadata = identity["gguf_metadata"]
    lineage = identity["lineage"]
    assert isinstance(metadata, dict) and isinstance(lineage, dict)
    assert identity["sha256"] == hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    assert metadata["general.architecture"] == "qwen3"
    assert lineage["parent"] == "qwen3-reference-v1"
    assert identity["artifact_class"] == "exact-quant"
    assert identity["record_type"] == "quant-comparison-v1"


def test_unverified_lineage_uses_discriminated_record_type(tmp_path: Path) -> None:
    artifact_path = _gguf(tmp_path / "unknown.gguf", {"general.architecture": "unknown"})

    identity = identify_artifact(artifact_path, parent=None)

    assert identity["artifact_class"] == "unverified-lineage"
    assert identity["record_type"] == "unverified-lineage-v1"


def test_reference_store_round_trips_signed_immutable_bundle(tmp_path: Path) -> None:
    key_path = tmp_path / "reference-key.pem"
    public_key = write_private_key(key_path, seed=b"r" * 32)
    edition = ReferenceEdition(
        edition_id="qwen3-reference-v1",
        family="qwen3",
        artifact_sha256="a" * 64,
        tokenizer_sha256="b" * 64,
        template_sha256="c" * 64,
        class_label="Q8 operational proxy",
        created_utc="2026-08-03T00:00:00Z",
        checkset_edition="check-set-v1",
        execution_edition="LCE-1",
    )
    bundle = create_reference_bundle(edition, key_path)

    path = store_reference_bundle(tmp_path / "store", bundle)
    loaded = load_reference_bundle(path, expected_public_key=public_key)

    assert loaded == edition
    assert store_reference_bundle(tmp_path / "store", bundle) == path
    changed = create_reference_bundle(replace(edition, artifact_sha256="d" * 64), key_path)
    with pytest.raises(ReferenceEditionError, match="immutable"):
        _ = store_reference_bundle(tmp_path / "store", changed)


def test_reference_accepts_q5km_operational_proxy_label(tmp_path: Path) -> None:
    key_path = tmp_path / "reference-key.pem"
    public_key = write_private_key(key_path, seed=b"r" * 32)
    edition = ReferenceEdition(
        edition_id="qwen36-27b-reference-v1",
        family="qwen3",
        artifact_sha256="a" * 64,
        tokenizer_sha256="b" * 64,
        template_sha256="c" * 64,
        class_label="Q5_K_M operational proxy",
        created_utc="2026-08-03T00:00:00Z",
        checkset_edition="check-set-v1",
        execution_edition="LCE-1",
    )

    path = store_reference_bundle(tmp_path / "store", create_reference_bundle(edition, key_path))
    loaded = load_reference_bundle(path, expected_public_key=public_key)

    assert loaded.class_label == "Q5_K_M operational proxy"


def test_reference_loader_rejects_wrong_signer(tmp_path: Path) -> None:
    key_path = tmp_path / "reference-key.pem"
    _ = write_private_key(key_path, seed=b"r" * 32)
    edition = ReferenceEdition(
        edition_id="edition-v1",
        family="qwen3",
        artifact_sha256="a" * 64,
        tokenizer_sha256="b" * 64,
        template_sha256="c" * 64,
        class_label="BF16 source",
        created_utc="2026-08-03T00:00:00Z",
        checkset_edition="check-set-v1",
        execution_edition="LCE-1",
    )
    path = store_reference_bundle(tmp_path / "store", create_reference_bundle(edition, key_path))

    with pytest.raises(ReferenceEditionError, match="signature"):
        _ = load_reference_bundle(path, expected_public_key="0" * 64)
