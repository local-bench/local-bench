from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.check.artifact import identify_artifact
from localbench.check.analysis import analyze_run
from localbench.check.execution import mock_lce_identity
from localbench.check.live_full import (
    FullLiveProgress,
    FullLiveRequest,
    run_full_live_check,
)
from localbench.check.live_runner import LiveRunOptions, run_live_items
from localbench.check.live_server import InfrastructureFailure, LiveRunnerConfig
from localbench.check.live_sources import load_live_items, load_smoke_items
from localbench.check.kld import unavailable_kld
from localbench.check.performance import live_task_performance, mock_performance
from localbench.check.receipt import write_run_receipt
from localbench.check.regrade import write_grades
from localbench.check.run_support import live_repo_root, mock_items
from localbench.check.run_progress import (
    ItemJournal,
    read_full_execution_progress,
)
from localbench.check.run_setup import (
    build_plan,
    prepare_run_dir,
    reference_edition,
    required_str,
)
from localbench.check.smoke import write_smoke_record
from localbench.check.types import CheckError
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import (
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
    reference = reference_edition(request, identity=identity, manifest=manifest)
    plan = build_plan(identity, manifest_sha256=manifest_sha256, reference=reference)
    run_dir, resumed = prepare_run_dir(request, plan=plan, identity=identity)
    items_path = run_dir / "items.jsonl"
    journal = ItemJournal(items_path)
    if not resumed:
        write_json_file(run_dir / "plan.lock.json", plan)
    try:
        if request.smoke:
            manifest_edition = required_str(manifest, "edition")
            completed_record = run_dir / "check-record.json"
            if resumed and completed_record.is_file():
                record = read_json(completed_record)
                items = journal.rows()
                execution = _required_object(record, "execution")
            else:
                previous = read_json(run_dir / "execution.json") if (run_dir / "execution.json").is_file() else None
                sources = load_smoke_items(live_repo_root(request.manifest), request.manifest)
                result = run_live_items(
                    LiveRunnerConfig(
                        model_file=request.artifact,
                        run_dir=run_dir,
                        allow_untrusted_code=request.allow_untrusted_code,
                    ),
                    sources,
                    LiveRunOptions(
                        completed_rows=tuple(journal.rows()),
                        previous_execution=previous,
                        row_sink=journal.append,
                        execution_sink=lambda value: write_json_file(run_dir / "execution.json", value),
                    ),
                )
                items = result.items
                execution = result.execution
                journal.finalize(items)
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
        completed_record = run_dir / "check-record.json"
        if resumed and completed_record.is_file():
            items = journal.rows()
            execution = _required_object(read_json(completed_record), "execution")
        elif request.dry_run:
            items = mock_items(manifest)
            execution = mock_lce_identity()
            journal.finalize(items)
        else:
            sources = load_live_items(live_repo_root(request.manifest), request.manifest)
            progress = read_full_execution_progress(run_dir / "execution.json")
            result = run_full_live_check(
                LiveRunnerConfig(
                    model_file=request.artifact,
                    run_dir=run_dir,
                    allow_untrusted_code=request.allow_untrusted_code,
                ),
                sources,
                FullLiveRequest(
                    candidate_sha256=required_str(identity, "sha256"),
                    reference=reference,
                    reference_run=request.reference_run,
                    manifest_edition=required_str(manifest, "edition"),
                    manifest_sha256=manifest_sha256,
                    progress=FullLiveProgress(
                        journal=journal,
                        rows=tuple(journal.rows()),
                        execution_path=run_dir / "execution.json",
                        reference_execution=progress.reference,
                        candidate_execution=progress.candidate,
                    ),
                ),
            )
            items = result.items
            execution = result.execution
            journal.finalize(items)
            write_json_file(run_dir / "execution.json", execution)
    except InfrastructureFailure as error:
        _write_failure_record(
            run_dir,
            failure_class=error.failure_class,
            kind=error.kind,
            message=error.detail,
        )
        raise
    except CheckError as error:
        _write_failure_record(
            run_dir,
            failure_class="validation",
            kind="check-error",
            message=str(error),
        )
        raise
    except KeyboardInterrupt:
        _write_failure_record(
            run_dir,
            failure_class="interrupted",
            kind="keyboard-interrupt",
            message="check execution interrupted",
        )
        raise
    manifest_edition = required_str(manifest, "edition")
    pairing_status = (
        "paired"
        if reference.checkset_edition == manifest_edition and reference.execution_edition == "LCE-1"
        else "unpaired"
    )
    grading = write_grades(run_dir, items)
    artifact_class = required_str(identity, "artifact_class")
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


def _write_failure_record(
    run_dir: Path,
    *,
    failure_class: str,
    kind: str,
    message: str,
) -> None:
    write_json_file(
        run_dir / "infrastructure-failure.json",
        {"failure_class": failure_class, "kind": kind, "message": message},
    )


def _required_object(document: JsonObject, key: str) -> JsonObject:
    value = document.get(key)
    if not isinstance(value, dict):
        raise CheckError(f"required check field {key!r} is missing")
    return value
