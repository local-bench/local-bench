from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject
from localbench.one_shot.preflight import validate_resume_plan_lock, write_plan_lock
from localbench.one_shot.types import (
    FULL_EXEC_SUITE_MANIFEST_SHA256,
    FULL_EXEC_SUITE_RELEASE_ID,
    ONE_SHOT_PLAN_SCHEMA_VERSION,
    ResolvedOneShotModel,
)


@dataclass(frozen=True, slots=True)
class OneShotPlanLockContext:
    run_root: Path
    resolved: ResolvedOneShotModel
    cli_version: str


@dataclass(frozen=True, slots=True)
class OneShotDownloadLockFacts:
    artifact_path: Path
    artifact_sha256: str
    tokenizer_snapshot_sha256: str | None


def validate_or_write_plan_lock(context: OneShotPlanLockContext, *, resume: Path | None) -> None:
    plan = plan_lock_document(context)
    lock_path = context.run_root / "plan.lock.json"
    if resume is not None:
        validate_resume_plan_lock(lock_path, plan)
        return
    write_plan_lock(lock_path, plan)


def write_download_plan_lock(context: OneShotPlanLockContext, download: OneShotDownloadLockFacts) -> None:
    write_plan_lock(context.run_root / "plan.lock.json", plan_lock_document(context, download))


def plan_lock_document(
    context: OneShotPlanLockContext,
    download: OneShotDownloadLockFacts | None = None,
) -> JsonObject:
    plan: JsonObject = {
        "schema_version": ONE_SHOT_PLAN_SCHEMA_VERSION,
        "requested_model": context.resolved.requested,
        "quant_label": context.resolved.artifact.quant_label,
        "artifact_revision": context.resolved.artifact.revision,
        "artifact_filename": context.resolved.artifact.filename,
        "suite_release_id": FULL_EXEC_SUITE_RELEASE_ID,
        "suite_manifest_sha256": FULL_EXEC_SUITE_MANIFEST_SHA256,
        "cli_version": context.cli_version,
    }
    if download is not None:
        plan.update(
            {
                "artifact_path": str(download.artifact_path),
                "artifact_sha256": download.artifact_sha256,
                "tokenizer_snapshot_sha256": download.tokenizer_snapshot_sha256,
            },
        )
    return plan
