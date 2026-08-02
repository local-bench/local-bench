from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from localbench.checkset.models import ChecksetBuildError, ChecksetTypeError, JsonObject

RUN_NAMES: Final = ("base_q5km", "q6k", "udq2", "fusion")
BENCHES: Final = ("bigcodebench_hard", "ifbench", "olymmath_hard", "amo", "tc_json_v1")


def load_verified_runs(
    manifest: JsonObject,
    *,
    suite_root: Path,
) -> tuple[dict[str, dict[str, dict[str, bool]]], dict[str, dict[str, float | None]]]:
    correctness: dict[str, dict[str, dict[str, bool]]] = {}
    base_latency: dict[str, dict[str, float | None]] = {}
    for run_name in RUN_NAMES:
        entry = manifest[run_name]
        if not isinstance(entry, dict):
            raise ChecksetTypeError(f"Invalid input manifest entry {run_name!r}.")
        root = Path(required_str(entry, "source_path"))
        _verify_run_files(root, entry)
        run = read_json(root / "localbench-run.json")
        verify_suite_itemset_hashes(suite_root, run_name, run)
        items = run.get("items")
        if not isinstance(items, list):
            raise ChecksetTypeError(f"Run {run_name!r} has no item list.")
        per_bench: dict[str, dict[str, bool]] = {bench: {} for bench in BENCHES}
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            bench = raw_item.get("bench")
            item_id = raw_item.get("id")
            if isinstance(bench, str) and bench in per_bench and isinstance(item_id, str):
                per_bench[bench][item_id] = bool(raw_item.get("correct"))
        correctness[run_name] = per_bench
        if run_name == "base_q5km":
            for bench in BENCHES:
                base_latency[bench] = _read_latencies(root / "benchmarks" / f"{bench}.scored_items.jsonl")
    return correctness, base_latency


def verify_suite_itemset_hashes(suite_root: Path, run_name: str, run: JsonObject) -> None:
    manifest = run.get("manifest")
    suite = manifest.get("suite") if isinstance(manifest, dict) else None
    item_set_hashes = suite.get("item_set_hashes") if isinstance(suite, dict) else None
    if not isinstance(item_set_hashes, dict):
        raise ChecksetTypeError(f"Run {run_name!r} has no suite item-set hashes.")
    for bench in BENCHES:
        expected = item_set_hashes.get(f"{bench}.jsonl")
        if not isinstance(expected, str):
            raise ChecksetTypeError(f"Run {run_name!r} has no item-set hash for {bench!r}.")
        actual = hashlib.sha256((suite_root / f"{bench}.jsonl").read_bytes()).hexdigest()
        if actual != expected:
            raise ChecksetBuildError(f"Suite item-set hash mismatch for {bench!r} against run {run_name!r}.")


def read_json(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ChecksetTypeError(f"Expected JSON object in {path}.")
    return value


def read_jsonl(path: Path) -> tuple[JsonObject, ...]:
    return tuple(_read_json_line(line, path) for line in path.read_text(encoding="utf-8").splitlines() if line)


def required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ChecksetTypeError(f"{key} must be a string.")
    return value


def _verify_run_files(root: Path, entry: JsonObject) -> None:
    hashes = entry.get("sha256")
    if not isinstance(hashes, dict):
        raise ChecksetTypeError(f"Missing hashes for {root}.")
    resolved_root = root.resolve()
    for relative, expected in hashes.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ChecksetTypeError(f"Invalid expected hash for {relative}.")
        relative_path = Path(relative)
        if relative_path.is_absolute() or relative_path.anchor:
            raise ChecksetBuildError("Pinned input hash paths must stay within the pinned run directory.")
        candidate = (resolved_root / relative_path).resolve()
        if not candidate.is_relative_to(resolved_root):
            raise ChecksetBuildError("Pinned input hash paths must stay within the pinned run directory.")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            raise ChecksetBuildError(f"Pinned input hash mismatch: {candidate}.")


def _read_latencies(path: Path) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for record in read_jsonl(path):
        item_id = required_str(record, "item_id")
        payload = record.get("payload")
        latency = payload.get("latency_seconds") if isinstance(payload, dict) else None
        result[item_id] = float(latency) if isinstance(latency, int | float) else None
    return result


def _read_json_line(line: str, path: Path) -> JsonObject:
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ChecksetTypeError(f"Expected JSON object rows in {path}.")
    return value
