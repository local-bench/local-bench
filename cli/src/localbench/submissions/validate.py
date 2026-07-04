from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from localbench._suite import read_json_object
from localbench._types import JsonObject, JsonValue
from localbench.scoring.scorecard import scorecard_identity
from localbench.submissions.canon import canonical_json_hash, sha256_bytes
from localbench.submissions.contracts import (
    ITEM_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    SUBMISSION_FORMAT,
)
from localbench.suite_verify import suite_hash, verify_suite_dir


class SubmissionValidationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SuiteItem:
    bench: str
    item_id: str
    source: JsonObject
    baseline: float
    item_sha256: str


def validate_manifest_contract(manifest: JsonObject) -> JsonObject:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise SubmissionValidationError("manifest schema_version is not supported")
    payload = _object_or_error(manifest.get("payload"), "manifest payload")
    if payload.get("submission_format") != SUBMISSION_FORMAT:
        raise SubmissionValidationError("submission format is not supported")
    expected_payload_sha = canonical_json_hash(payload)
    if manifest.get("payload_sha256") != expected_payload_sha:
        raise SubmissionValidationError("manifest payload sha mismatch")
    return payload


def validate_item_contracts(items: list[JsonObject]) -> None:
    for item in items:
        if item.get("schema_version") != ITEM_SCHEMA_VERSION:
            raise SubmissionValidationError("item schema_version is not supported")
        _require_string(item, "bench")
        _require_string(item, "item_id")
        _require_string(item, "suite_item_sha256")
        _object_or_error(item.get("response"), "item response")


def validate_file_hashes(manifest: JsonObject, files: dict[str, bytes]) -> None:
    payload = _object_or_error(manifest.get("payload"), "manifest payload")
    signed_files = payload.get("files")
    if not isinstance(signed_files, list):
        raise SubmissionValidationError("manifest files must be a list")
    expected_paths: set[str] = set()
    for entry in signed_files:
        file_entry = _object_or_error(entry, "manifest file entry")
        path = _require_string(file_entry, "path")
        expected_paths.add(path)
        data = files.get(path)
        if data is None:
            raise SubmissionValidationError(f"signed file missing: {path}")
        if file_entry.get("sha256") != sha256_bytes(data) or file_entry.get("size") != len(data):
            raise SubmissionValidationError(f"file hash mismatch: {path}")
    unsigned = set(files) - {"manifest.json"} - expected_paths
    if unsigned:
        raise SubmissionValidationError(f"unsigned file in bundle: {sorted(unsigned)[0]}")


def validate_suite_and_scorecard(payload: JsonObject, suite_dir: Path) -> None:
    verify_suite_dir(suite_dir)
    submitted_suite = _object_or_error(payload.get("suite"), "payload suite")
    if submitted_suite.get("hash") != suite_hash(suite_dir):
        raise SubmissionValidationError("suite hash mismatch")
    submitted_scorecard = _object_or_error(payload.get("scorecard"), "payload scorecard")
    current = scorecard_identity(_optional_string(submitted_scorecard.get("reasoning_registry_entry_id")))
    if submitted_scorecard.get("id") != current.get("scorecard_id"):
        raise SubmissionValidationError("scorecard id mismatch")
    if submitted_scorecard.get("registry_digest") != current.get("registry_digest"):
        raise SubmissionValidationError("scorecard registry digest mismatch")


def suite_item_index(payload: JsonObject, suite_dir: Path) -> dict[tuple[str, str], SuiteItem]:
    submitted_suite = _object_or_error(payload.get("suite"), "payload suite")
    item_hashes = _object_or_error(submitted_suite.get("item_set_hashes"), "suite item_set_hashes")
    tier = _optional_string(submitted_suite.get("tier")) or "standard"
    suite = read_json_object(suite_dir / "suite.json")
    benches = _object_or_error(suite.get("benches"), "suite benches")
    index: dict[tuple[str, str], SuiteItem] = {}
    for bench_name, bench_value in benches.items():
        if not isinstance(bench_name, str) or not isinstance(bench_value, dict):
            continue
        itemset = _itemset_for_tier(bench_value, tier)
        file_name = _optional_string(itemset.get("file"))
        if file_name is None or file_name not in item_hashes:
            continue
        baseline = _number(bench_value.get("chance_correction_baseline"))
        for source in _read_jsonl(suite_dir / file_name):
            item_id = _item_id(source)
            index[(bench_name, item_id)] = SuiteItem(
                bench=bench_name,
                item_id=item_id,
                source=source,
                baseline=baseline,
                item_sha256=canonical_json_hash(source),
            )
    return index


def validate_items_match_suite(
    items: list[JsonObject],
    expected: dict[tuple[str, str], SuiteItem],
    dynamic_benches: frozenset[str] = frozenset(),
) -> None:
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (_require_string(item, "bench"), _require_string(item, "item_id"))
        if key in seen:
            raise SubmissionValidationError(f"duplicate item: {key[0]}/{key[1]}")
        seen.add(key)
        suite_item = expected.get(key)
        if suite_item is None:
            if key[0] in dynamic_benches:
                continue
            raise SubmissionValidationError(f"unknown item: {key[0]}/{key[1]}")
        if item.get("suite_item_sha256") != suite_item.item_sha256:
            raise SubmissionValidationError(f"suite item hash mismatch: {key[0]}/{key[1]}")
    missing = sorted(set(expected) - seen)
    if missing:
        bench, item_id = missing[0]
        raise SubmissionValidationError(f"missing item: {bench}/{item_id}")


def _itemset_for_tier(bench: JsonObject, tier: str) -> JsonObject:
    itemsets = _object_or_error(bench.get("itemsets"), "bench itemsets")
    itemset = itemsets.get(tier)
    return dict(itemset) if isinstance(itemset, dict) else {}


def _read_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _item_id(item: JsonObject) -> str:
    for key in ("id", "question_id", "key"):
        value = item.get(key)
        if isinstance(value, str | int):
            return str(value)
    return "unknown"


def _object_or_error(value: JsonValue | None, label: str) -> JsonObject:
    if isinstance(value, dict):
        return dict(value)
    raise SubmissionValidationError(f"{label} must be an object")


def _require_string(item: JsonObject, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise SubmissionValidationError(f"{key} must be a non-empty string")
    return value


def _optional_string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _number(value: JsonValue | None) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0
