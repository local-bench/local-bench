from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from localbench._types import JsonObject, JsonValue
from localbench.check.artifact import identify_artifact
from localbench.check.analysis import analyze_run
from localbench.check.budget import generation_parameters
from localbench.check.execution import mock_lce_identity
from localbench.check.kld import unavailable_kld
from localbench.check.performance import mock_performance
from localbench.check.reference import load_reference_bundle
from localbench.check.regrade import write_grades
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


def run_check(request: CheckRequest) -> tuple[Path, JsonObject]:
    identity = identify_artifact(request.artifact, parent=request.parent)
    manifest = read_json(request.manifest)
    manifest_sha256 = sha256_file(request.manifest)
    reference = _reference_edition(request, identity=identity, manifest=manifest)
    plan = _plan(identity, manifest_sha256=manifest_sha256, reference=reference)
    run_dir, resumed = _prepare_run_dir(request, plan=plan, identity=identity)
    items_path = run_dir / "items.jsonl"
    if resumed:
        items = _read_items(items_path)
    else:
        if not request.dry_run:
            raise CheckError("non-dry execution requires an injected runner; no model is loaded by this stage")
        items = _mock_items(manifest)
        _ = items_path.write_bytes(jsonl_bytes(items))
        write_json_file(run_dir / "plan.lock.json", plan)
    manifest_edition = _required_str(manifest, "edition")
    pairing_status = (
        "paired"
        if reference.checkset_edition == manifest_edition and reference.execution_edition == "LCE-1"
        else "unpaired"
    )
    grading = write_grades(run_dir, items)
    artifact_class = _required_str(identity, "artifact_class")
    statistics, verdict = analyze_run(run_dir, manifest, artifact_class=artifact_class)
    kld = unavailable_kld("pinned reference weights are not local in dry-run mode")
    execution = mock_lce_identity()
    performance = mock_performance(items, execution)
    write_json_file(run_dir / "kld.json", kld)
    write_json_file(run_dir / "performance.json", performance)
    item_values: list[JsonValue] = [item for item in items]
    record: JsonObject = {
        "artifact": identity,
        "comparison": {
            "candidate_checkset_edition": manifest_edition,
            "candidate_execution_edition": "LCE-1",
            "pairing_status": pairing_status,
            "reference_edition": reference.as_dict(),
            "verdict": "pending-grading" if pairing_status == "paired" else "unpaired",
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
    return run_dir, record


def _reference_edition(request: CheckRequest, *, identity: JsonObject, manifest: JsonObject) -> ReferenceEdition:
    if request.reference_bundle is not None:
        if request.reference_public_key is None:
            raise CheckError("--reference-public-key is required with --reference-bundle")
        return load_reference_bundle(request.reference_bundle, expected_public_key=request.reference_public_key)
    if not request.dry_run:
        raise CheckError("a signed --reference-bundle is required outside --dry-run")
    family = identity.get("model_family")
    artifact_sha = identity.get("sha256")
    template_sha = identity.get("template_sha256")
    tokenizer_sha = identity.get("tokenizer_sha256")
    if not isinstance(artifact_sha, str):
        raise CheckError("candidate artifact hash is missing")
    return ReferenceEdition(
        edition_id=request.parent or "dry-run-reference-v1",
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


def _mock_items(manifest: JsonObject) -> list[JsonObject]:
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise CheckError("check-set manifest has no modules")
    results: list[JsonObject] = []
    for module in modules:
        if not isinstance(module, dict):
            raise CheckError("check-set manifest contains an invalid module")
        module_name = _required_str(module, "name")
        raw_items = module.get("items")
        if not isinstance(raw_items, list):
            raise CheckError(f"manifest module {module_name!r} has no items")
        params = generation_parameters(module_name)
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise CheckError(f"manifest module {module_name!r} has an invalid item")
            item_id = _required_str(raw_item, "item_id")
            digest = hashlib.sha256(f"{module_name}:{item_id}".encode()).digest()
            token_ids: list[JsonValue] = [value for value in digest[:4]]
            generation: JsonObject = {
                "finish_reason": "stop",
                "parsed_tool_calls": [],
                "protocol_flag": None,
                "text": f"mock:{item_id}",
                "token_ids": token_ids,
            }
            results.append(
                {
                    "candidate": {**generation, "mock_correct": digest[0] % 17 != 0},
                    "generation_parameters": params,
                    "item_id": item_id,
                    "module": module_name,
                    "reference": {**generation, "mock_correct": True},
                }
            )
    return results


def _read_items(path: Path) -> list[JsonObject]:
    records: list[JsonObject] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = read_json_line(line)
        records.append(value)
    return records


def read_json_line(line: str) -> JsonObject:
    import json

    parsed = cast(object, json.loads(line))
    if not isinstance(parsed, dict):
        raise CheckError("run item row must be a JSON object")
    return cast(JsonObject, parsed)


def _required_str(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"required check field {key!r} is missing")
    return value
