from __future__ import annotations

from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.check.grading import grade_response
from localbench.check.kld import unavailable_kld
from localbench.check.performance import naturalistic_task_telemetry
from localbench.check.receipt import write_run_receipt
from localbench.submissions.canon import jsonl_bytes, write_json_file


def write_smoke_record(
    run_dir: Path,
    *,
    artifact: JsonObject,
    execution: JsonObject,
    items: list[JsonObject],
    manifest_edition: str,
    manifest_sha256: str,
    resumed: bool,
) -> JsonObject:
    grades = [_grade_item(item) for item in items]
    grading: JsonObject = {
        "n_items": len(items),
        "schema_version": "localbench-check-smoke-grading-v1",
        "status": "non-scoring",
    }
    statistics: JsonObject = {
        "label": "non-scoring",
        "schema_version": "localbench-check-statistics-v1",
        "status": "not-computed",
    }
    verdict: JsonObject = {
        "label": "non-scoring smoke validation",
        "verdict": "non-scoring",
    }
    kld = unavailable_kld("smoke mode never runs the KLD sub-pass")
    performance: JsonObject = {
        "controlled": {"reason": "smoke mode", "status": "not-run"},
        "schema_version": "localbench-check-performance-record-v1",
        "task_phase": naturalistic_task_telemetry(items),
    }
    _ = (run_dir / "items.jsonl").write_bytes(jsonl_bytes(items))
    _ = (run_dir / "grades.jsonl").write_bytes(jsonl_bytes(grades))
    write_json_file(run_dir / "grading-summary.json", grading)
    write_json_file(run_dir / "kld.json", kld)
    write_json_file(run_dir / "performance.json", performance)
    write_json_file(run_dir / "statistics.json", statistics)
    write_json_file(run_dir / "verdict.json", verdict)
    item_values: list[JsonValue] = [item for item in items]
    record: JsonObject = {
        "artifact": artifact,
        "comparison": {
            "candidate_checkset_edition": manifest_edition,
            "candidate_execution_edition": "LCE-1",
            "pairing_status": "non-scoring",
            "verdict": "non-scoring",
        },
        "execution": execution,
        "failure_policy": {
            "denominator_reduction": False,
            "infrastructure": "invalidate-or-explicit-resume-with-prior-records-immutable",
            "model_or_protocol": "score-wrong",
            "outcome_conditioned_reruns": False,
        },
        "grading": grading,
        "items": item_values,
        "kld": kld,
        "lifecycle": {"resume_explicit": resumed, "status": "smoke-executed"},
        "manifest": {"edition": manifest_edition, "sha256": manifest_sha256},
        "performance": performance,
        "schema_version": "localbench-check-run-v1",
        "scoring": {"label": "non-scoring", "reason": "pinned-smoke-validation"},
        "statistics": statistics,
        "verdict": verdict,
    }
    write_json_file(run_dir / "check-record.json", record)
    _ = write_run_receipt(run_dir)
    return record


def _grade_item(item: JsonObject) -> JsonObject:
    module = item.get("module")
    item_id = item.get("item_id")
    source = item.get("source_item")
    candidate = item.get("candidate")
    repeated = item.get("candidate_repeat")
    if not isinstance(module, str) or not isinstance(item_id, str):
        return {"item_id": item_id, "status": "invalid-smoke-row"}
    if not isinstance(source, dict) or not isinstance(candidate, dict):
        return {"item_id": item_id, "module": module, "status": "invalid-smoke-row"}
    grade = grade_response(
        module,
        source,
        candidate,
        repeated_generation=repeated if isinstance(repeated, dict) else None,
    )
    return {"candidate": grade, "item_id": item_id, "module": module, "status": "non-scoring"}
