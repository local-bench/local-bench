from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

FULL_EXEC_SUITE_RELEASE_ID: Final = "suite-v1-full-exec-6axis-v1"
FULL_EXEC_SUITE_MANIFEST_SHA256: Final = (
    "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468"
)
ONE_SHOT_PLAN_SCHEMA_VERSION: Final = "localbench.one_shot_plan.v1"
IDENTITY_ENVELOPE_SCHEMA_VERSION: Final = "localbench.one_shot_identity.v1"
PUBLISHABILITY_PREFLIGHT_SCHEMA_VERSION: Final = "localbench.publishability_preflight.v1"

SourceKind = Literal["catalog", "raw_hf"]


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
