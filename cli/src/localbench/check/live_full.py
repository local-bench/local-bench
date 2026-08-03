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
from localbench.check.live_runner import LiveItem, run_live_items
from localbench.check.live_server import LiveRunnerConfig
from localbench.check.types import CheckError, ReferenceEdition


@dataclass(frozen=True, slots=True)
class FullLiveResult:
    items: list[JsonObject]
    execution: JsonObject


def run_full_live_check(
    config: LiveRunnerConfig,
    items: tuple[LiveItem, ...],
    *,
    candidate_sha256: str,
    reference: ReferenceEdition,
    reference_run: Path | None,
    manifest_sha256: str,
) -> FullLiveResult:
    validate_full_live_inputs(
        candidate_sha256=candidate_sha256,
        reference=reference,
        reference_run=reference_run,
        allow_untrusted_code=config.allow_untrusted_code,
    )
    if candidate_sha256 == reference.artifact_sha256:
        if reference_run is not None:
            raise CheckError("--reference-run is not used when checking the reference artifact itself")
        reference_result = run_live_items(config, items)
        reference_rows = reference_result.items
        reference_execution = reference_result.execution
        validate_reference_execution(reference_execution, reference)
    else:
        if reference_run is None:
            message = (
                "--reference-run is required for a live candidate check; create it by running "
                + "the signed reference artifact through this command first"
            )
            raise CheckError(message)
        cached = load_live_reference_run(
            reference_run,
            reference=reference,
            manifest_sha256=manifest_sha256,
        )
        reference_rows = cached.rows
        reference_execution = cached.execution
    candidate_result = run_live_items(config, items)
    validate_execution_pair(candidate_result.execution, reference_execution)
    paired_rows = attach_reference_rows(candidate_result.items, reference_rows)
    execution = dict(candidate_result.execution)
    execution["paired_reference_execution"] = {
        key: value for key, value in reference_execution.items() if key != "paired_reference_execution"
    }
    execution["reference_source"] = (
        "independent-live-rerun"
        if candidate_sha256 == reference.artifact_sha256
        else "validated-immutable-reference-run"
    )
    return FullLiveResult(paired_rows, execution)


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
