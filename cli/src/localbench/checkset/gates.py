from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from localbench.checkset.input_runs import read_json
from localbench.checkset.models import (
    ChecksetBuildError,
    ItemRecord,
    JsonObject,
    JsonValue,
    ModuleRecord,
)
from localbench.checkset.select import SELECTION_SEED
from localbench.submissions.canon import canonical_json_bytes

GATE_COUNTS = {
    "stop-token": 3,
    "budget-control": 3,
    "template-canary": 3,
    "repetition": 3,
    "long-context-needle": 3,
    "determinism": 3,
}
DETERMINISM_FIELDS = ("token_ids", "finish_reason", "parsed_tool_calls", "scorer_result")


def build_sanity_gates(repo_root: Path) -> tuple[ModuleRecord, JsonObject]:
    source_path = repo_root / "checkset" / "sanity-gates.json"
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    document = read_json(source_path)
    if document.get("schema_version") != "localbench-sanity-gates-v1":
        raise ChecksetBuildError("Unsupported sanity-gate schema.")
    raw = document.get("gates")
    if not isinstance(raw, list) or not all(isinstance(record, dict) for record in raw):
        raise ChecksetBuildError("Sanity-gate source must contain object definitions.")
    definitions = [_with_digest(record) for record in raw if isinstance(record, dict)]
    definition_values: list[JsonValue] = [record for record in definitions]
    counts = Counter(record.get("category") for record in definitions)
    if counts != Counter(GATE_COUNTS):
        raise ChecksetBuildError("Sanity-gate source does not match the locked 18-item taxonomy.")
    module = ModuleRecord(
        name="sanity-gates",
        scored=18,
        items=tuple(ItemRecord(_required_str(record, "item_id"), _required_str(record, "content_sha256")) for record in definitions),
        source={"dataset": "checkset/sanity-gates.json", "revision": source_sha256, "split": "authored"},
        scorer={"name": "sanity-gates-exact", "version": "localbench-v1"},
        selection={"algorithm": "complete-authored-gate-set-v1", "inputs_sha256": source_sha256, "seed": SELECTION_SEED},
    )
    metadata: JsonObject = {
        "definitions": definition_values,
        "determinism_contract": {
            "comparison_fields": list(DETERMINISM_FIELDS),
            "independent_server_restarts": True,
            "tolerance": 0,
        },
        "source_sha256": source_sha256,
        "status": "ready",
    }
    return module, metadata


def determinism_canary_matches(first: JsonObject, second: JsonObject) -> bool:
    first_start = first.get("server_start_id")
    second_start = second.get("server_start_id")
    if not isinstance(first_start, str) or not first_start or not isinstance(second_start, str) or not second_start:
        return False
    if first_start == second_start:
        return False
    return all(first.get(field) == second.get(field) for field in DETERMINISM_FIELDS)


def _with_digest(source: JsonObject) -> JsonObject:
    record = dict(source)
    record["content_sha256"] = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return record


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ChecksetBuildError(f"Sanity-gate field {key!r} must be a non-empty string.")
    return value
