from __future__ import annotations

from pathlib import Path

from localbench._types import JsonObject
from localbench.check.types import CheckError
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import sha256_file, write_json_file

_RECEIPT_ARTIFACTS = (
    "check-record.json",
    "grades.jsonl",
    "grading-summary.json",
    "items.jsonl",
    "kld.json",
    "performance.json",
    "plan.lock.json",
    "statistics.json",
    "verdict.json",
)


def write_run_receipt(run_dir: Path) -> JsonObject:
    artifact_hashes: JsonObject = {}
    for name in _RECEIPT_ARTIFACTS:
        path = run_dir / name
        if not path.is_file():
            raise CheckError(f"cannot issue receipt; run artifact is missing: {name}")
        artifact_hashes[name] = sha256_file(path)
    record = read_json(run_dir / "check-record.json")
    manifest = record.get("manifest")
    receipt: JsonObject = {
        "artifacts": artifact_hashes,
        "issued_utc": "2026-08-03T00:00:00Z",
        "manifest": manifest if isinstance(manifest, dict) else {},
        "receipt_kind": "deterministic-dry-run" if _is_dry_run(record) else "execution",
        "schema_version": "localbench-check-receipt-v1",
    }
    write_json_file(run_dir / "receipt.json", receipt)
    return receipt


def validate_run_dir(run_dir: Path) -> None:
    receipt_path = run_dir / "receipt.json"
    if not receipt_path.is_file():
        raise CheckError("check run has no receipt.json")
    receipt = read_json(receipt_path)
    if receipt.get("schema_version") != "localbench-check-receipt-v1":
        raise CheckError("check receipt schema is invalid")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(_RECEIPT_ARTIFACTS):
        raise CheckError("check receipt artifact set is incomplete")
    for name in _RECEIPT_ARTIFACTS:
        expected = artifacts.get(name)
        if not isinstance(expected, str) or sha256_file(run_dir / name) != expected:
            raise CheckError(f"check receipt digest mismatch: {name}")
    record = read_json(run_dir / "check-record.json")
    _validate_record(record)


def _validate_record(record: JsonObject) -> None:
    if record.get("schema_version") != "localbench-check-run-v1":
        raise CheckError("check record schema is invalid")
    required_objects = (
        "artifact",
        "comparison",
        "execution",
        "grading",
        "kld",
        "lifecycle",
        "manifest",
        "performance",
        "statistics",
        "verdict",
    )
    for key in required_objects:
        if not isinstance(record.get(key), dict):
            raise CheckError(f"check record field {key!r} must be an object")
    items = record.get("items")
    grading = record["grading"]
    lifecycle = record["lifecycle"]
    if not isinstance(items, list) or not isinstance(grading, dict) or not isinstance(lifecycle, dict):
        raise CheckError("check record completion fields are invalid")
    if lifecycle.get("status") == "smoke-executed":
        if not items or grading.get("status") != "non-scoring" or grading.get("n_items") != len(items):
            raise CheckError("complete smoke record must contain non-scoring executed items")
        return
    if len(items) != 594:
        raise CheckError("complete check record must contain all 594 executed items")
    if grading.get("status") != "complete" or grading.get("n_items") != 594:
        raise CheckError("complete check record must contain complete 594-item grading")


def _is_dry_run(record: JsonObject) -> bool:
    lifecycle = record.get("lifecycle")
    return isinstance(lifecycle, dict) and lifecycle.get("status") == "dry-run-executed"
