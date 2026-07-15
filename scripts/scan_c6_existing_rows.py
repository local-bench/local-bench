from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.submissions.canon import sha256_file, write_json_file

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_INDEX: Final = REPO_ROOT / "web/public/data/index.json"
DEFAULT_BOARD: Final = REPO_ROOT / "cli/runs/board/board_v2.json"
DEFAULT_OUTPUT: Final = REPO_ROOT / "scratchpad/c6-impact-scan-2026-07-15.json"
CLASSIFICATIONS: Final = (
    "AFFECTED",
    "UNAFFECTED-WITH-EVIDENCE",
    "INDETERMINATE-MISSING-EVIDENCE",
)
NON_MEASUREMENT_CLASSES: Final = frozenset(
    {"harness_error", "infra_sandbox", "infra_timeout"}
)
AGGREGATE_INFRA_FIELDS: Final = (
    "infra_timeout_rate",
    "infra_sandbox_rate",
    "harness_error_subclass_rate",
    "harness_error_rate",
)


def classify_published_rows(
    published_index: JsonObject,
    board: JsonObject,
) -> JsonObject:
    board_models = _object_list(board.get("models"), "board.models")
    board_by_slug = {
        _string(model.get("slug"), "board model slug"): (index, model)
        for index, model in enumerate(board_models)
    }
    rows: list[JsonValue] = []
    published_models = _object_list(
        published_index.get("models"), "published_index.models"
    )
    for published_index_value, model in enumerate(published_models):
        if not _is_published_row(model):
            continue
        slug = _string(model.get("slug"), "published model slug")
        board_entry = board_by_slug.get(slug)
        rows.append(
            _classify_row(model, slug, published_index_value, board_entry)
        )
    rows.sort(key=lambda row: _string(_object(row, "classified row").get("slug"), "slug"))
    counts: JsonObject = {
        classification: sum(
            1
            for row in rows
            if _object(row, "classified row").get("classification") == classification
        )
        for classification in CLASSIFICATIONS
    }
    return {"counts": counts, "rows": rows}


def build_impact_scan(index_path: Path, board_path: Path) -> JsonObject:
    published_index = _read_object(index_path)
    board = _read_object(board_path)
    classified = classify_published_rows(published_index, board)
    return {
        "schema_version": "localbench.c6-impact-scan.v1",
        "scan_date": "2026-07-15",
        "inputs": [
            {"path": _repo_path(index_path), "sha256": sha256_file(index_path)},
            {"path": _repo_path(board_path), "sha256": sha256_file(board_path)},
        ],
        "selection": "ranked rows plus measured community rows",
        **classified,
    }


def _classify_row(
    published: JsonObject,
    slug: str,
    published_index: int,
    board_entry: tuple[int, JsonObject] | None,
) -> JsonObject:
    base: JsonObject = {
        "row_id": _string(published.get("best_run_id"), "published best_run_id"),
        "slug": slug,
        "model_label": _string(published.get("model_label"), "model_label"),
    }
    if board_entry is None:
        return {
            **base,
            "classification": "INDETERMINATE-MISSING-EVIDENCE",
            "reason": "published row has no board-side attempt-level evidence",
            "evidence_pointer": f"/published_index/models/{published_index}",
        }
    board_index, board_model = board_entry
    pointer = f"/board/models/{board_index}/agentic_run"
    agentic = board_model.get("agentic_run")
    if not isinstance(agentic, dict):
        return {
            **base,
            "classification": "INDETERMINATE-MISSING-EVIDENCE",
            "reason": "published row has no board-side agentic evidence",
            "evidence_pointer": pointer,
        }
    affected = _aggregate_affected(agentic, pointer)
    if affected is not None:
        reason, evidence_pointer = affected
        return {
            **base,
            "classification": "AFFECTED",
            "reason": reason,
            "evidence_pointer": evidence_pointer,
        }
    if _complete_unaffected_evidence(agentic):
        return {
            **base,
            "classification": "UNAFFECTED-WITH-EVIDENCE",
            "reason": (
                "complete attempt-level evidence has exactly one accepted measurement per "
                "task and no non-measurement failures"
            ),
            "evidence_pointer": f"{pointer}/attempt_evidence",
        }
    return {
        **base,
        "classification": "INDETERMINATE-MISSING-EVIDENCE",
        "reason": (
            "attempt-level evidence is absent or incomplete; zero aggregate rates do not "
            "prove unaffected status"
        ),
        "evidence_pointer": pointer,
    }


def _aggregate_affected(
    agentic: JsonObject,
    pointer: str,
) -> tuple[str, str] | None:
    for run_index, run in enumerate(_object_list(agentic.get("runs"), "agentic runs")):
        for field in AGGREGATE_INFRA_FIELDS:
            value = run.get(field)
            if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
                return (
                    f"published agentic aggregate contains a nonzero {field}",
                    f"{pointer}/runs/{run_index}/{field}",
                )
    return None


def _complete_unaffected_evidence(agentic: JsonObject) -> bool:
    if agentic.get("attempt_evidence_complete") is not True:
        return False
    evidence = agentic.get("attempt_evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    for item in evidence:
        if not isinstance(item, dict) or item.get("accepted_measurement_count") != 1:
            return False
        failure_classes = item.get("failure_classes")
        if not isinstance(failure_classes, list) or not all(
            isinstance(value, str) for value in failure_classes
        ):
            return False
        if NON_MEASUREMENT_CLASSES.intersection(failure_classes):
            return False
    return True


def _is_published_row(model: JsonObject) -> bool:
    return model.get("ranked") is True or (
        model.get("kind") == "community" and model.get("score_status") == "measured"
    )


def _read_object(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, str(path))


def _object(value: JsonValue, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _object_list(value: JsonValue | None, field: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must be a list of objects")
    return value


def _string(value: JsonValue | None, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--published-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = build_impact_scan(args.published_index, args.board)
    write_json_file(args.output, output)
    print(f"wrote={args.output}")


if __name__ == "__main__":
    main()
