from __future__ import annotations

from pathlib import Path
from typing import Protocol

from localbench._types import JsonObject
from localbench.check.reference import load_reference_bundle
from localbench.check.types import CheckError, ReferenceEdition
from localbench.checkset.input_runs import read_json


class RunSetupRequest(Protocol):
    artifact: Path
    parent: str | None
    dry_run: bool
    out: Path | None
    resume: Path | None
    reference_bundle: Path | None
    reference_public_key: str | None
    reference_checkset_edition: str | None
    smoke: bool


def reference_edition(
    request: RunSetupRequest,
    *,
    identity: JsonObject,
    manifest: JsonObject,
) -> ReferenceEdition:
    if request.reference_bundle is not None:
        if request.reference_public_key is None:
            raise CheckError("--reference-public-key is required with --reference-bundle")
        return load_reference_bundle(
            request.reference_bundle,
            expected_public_key=request.reference_public_key,
        )
    if not request.dry_run and not request.smoke:
        raise CheckError("a signed --reference-bundle is required outside --dry-run")
    family = identity.get("model_family")
    artifact_sha = identity.get("sha256")
    template_sha = identity.get("template_sha256")
    tokenizer_sha = identity.get("tokenizer_sha256")
    if not isinstance(artifact_sha, str):
        raise CheckError("candidate artifact hash is missing")
    return ReferenceEdition(
        edition_id="smoke-non-scoring" if request.smoke else request.parent or "dry-run-reference-v1",
        family=family if isinstance(family, str) else "dry-run-family",
        artifact_sha256=artifact_sha,
        tokenizer_sha256=tokenizer_sha if isinstance(tokenizer_sha, str) else "0" * 64,
        template_sha256=template_sha if isinstance(template_sha, str) else "0" * 64,
        class_label="Q8 operational proxy",
        created_utc="2026-08-03T00:00:00Z",
        checkset_edition=request.reference_checkset_edition or required_str(manifest, "edition"),
        execution_edition="LCE-1",
    )


def build_plan(
    identity: JsonObject,
    *,
    manifest_sha256: str,
    reference: ReferenceEdition,
) -> JsonObject:
    lineage = identity.get("lineage")
    parent = lineage.get("parent") if isinstance(lineage, dict) else None
    return {
        "artifact_sha256": required_str(identity, "sha256"),
        "manifest_sha256": manifest_sha256,
        "parent": parent,
        "reference_edition_id": reference.edition_id,
        "schema_version": "localbench-check-plan-lock-v1",
    }


def prepare_run_dir(
    request: RunSetupRequest,
    *,
    plan: JsonObject,
    identity: JsonObject,
) -> tuple[Path, bool]:
    if request.resume is not None:
        run_dir = request.resume.resolve()
        if not run_dir.is_dir():
            raise CheckError(f"--resume directory does not exist: {run_dir}")
        if read_json(run_dir / "plan.lock.json") != plan:
            raise CheckError(
                "--resume plan lock does not match the requested artifact, manifest, parent, and edition"
            )
        return run_dir, True
    artifact_sha = required_str(identity, "sha256")
    run_dir = (request.out or Path("runs") / "check" / artifact_sha[:12]).resolve()
    if run_dir.exists():
        raise CheckError(f"run directory already exists; use --resume explicitly: {run_dir}")
    run_dir.mkdir(parents=True)
    return run_dir, False


def required_str(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"required check field {key!r} is missing")
    return value
