from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

FULL_EXEC_SUITE_RELEASE_ID: Final = "suite-v1-full-exec-6axis-v1"
FULL_EXEC_SUITE_MANIFEST_SHA256: Final = (
    "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468"
)
STATIC_EXEC_SUITE_RELEASE_ID: Final = "suite-v1-static-exec-5axis-v1"
STATIC_EXEC_SUITE_MANIFEST_SHA256: Final = (
    "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64"
)
ONE_SHOT_PLAN_SCHEMA_VERSION: Final = "localbench.one_shot_plan.v1"
IDENTITY_ENVELOPE_SCHEMA_VERSION: Final = "localbench.one_shot_identity.v1"
PUBLISHABILITY_PREFLIGHT_SCHEMA_VERSION: Final = "localbench.publishability_preflight.v1"
ONE_SHOT_LOCAL_PREVIEW_REASON: Final = (
    "one-shot is a local preview without ranked identity guarantees and cannot be submitted"
)

SourceKind = Literal["catalog", "raw_hf"]


@dataclass(frozen=True, slots=True)
class OneShotSuiteIdentity:
    release_id: str
    manifest_sha256: str


FULL_EXEC_SUITE_IDENTITY: Final = OneShotSuiteIdentity(
    release_id=FULL_EXEC_SUITE_RELEASE_ID,
    manifest_sha256=FULL_EXEC_SUITE_MANIFEST_SHA256,
)
STATIC_EXEC_SUITE_IDENTITY: Final = OneShotSuiteIdentity(
    release_id=STATIC_EXEC_SUITE_RELEASE_ID,
    manifest_sha256=STATIC_EXEC_SUITE_MANIFEST_SHA256,
)
ONE_SHOT_SUITE_MANIFESTS: Final = {
    FULL_EXEC_SUITE_RELEASE_ID: FULL_EXEC_SUITE_MANIFEST_SHA256,
    STATIC_EXEC_SUITE_RELEASE_ID: STATIC_EXEC_SUITE_MANIFEST_SHA256,
}


@dataclass(frozen=True, slots=True)
class OneShotArtifact:
    repo_id: str
    filename: str
    revision: str
    quant_label: str
    sha256: str | None
    size_bytes: int | None
    vram_required_gb_8k: float | None
    vram_required_gb_32k: float | None

    @property
    def model_ref(self) -> str | None:
        if not self.repo_id or not self.revision or not self.filename:
            return None
        return f"hf://{self.repo_id}@{self.revision}#{self.filename}"

    @property
    def vram_budget_gb(self) -> float | None:
        return self.vram_required_gb_32k or self.vram_required_gb_8k


@dataclass(frozen=True, slots=True)
class ResolvedOneShotModel:
    requested: str
    model_id: str
    display_name: str
    family: str | None
    source_kind: SourceKind
    catalog_model_id: str | None
    tokenizer_repo: str | None
    tokenizer_revision: str | None
    artifact: OneShotArtifact
    local_only: bool
    publishable: bool
    blocking_reasons: tuple[str, ...]
