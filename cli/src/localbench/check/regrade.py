from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from localbench._types import JsonObject
from localbench.check.grading import grade_mock_generation, grade_response
from localbench.check.types import CheckError
from localbench.submissions.canon import jsonl_bytes, write_json_file


def grade_item_rows(rows: list[JsonObject]) -> tuple[list[JsonObject], JsonObject]:
    grades: list[JsonObject] = []
    for row in rows:
        item_id = _required_str(row, "item_id")
        module = _required_str(row, "module")
        candidate = _required_object(row, "candidate")
        reference = _required_object(row, "reference")
        source = row.get("source_item")
        repeated = row.get("candidate_repeat")
        if isinstance(source, dict):
            candidate_grade = grade_response(
                module,
                source,
                candidate,
                repeated_generation=repeated if isinstance(repeated, dict) else None,
            )
            reference_grade = grade_response(module, source, reference)
        else:
            candidate_grade = grade_mock_generation(candidate)
            reference_grade = grade_mock_generation(reference)
        grades.append(
            {
                "candidate": candidate_grade,
                "item_id": item_id,
                "module": module,
                "paired": True,
                "reference": reference_grade,
            }
        )
    summary: JsonObject = {
        "candidate_correct": sum(_is_correct(grade, "candidate") for grade in grades),
        "n_items": len(grades),
        "reference_correct": sum(_is_correct(grade, "reference") for grade in grades),
        "schema_version": "localbench-check-grading-summary-v1",
        "status": "complete",
    }
    return grades, summary


def write_grades(run_dir: Path, rows: list[JsonObject]) -> JsonObject:
    grades, summary = grade_item_rows(rows)
    _ = (run_dir / "grades.jsonl").write_bytes(jsonl_bytes(grades))
    write_json_file(run_dir / "grading-summary.json", summary)
    return summary


def regrade_run(run_dir: Path) -> JsonObject:
    items_path = run_dir / "items.jsonl"
    if not items_path.is_file():
        raise CheckError(f"run directory has no immutable items.jsonl: {run_dir}")
    rows = [_parse_object(line) for line in items_path.read_text(encoding="utf-8").splitlines()]
    return write_grades(run_dir, rows)


def _parse_object(line: str) -> JsonObject:
    parsed = cast(object, json.loads(line))
    if not isinstance(parsed, dict):
        raise CheckError("run item row must be a JSON object")
    return cast(JsonObject, parsed)


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"run item field {key!r} must be a non-empty string")
    return value


def _required_object(row: JsonObject, key: str) -> JsonObject:
    value = row.get(key)
    if not isinstance(value, dict):
        raise CheckError(f"run item field {key!r} must be an object")
    return value


def _is_correct(grade: JsonObject, side: str) -> int:
    value = grade.get(side)
    return int(isinstance(value, dict) and value.get("correct") is True)
