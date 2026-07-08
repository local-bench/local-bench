from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from localbench.one_shot.types import OneShotArtifact, ResolvedOneShotModel

_FULL_SHA_RE: Final = re.compile(r"^[0-9a-fA-F]{40}$")
_FULL_SHA256_RE: Final = re.compile(r"^[0-9a-fA-F]{64}$")
_QUANT_RANK: Final = {
    "IQ2_XS": 10,
    "Q2_K": 20,
    "Q3_K_M": 30,
    "Q4_K_M": 40,
    "Q5_K_M": 50,
    "Q6_K": 60,
    "Q8_0": 80,
    "F16": 100,
}


@dataclass(frozen=True, slots=True)
class CatalogResolutionError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class CatalogArtifactConflictError(CatalogResolutionError):
    pass


def resolve_one_shot_model(
    requested_model: str,
    catalog: dict[str, object],
    *,
    quant: str | None,
    vram_gb: float | None,
) -> ResolvedOneShotModel:
    entry = _find_catalog_entry(catalog, requested_model)
    if entry is None:
        if "/" not in requested_model:
            raise CatalogResolutionError(f"unknown localbench catalog model: {requested_model}")
        quant_label = quant or "auto"
        return ResolvedOneShotModel(
            requested=requested_model,
            model_id=requested_model.rsplit("/", maxsplit=1)[-1],
            display_name=requested_model,
            family=None,
            source_kind="raw_hf",
            catalog_model_id=None,
            tokenizer_repo=None,
            tokenizer_revision=None,
            artifact=OneShotArtifact(
                repo_id=requested_model,
                filename="",
                revision="",
                quant_label=quant_label,
                sha256=None,
                size_bytes=None,
                vram_required_gb_8k=None,
                vram_required_gb_32k=None,
            ),
            local_only=True,
            publishable=False,
            blocking_reasons=("raw HF repos are LOCAL-ONLY in localbench 0.3.0",),
        )
    artifacts = [_artifact_from(entry, item) for item in _object_list(entry.get("artifacts"))]
    if not artifacts:
        raise CatalogResolutionError(
            f"catalog model {requested_model!r} lacks immutable HF artifact pins; "
            "publishable one-shot runs require repo_id, filename, full revision, and sha256",
        )
    _assert_artifact_catalog_consistency(entry, artifacts)
    selected = _select_artifact(artifacts, quant=quant, vram_gb=vram_gb)
    return ResolvedOneShotModel(
        requested=requested_model,
        model_id=_text(entry, "model_id") or _text(entry, "slug") or requested_model,
        display_name=_text(entry, "display_name") or requested_model,
        family=_text(entry, "family"),
        source_kind="catalog",
        catalog_model_id=_text(entry, "catalog_id") or _text(entry, "catalog_model_id"),
        tokenizer_repo=_text(entry, "tokenizer_repo") or _text(entry, "hf_model_id"),
        tokenizer_revision=_text(entry, "tokenizer_revision") or selected.revision,
        artifact=selected,
        local_only=False,
        publishable=True,
        blocking_reasons=(),
    )


def _find_catalog_entry(catalog: dict[str, object], requested_model: str) -> dict[str, object] | None:
    candidates = _object_list(catalog.get("models"))
    if not candidates and isinstance(catalog.get("slug"), str):
        candidates = [catalog]
    for entry in candidates:
        keys = (
            _text(entry, "slug"),
            _text(entry, "id"),
            _text(entry, "model_id"),
            _text(entry, "catalog_id"),
            _text(entry, "catalog_model_id"),
        )
        if requested_model in keys:
            return entry
    return None


def _artifact_from(entry: dict[str, object], raw: dict[str, object]) -> OneShotArtifact:
    repo_id = _text(raw, "repo_id") or _text(raw, "gguf_repo") or _text(entry, "gguf_repo")
    filename = _text(raw, "filename") or _text(raw, "file")
    revision = _text(raw, "revision") or _text(raw, "hf_revision")
    quant_label = _text(raw, "quant_label") or _text(raw, "quant")
    sha256 = _text(raw, "sha256") or _text(raw, "file_sha256")
    if repo_id is None or filename is None or quant_label is None:
        raise CatalogResolutionError("immutable HF artifact entries require repo_id, filename, and quant_label")
    if revision is None or _FULL_SHA_RE.fullmatch(revision) is None:
        raise CatalogResolutionError("immutable HF artifact entries require a full 40-character revision")
    if sha256 is None or _FULL_SHA256_RE.fullmatch(sha256) is None:
        raise CatalogResolutionError("immutable HF artifact entries require a sha256 digest")
    return OneShotArtifact(
        repo_id=repo_id,
        filename=filename,
        revision=revision.lower(),
        quant_label=quant_label,
        sha256=sha256.lower(),
        size_bytes=_int(raw, "size_bytes") or _int(raw, "file_size_bytes"),
        vram_required_gb_8k=_float(raw, "vram_required_gb_8k"),
        vram_required_gb_32k=_float(raw, "vram_required_gb_32k"),
    )


def _assert_artifact_catalog_consistency(entry: dict[str, object], artifacts: list[OneShotArtifact]) -> None:
    artifact_by_quant = {artifact.quant_label: artifact for artifact in artifacts}
    for run in _object_list(entry.get("runs")):
        quant_label = _text(run, "quant_label") or _text(run, "quant")
        if quant_label is None or quant_label not in artifact_by_quant:
            continue
        artifact = artifact_by_quant[quant_label]
        _assert_same_int(run, "file_size_bytes", artifact.size_bytes)
        _assert_same_text(run, "filename", artifact.filename)
        _assert_same_text(run, "sha256", artifact.sha256)
        _assert_same_text(run, "hf_revision", artifact.revision)


def _assert_same_int(run: dict[str, object], field: str, artifact_value: int | None) -> None:
    value = _int(run, field)
    if value is not None and artifact_value is not None and value != artifact_value:
        raise CatalogArtifactConflictError(f"artifact facts conflict with catalog {field}")


def _assert_same_text(run: dict[str, object], field: str, artifact_value: str | None) -> None:
    value = _text(run, field)
    if value is not None and artifact_value is not None and value != artifact_value:
        raise CatalogArtifactConflictError(f"artifact facts conflict with catalog {field}")


def _select_artifact(
    artifacts: list[OneShotArtifact],
    *,
    quant: str | None,
    vram_gb: float | None,
) -> OneShotArtifact:
    if quant is not None:
        for artifact in artifacts:
            if artifact.quant_label == quant:
                return artifact
        raise CatalogResolutionError(f"catalog model does not have pinned quant {quant}")
    if vram_gb is None:
        raise CatalogResolutionError("auto quant selection requires --vram-gb when VRAM cannot be detected")
    fitting = [
        artifact
        for artifact in artifacts
        if artifact.vram_budget_gb is not None and artifact.vram_budget_gb <= vram_gb
    ]
    if not fitting:
        raise CatalogResolutionError("no pinned quant fits the requested VRAM budget")
    return max(fitting, key=lambda artifact: _QUANT_RANK.get(artifact.quant_label, 0))


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(record: dict[str, object], key: str) -> str | None:
    value = record.get(key)
    return value if isinstance(value, str) and value else None


def _int(record: dict[str, object], key: str) -> int | None:
    value = record.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(record: dict[str, object], key: str) -> float | None:
    value = record.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None
