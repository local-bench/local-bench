from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from localbench.one_shot.catalog import CatalogResolutionError, resolve_one_shot_model
from localbench.one_shot.catalog_loader import HttpCatalogLoader
from localbench.one_shot.preflight import (
    JsonPostClient,
    build_publishability_preflight_payload,
    request_publishability_preflight,
)
from localbench.one_shot.raw_hf import HuggingFaceRawArtifactResolver
from localbench.one_shot.types import (
    OneShotArtifact,
    OneShotSuiteIdentity,
    ResolvedOneShotModel,
)


class CatalogLoader(Protocol):
    def load(self, *, requested_model: str, site: str) -> dict[str, object]: ...


class RawArtifactResolver(Protocol):
    def resolve_raw_artifact(
        self, *, repo_id: str, quant: str | None
    ) -> OneShotArtifact: ...


def resolve_one_shot(
    args: argparse.Namespace,
    vram_gb: float | None,
    catalog_loader: CatalogLoader | None,
    raw_artifact_resolver: RawArtifactResolver | None,
    site: str,
) -> ResolvedOneShotModel:
    requested_model = str(getattr(args, "one_shot_model"))
    catalog = (
        {"models": []}
        if "/" in requested_model
        else (catalog_loader or HttpCatalogLoader()).load(
            requested_model=requested_model,
            site=site,
        )
    )
    resolved = resolve_one_shot_model(
        requested_model,
        catalog,
        quant=getattr(args, "quant", None),
        vram_gb=vram_gb,
    )
    if resolved.local_only and resolved.artifact.filename == "":
        resolver = raw_artifact_resolver or HuggingFaceRawArtifactResolver()
        artifact = resolver.resolve_raw_artifact(
            repo_id=requested_model,
            quant=getattr(args, "quant", None),
        )
        resolved = replace(
            resolved,
            model_id=Path(artifact.filename).stem,
            tokenizer_repo=requested_model,
            tokenizer_revision=artifact.revision,
            artifact=artifact,
        )
    print(f"resolve   {resolved.display_name} {resolved.artifact.quant_label}")
    return resolved


def server_publishability_preflight(
    resolved: ResolvedOneShotModel,
    cli_version: str,
    site: str,
    http: JsonPostClient | None,
    suite_identity: OneShotSuiteIdentity,
) -> None:
    payload = build_publishability_preflight_payload(
        resolved,
        cli_version=cli_version,
        suite_identity=suite_identity,
    )
    response = request_publishability_preflight(site, payload, http=http)
    if response.get("publishable") is not True:
        reasons = response.get("reasons")
        detail = (
            ", ".join(str(item) for item in reasons)
            if isinstance(reasons, list)
            else "preflight rejected"
        )
        raise CatalogResolutionError(
            f"publishability preflight rejected one-shot run: {detail}"
        )
    print("preflight publishable")
