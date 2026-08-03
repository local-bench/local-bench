from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject
from localbench.check.live_reference import (
    attach_reference_rows,
    load_live_reference_run,
    validate_execution_pair,
    validate_reference_execution,
)
from localbench.check.live_runner import LiveItem, LiveRunOptions, run_live_items
from localbench.check.run_progress import ItemJournal, write_full_execution_progress
from localbench.check.live_server import LiveRunnerConfig
from localbench.check.types import CheckError, ReferenceEdition


@dataclass(frozen=True, slots=True)
class FullLiveResult:
    items: list[JsonObject]
    execution: JsonObject


@dataclass(frozen=True, slots=True)
class FullLiveProgress:
    journal: ItemJournal
    rows: tuple[JsonObject, ...]
    execution_path: Path
    reference_execution: JsonObject | None
    candidate_execution: JsonObject | None


@dataclass(frozen=True, slots=True)
class FullLiveRequest:
    candidate_sha256: str
    reference: ReferenceEdition
    reference_run: Path | None
    manifest_sha256: str
    progress: FullLiveProgress


def run_full_live_check(
    config: LiveRunnerConfig,
    items: tuple[LiveItem, ...],
    request: FullLiveRequest,
) -> FullLiveResult:
    validate_full_live_inputs(
        candidate_sha256=request.candidate_sha256,
        reference=request.reference,
        reference_run=request.reference_run,
        allow_untrusted_code=config.allow_untrusted_code,
    )
    reference_execution = request.progress.reference_execution
    if request.candidate_sha256 == request.reference.artifact_sha256:
        if request.reference_run is not None:
            raise CheckError("--reference-run is not used when checking the reference artifact itself")
        reference_rows = _reference_runner_rows(request.progress.rows)
        if len(reference_rows) != len(items):
            reference_result = run_live_items(
                config,
                items,
                LiveRunOptions(
                    completed_rows=tuple(reference_rows),
                    previous_execution=reference_execution,
                    row_sink=lambda row: request.progress.journal.append(_stored_reference_row(row)),
                    execution_sink=lambda execution: write_full_execution_progress(
                        request.progress.execution_path,
                        reference=execution,
                        candidate=request.progress.candidate_execution,
                    ),
                ),
            )
            reference_rows = reference_result.items
            reference_execution = reference_result.execution
        if reference_execution is None:
            raise CheckError("reference execution identity is missing from partial run")
        validate_reference_execution(reference_execution, request.reference)
    else:
        if request.reference_run is None:
            message = (
                "--reference-run is required for a live candidate check; create it by running "
                + "the signed reference artifact through this command first"
            )
            raise CheckError(message)
        cached = load_live_reference_run(
            request.reference_run,
            reference=request.reference,
            manifest_sha256=request.manifest_sha256,
        )
        reference_rows = cached.rows
        reference_execution = cached.execution
    candidate_rows = _candidate_runner_rows(request.progress.rows)
    candidate_result = run_live_items(
        config,
        items,
        LiveRunOptions(
            completed_rows=tuple(candidate_rows),
            previous_execution=request.progress.candidate_execution,
            row_sink=lambda row: request.progress.journal.append(
                attach_reference_rows([row], [_reference_row(reference_rows, row)])[0]
            ),
            execution_sink=lambda execution: write_full_execution_progress(
                request.progress.execution_path,
                reference=reference_execution,
                candidate=execution,
            ),
        ),
    )
    validate_execution_pair(candidate_result.execution, reference_execution)
    paired_rows = attach_reference_rows(candidate_result.items, reference_rows)
    execution = dict(candidate_result.execution)
    execution["paired_reference_execution"] = {
        key: value for key, value in reference_execution.items() if key != "paired_reference_execution"
    }
    execution["reference_source"] = (
        "independent-live-rerun"
        if request.candidate_sha256 == request.reference.artifact_sha256
        else "validated-immutable-reference-run"
    )
    return FullLiveResult(paired_rows, execution)


def _stored_reference_row(row: JsonObject) -> JsonObject:
    stored = {
        key: value
        for key, value in row.items()
        if key not in {"candidate", "candidate_repeat", "reference", "reference_repeat"}
    }
    stored["reference"] = row["candidate"]
    repeated = row.get("candidate_repeat")
    if isinstance(repeated, dict):
        stored["reference_repeat"] = repeated
    return stored


def _reference_runner_rows(rows: tuple[JsonObject, ...]) -> list[JsonObject]:
    runner_rows: list[JsonObject] = []
    for row in rows:
        reference = row.get("reference")
        if not isinstance(reference, dict):
            continue
        runner = {
            key: value
            for key, value in row.items()
            if key not in {"candidate", "candidate_repeat", "reference", "reference_repeat"}
        }
        runner["candidate"] = reference
        repeated = row.get("reference_repeat")
        if isinstance(repeated, dict):
            runner["candidate_repeat"] = repeated
        runner_rows.append(runner)
    return runner_rows


def _candidate_runner_rows(rows: tuple[JsonObject, ...]) -> list[JsonObject]:
    return [row for row in rows if isinstance(row.get("candidate"), dict)]


def _reference_row(reference_rows: list[JsonObject], candidate: JsonObject) -> JsonObject:
    item_id = candidate.get("item_id")
    module = candidate.get("module")
    for row in reference_rows:
        if row.get("item_id") == item_id and row.get("module") == module:
            return row
    raise CheckError(f"reference row is missing for {module}/{item_id}")


def validate_full_live_inputs(
    *,
    candidate_sha256: str,
    reference: ReferenceEdition,
    reference_run: Path | None,
    allow_untrusted_code: bool,
) -> None:
    if candidate_sha256 == reference.artifact_sha256 and reference_run is not None:
        raise CheckError("--reference-run is not used when checking the reference artifact itself")
    if candidate_sha256 != reference.artifact_sha256 and reference_run is None:
        raise CheckError(
            "--reference-run is required for a live candidate check; first run the signed reference artifact"
        )
    if not allow_untrusted_code:
        raise CheckError("a full live check requires --allow-untrusted-code for the restricted coding sandbox")
