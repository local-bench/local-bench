from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.check.artifact import identify_artifact
from localbench.check.analysis import analyze_run
from localbench.check.execution import mock_lce_identity
from localbench.check.live_full import run_full_live_check, validate_full_live_inputs
from localbench.check.live_runner import run_live_items
from localbench.check.live_server import InfrastructureFailure, LiveRunnerConfig
from localbench.check.live_sources import load_live_items, load_smoke_items
from localbench.check.kld import unavailable_kld
from localbench.check.performance import live_task_performance, mock_performance
from localbench.check.reference import load_reference_bundle
from localbench.check.receipt import write_run_receipt
from localbench.check.regrade import write_grades
from localbench.check.run_support import live_repo_root, mock_items, read_items
from localbench.check.smoke import write_smoke_record
from localbench.check.types import CheckError, ReferenceEdition
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import (
    jsonl_bytes,
    sha256_file,
    write_json_file,
)


@dataclass(frozen=True, slots=True)
class CheckRequest:
    artifact: Path
    manifest: Path
    parent: str | None
    dry_run: bool
    out: Path | None
    resume: Path | None
    reference_bundle: Path | None = None
    reference_public_key: str | None = None
    reference_checkset_edition: str | None = None
    smoke: bool = False
    reference_run: Path | None = None
    allow_untrusted_code: bool = False


def run_check(request: CheckRequest) -> tuple[Path, JsonObject]:
    if request.dry_run and request.smoke:
        raise CheckError("--dry-run and --smoke are mutually exclusive")
    if request.smoke and request.reference_run is not None:
        raise CheckError("--reference-run is not used with --smoke")
    identity = identify_artifact(request.artifact, parent=request.parent)
    manifest = read_json(request.manifest)
    manifest_sha256 = sha256_file(request.manifest)
    reference = _reference_edition(request, identity=identity, manifest=manifest)
    if not request.dry_run and not request.smoke:
        validate_full_live_inputs(
            candidate_sha256=_required_str(identity, "sha256"),
            reference=reference,
            reference_run=request.reference_run,
            allow_untrusted_code=request.allow_untrusted_code,
        )
    plan = _plan(identity, manifest_sha256=manifest_sha256, reference=reference)
    run_dir, resumed = _prepare_run_dir(request, plan=plan, identity=identity)
    items_path = run_dir / "items.jsonl"
    if request.smoke:
        manifest_edition = _required_str(manifest, "edition")
        if resumed:
            items = read_items(items_path)
            execution = read_json(run_dir / "execution.json")
        else:
            write_json_file(run_dir / "plan.lock.json", plan)
            sources = load_smoke_items(live_repo_root(request.manifest), request.manifest)
            try:
                result = run_live_items(
                    LiveRunnerConfig(
                        model_file=request.artifact,
                        run_dir=run_dir,
                        allow_untrusted_code=request.allow_untrusted_code,
                    ),
                    sources,
                )
            except InfrastructureFailure as error:
                write_json_file(
                    run_dir / "infrastructure-failure.json",
                    {"failure_class": error.failure_class, "kind": error.kind, "message": error.detail},
                )
                raise
            items = result.items
            execution = result.execution
            write_json_file(run_dir / "execution.json", execution)
        record = write_smoke_record(
            run_dir,
            artifact=identity,
            execution=execution,
            items=items,
            manifest_edition=manifest_edition,
            manifest_sha256=manifest_sha256,
            resumed=resumed,
        )
        return run_dir, record
    if resumed:
        items = read_items(items_path)
        execution = mock_lce_identity() if request.dry_run else read_json(run_dir / "execution.json")
    else:
        write_json_file(run_dir / "plan.lock.json", plan)
        if request.dry_run:
            items = mock_items(manifest)
            execution = mock_lce_identity()
        else:
            sources = load_live_items(live_repo_root(request.manifest), request.manifest)
            try:
                result = run_full_live_check(
                    LiveRunnerConfig(
                        model_file=request.artifact,
                        run_dir=run_dir,
                        allow_untrusted_code=request.allow_untrusted_code,
                    ),
                    sources,
                    candidate_sha256=_required_str(identity, "sha256"),
                    reference=reference,
                    reference_run=request.reference_run,
                    manifest_sha256=manifest_sha256,
                )
            except InfrastructureFailure as error:
                write_json_file(
                    run_dir / "infrastructure-failure.json",
                    {"failure_class": error.failure_class, "kind": error.kind, "message": error.detail},
                )
                raise
            items = result.items
            execution = result.execution
            write_json_file(run_dir / "execution.json", execution)
        _ = items_path.write_bytes(jsonl_bytes(items))
    manifest_edition = _required_str(manifest, "edition")
    pairing_status = (
        "paired"
        if reference.checkset_edition == manifest_edition and reference.execution_edition == "LCE-1"
        else "unpaired"
    )
    grading = write_grades(run_dir, items)
    artifact_class = _required_str(identity, "artifact_class")
    statistics, verdict = analyze_run(run_dir, manifest, artifact_class=artifact_class)
    kld = unavailable_kld(
        "pinned reference weights are not local in dry-run mode"
        if request.dry_run
        else "the T-C live runner does not execute the optional KLD sub-pass"
    )
    performance = (
        mock_performance(items, execution)
        if request.dry_run
        else live_task_performance(items, execution)
    )
    write_json_file(run_dir / "kld.json", kld)
    write_json_file(run_dir / "performance.json", performance)
    item_values: list[JsonValue] = [item for item in items]
    published_verdict = verdict.get("verdict")
    record: JsonObject = {
        "artifact": identity,
        "comparison": {
            "candidate_checkset_edition": manifest_edition,
            "candidate_execution_edition": "LCE-1",
            "pairing_status": pairing_status,
            "reference_edition": reference.as_dict(),
            "verdict": published_verdict if pairing_status == "paired" and isinstance(published_verdict, str) else "unpaired",
        },
        "execution": execution,
        "failure_policy": {
            "denominator_reduction": False,
            "infrastructure": "invalidate-or-explicit-resume-with-prior-records-immutable",
            "model_or_protocol": "score-wrong",
            "outcome_conditioned_reruns": False,
        },
        "items": item_values,
        "grading": grading,
        "statistics": statistics,
        "verdict": verdict,
        "lifecycle": {
            "resume_explicit": request.resume is not None,
            "status": "dry-run-executed" if request.dry_run else "executed",
        },
        "kld": kld,
        "manifest": {"edition": manifest_edition, "sha256": manifest_sha256},
        "performance": performance,
        "schema_version": "localbench-check-run-v1",
    }
    write_json_file(run_dir / "check-record.json", record)
    _ = write_run_receipt(run_dir)
    return run_dir, record


def _reference_edition(request: CheckRequest, *, identity: JsonObject, manifest: JsonObject) -> ReferenceEdition:
    if request.reference_bundle is not None:
        if request.reference_public_key is None:
            raise CheckError("--reference-public-key is required with --reference-bundle")
        return load_reference_bundle(request.reference_bundle, expected_public_key=request.reference_public_key)
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
        checkset_edition=request.reference_checkset_edition or _required_str(manifest, "edition"),
        execution_edition="LCE-1",
    )


def _plan(identity: JsonObject, *, manifest_sha256: str, reference: ReferenceEdition) -> JsonObject:
    lineage = identity.get("lineage")
    parent = lineage.get("parent") if isinstance(lineage, dict) else None
    return {
        "artifact_sha256": _required_str(identity, "sha256"),
        "manifest_sha256": manifest_sha256,
        "parent": parent,
        "reference_edition_id": reference.edition_id,
        "schema_version": "localbench-check-plan-lock-v1",
    }


def _prepare_run_dir(request: CheckRequest, *, plan: JsonObject, identity: JsonObject) -> tuple[Path, bool]:
    if request.resume is not None:
        run_dir = request.resume.resolve()
        if not run_dir.is_dir():
            raise CheckError(f"--resume directory does not exist: {run_dir}")
        if read_json(run_dir / "plan.lock.json") != plan:
            raise CheckError("--resume plan lock does not match the requested artifact, manifest, parent, and edition")
        return run_dir, True
    artifact_sha = _required_str(identity, "sha256")
    run_dir = (request.out or Path("runs") / "check" / artifact_sha[:12]).resolve()
    if run_dir.exists():
        raise CheckError(f"run directory already exists; use --resume explicitly: {run_dir}")
    run_dir.mkdir(parents=True)
    return run_dir, False


def _required_str(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"required check field {key!r} is missing")
    return value
