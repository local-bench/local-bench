from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from localbench._types import JsonObject, JsonValue
from localbench.check.receipt import validate_run_dir
from localbench.check.types import CheckError, ReferenceEdition, SignedEditionValidationError
from localbench.checkset.input_runs import read_json

_PAIR_IDENTITY_KEYS: Final = (
    "backend",
    "batch_size",
    "binaries",
    "build",
    "commit",
    "context_tokens",
    "cuda_version",
    "driver",
    "edition",
    "flags",
    "prompt_rendering",
    "reasoning_transport",
    "repo_defaults_disabled",
    "server_defaults_disabled",
)


@dataclass(frozen=True, slots=True)
class LiveReferenceRun:
    rows: list[JsonObject]
    execution: JsonObject


def load_live_reference_run(
    run_dir: Path,
    *,
    reference: ReferenceEdition,
    manifest_sha256: str,
) -> LiveReferenceRun:
    resolved = run_dir.resolve()
    validate_run_dir(resolved)
    record = read_json(resolved / "check-record.json")
    artifact = _required_object(record, "artifact")
    if artifact.get("sha256") != reference.artifact_sha256:
        raise CheckError("--reference-run artifact does not match the signed reference edition")
    manifest = _required_object(record, "manifest")
    if (
        manifest.get("edition") != reference.checkset_edition
        or manifest.get("sha256") != manifest_sha256
    ):
        raise CheckError("--reference-run manifest does not match the requested check-set edition")
    execution = _required_object(record, "execution")
    if execution.get("edition") != reference.execution_edition:
        raise CheckError("--reference-run execution edition does not match the signed reference edition")
    validate_reference_execution(execution, reference)
    raw_rows = record.get("items")
    if not isinstance(raw_rows, list) or len(raw_rows) != 594:
        raise CheckError("--reference-run must contain all 594 immutable item rows")
    rows = [cast(JsonObject, row) for row in raw_rows if isinstance(row, dict)]
    if len(rows) != 594:
        raise CheckError("--reference-run contains an invalid item row")
    return LiveReferenceRun(rows, execution)


def attach_reference_rows(
    candidate_rows: list[JsonObject],
    reference_rows: list[JsonObject],
) -> list[JsonObject]:
    if len(candidate_rows) != len(reference_rows):
        raise CheckError("candidate and reference live runs have different item counts")
    paired: list[JsonObject] = []
    for candidate, reference in zip(candidate_rows, reference_rows, strict=True):
        candidate_key = (_required_str(candidate, "module"), _required_str(candidate, "item_id"))
        reference_key = (_required_str(reference, "module"), _required_str(reference, "item_id"))
        if candidate_key != reference_key:
            raise CheckError(
                "candidate and reference live runs have different item order: "
                + f"{candidate_key[0]}/{candidate_key[1]} != {reference_key[0]}/{reference_key[1]}"
            )
        row = _clone_object(candidate)
        row["reference"] = _clone_object(_required_object(reference, "candidate"))
        repeated = reference.get("candidate_repeat")
        if isinstance(repeated, dict):
            row["reference_repeat"] = _clone_object(cast(JsonObject, repeated))
        paired.append(row)
    return paired


def validate_execution_pair(candidate: JsonObject, reference: JsonObject) -> None:
    for key in _PAIR_IDENTITY_KEYS:
        if candidate.get(key) != reference.get(key):
            raise CheckError(f"candidate/reference LCE-1 execution mismatch: {key}")
    candidate_props = _comparable_props(candidate.get("effective_server_config"))
    reference_props = _comparable_props(reference.get("effective_server_config"))
    if candidate_props != reference_props:
        raise CheckError("candidate/reference LCE-1 execution mismatch: effective_server_config")


def validate_reference_execution(execution: JsonObject, reference: ReferenceEdition) -> None:
    if execution.get("prompt_template_sha256") != reference.template_sha256:
        raise SignedEditionValidationError(
            "reference execution prompt template does not match the signed reference edition"
        )


def validate_signed_reference_execution(
    execution: JsonObject,
    reference: ReferenceEdition,
    *,
    artifact_sha256: str,
    checkset_edition: str,
) -> None:
    if artifact_sha256 != reference.artifact_sha256:
        raise SignedEditionValidationError("artifact does not match the signed reference edition")
    if checkset_edition != reference.checkset_edition:
        raise SignedEditionValidationError("check-set does not match the signed reference edition")
    if execution.get("edition") != reference.execution_edition:
        raise SignedEditionValidationError("execution does not match the signed reference edition")
    validate_reference_execution(execution, reference)


def _comparable_props(value: JsonValue | None) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    ignored = {"model", "model_alias", "model_id", "model_path"}
    return {
        key: item
        for key, item in value.items()
        if key not in ignored and not key.startswith("chat_template")
    }


def _clone_object(value: JsonObject) -> JsonObject:
    parsed = cast(object, json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True)))
    if not isinstance(parsed, dict):
        raise CheckError("live run row could not be cloned as JSON")
    return cast(JsonObject, parsed)


def _required_object(document: JsonObject, key: str) -> JsonObject:
    value = document.get(key)
    if not isinstance(value, dict):
        raise CheckError(f"live run field {key!r} must be an object")
    return cast(JsonObject, value)


def _required_str(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"live run field {key!r} must be a non-empty string")
    return value
