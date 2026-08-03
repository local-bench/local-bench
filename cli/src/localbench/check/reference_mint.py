from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject
from localbench.check.receipt import validate_run_dir
from localbench.check.reference import create_reference_bundle, store_reference_bundle
from localbench.check.types import CheckError, ReferenceEdition
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import sha256_file


@dataclass(frozen=True, slots=True)
class ReferenceMintRequest:
    edition_id: str
    family: str
    class_label: str
    created_utc: str
    artifact: Path
    execution_run: Path
    signing_key: Path
    store: Path


def mint_reference_from_execution(request: ReferenceMintRequest) -> Path:
    run_dir = request.execution_run.resolve()
    validate_run_dir(run_dir)
    record = read_json(run_dir / "check-record.json")
    lifecycle = _required_object(record, "lifecycle")
    if lifecycle.get("status") not in {"executed", "smoke-executed"}:
        raise CheckError("reference mint requires a completed live run or smoke record")
    artifact = _required_object(record, "artifact")
    record_sha256 = _required_digest(artifact, "sha256")
    if sha256_file(request.artifact.resolve()) != record_sha256:
        raise CheckError("reference artifact sha256 does not match the execution record")
    if _required_text(artifact, "model_family") != request.family:
        raise CheckError("reference family does not match the execution record")
    execution = _required_object(record, "execution")
    if execution.get("runner") != "llama-server-live":
        raise CheckError("reference mint requires a live llama-server execution identity")
    manifest = _required_object(record, "manifest")
    edition = ReferenceEdition(
        edition_id=request.edition_id,
        family=request.family,
        artifact_sha256=record_sha256,
        tokenizer_sha256=_required_digest(artifact, "tokenizer_sha256"),
        template_sha256=_required_digest(execution, "prompt_template_sha256"),
        class_label=request.class_label,
        created_utc=request.created_utc,
        checkset_edition=_required_text(manifest, "edition"),
        execution_edition=_required_text(execution, "edition"),
    )
    return store_reference_bundle(request.store, create_reference_bundle(edition, request.signing_key))


def _required_object(document: JsonObject, key: str) -> JsonObject:
    value = document.get(key)
    if not isinstance(value, dict):
        raise CheckError(f"reference mint field {key!r} must be an object")
    return value


def _required_text(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"reference mint field {key!r} must be a non-empty string")
    return value


def _required_digest(document: JsonObject, key: str) -> str:
    value = _required_text(document, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise CheckError(f"reference mint field {key!r} must be a lowercase sha256 digest")
    return value
