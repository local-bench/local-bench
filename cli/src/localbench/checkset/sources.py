from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from localbench.checkset.models import (
    ChecksetBuildError,
    ChecksetTypeError,
    ItemRecord,
    JsonObject,
    ModuleRecord,
)
from localbench.checkset.select import SourceItem, select_cost_aware, select_ifbench

RUN_NAMES: Final = ("base_q5km", "q6k", "udq2", "fusion")
BENCHES: Final = ("bigcodebench_hard", "ifbench", "olymmath_hard", "amo", "tc_json_v1")
CODING_EXCLUSIONS: Final = (
    "bcbh-006",
    "bcbh-007",
    "bcbh-014",
    "bcbh-035",
    "bcbh-074",
    "bcbh-096",
    "bcbh-104",
)
IFBENCH_QUOTAS: Final = {
    "format": 35,
    "words": 30,
    "count": 23,
    "ratio": 16,
    "sentence": 10,
    "custom": 4,
    "repeat": 2,
}


def build_local_modules(repo_root: Path) -> tuple[tuple[ModuleRecord, ...], tuple[JsonObject, ...]]:
    suite_rows = {bench: _read_jsonl(repo_root / "suite" / "v2" / f"{bench}.jsonl") for bench in BENCHES}
    manifest = _read_json(repo_root / "docs" / "v2" / "inputs" / "inputs-manifest.json")
    correctness, latency = _load_verified_runs(manifest)
    source_items = {
        bench: _source_items(bench, rows, correctness, latency)
        for bench, rows in suite_rows.items()
    }
    coding_pool = tuple(
        item for item in source_items["bigcodebench_hard"] if item.item_id not in CODING_EXCLUSIONS
    )
    coding_informative = tuple(item for item in coding_pool if item.informative)
    coding_complement = tuple(item for item in coding_pool if not item.informative)
    coding = tuple(sorted(coding_informative, key=lambda item: item.item_id)) + select_cost_aware(
        coding_complement,
        quota=58,
        median_pool=coding_pool,
    )
    if len(coding_informative) != 38 or len(coding) != 96:
        raise ChecksetBuildError(f"Coding selection mismatch: {len(coding_informative)} informative, {len(coding)} total.")

    instruction = select_ifbench(source_items["ifbench"], IFBENCH_QUOTAS, informative_quota=72)
    informative_count = sum(item.informative for item in instruction)
    if informative_count != 72 or len(instruction) != 120:
        raise ChecksetBuildError(f"IFBench selection mismatch: {informative_count} informative, {len(instruction)} total.")

    legacy_pool = tuple(
        item
        for bench in ("olymmath_hard", "amo")
        for item in source_items[bench]
        if item.informative
    )
    if len(legacy_pool) != 55:
        raise ChecksetBuildError(f"Legacy math informative pool is {len(legacy_pool)}, expected 55.")
    math_legacy = select_cost_aware(legacy_pool, quota=30)

    tools_pool = source_items["tc_json_v1"]
    fresh_ids = {
        _required_str(row, "id")
        for row in suite_rows["tc_json_v1"]
        if row.get("stratum") == "fresh_common_tools"
    }
    fresh = tuple(item for item in tools_pool if item.item_id in fresh_ids)
    informative_bfcl = tuple(
        item for item in tools_pool if item.item_id not in fresh_ids and item.informative
    )
    selected_ids = fresh_ids | {item.item_id for item in informative_bfcl}
    complement = min(
        (item for item in tools_pool if item.item_id not in selected_ids and item.tool_count > 1),
        key=lambda item: item.item_id,
    )
    tools = tuple(sorted(fresh + informative_bfcl + (complement,), key=lambda item: item.item_id))
    if len(fresh) != 30 or len(informative_bfcl) != 23 or len(tools) != 54:
        raise ChecksetBuildError(
            f"Tools selection mismatch: {len(fresh)} fresh, {len(informative_bfcl)} informative, {len(tools)} total."
        )

    modules = (
        _module("coding", coding),
        _module("instruction", instruction),
        _module("math-legacy", math_legacy),
        _module("tools-single", tools),
    )
    exclusions = tuple(_coding_exclusion(item_id) for item_id in CODING_EXCLUSIONS)
    return modules, exclusions


def _coding_exclusion(item_id: str) -> JsonObject:
    return {
        "item_id": item_id,
        "module": "coding",
        "reason": "sandbox-unscoreable",
    }


def _module(name: str, items: tuple[SourceItem, ...]) -> ModuleRecord:
    records = tuple(ItemRecord(item.item_id, item.content_sha256) for item in items)
    return ModuleRecord(name=name, scored=len(records), items=records)


def _source_items(
    bench: str,
    rows: tuple[JsonObject, ...],
    correctness: dict[str, dict[str, dict[str, bool]]],
    latency: dict[str, dict[str, float | None]],
) -> tuple[SourceItem, ...]:
    items: list[SourceItem] = []
    for row in rows:
        item_id = _required_str(row, "id")
        correct_count = sum(correctness[run][bench][item_id] for run in RUN_NAMES)
        raw_instruction_ids = row.get("instruction_id_list", [])
        instruction_ids = tuple(value for value in raw_instruction_ids if isinstance(value, str)) if isinstance(raw_instruction_ids, list) else ()
        raw_tools = row.get("tools", [])
        tool_count = len(raw_tools) if isinstance(raw_tools, list) else 0
        items.append(
            SourceItem(
                item_id=item_id,
                content_sha256=_content_sha256(row),
                informative=0 < correct_count < 4,
                latency_seconds=latency[bench][item_id],
                instruction_ids=instruction_ids,
                tool_count=tool_count,
            )
        )
    return tuple(items)


def _load_verified_runs(
    manifest: JsonObject,
) -> tuple[dict[str, dict[str, dict[str, bool]]], dict[str, dict[str, float | None]]]:
    correctness: dict[str, dict[str, dict[str, bool]]] = {}
    base_latency: dict[str, dict[str, float | None]] = {}
    for run_name in RUN_NAMES:
        entry = manifest[run_name]
        if not isinstance(entry, dict):
            raise ChecksetTypeError(f"Invalid input manifest entry {run_name!r}.")
        root = Path(_required_str(entry, "source_path"))
        _verify_run_files(root, entry)
        run = _read_json(root / "localbench-run.json")
        items = run.get("items")
        if not isinstance(items, list):
            raise ChecksetTypeError(f"Run {run_name!r} has no item list.")
        per_bench = {bench: {} for bench in BENCHES}
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


def _verify_run_files(root: Path, entry: JsonObject) -> None:
    hashes = entry.get("sha256")
    if not isinstance(hashes, dict):
        raise ChecksetTypeError(f"Missing hashes for {root}.")
    for relative, expected in hashes.items():
        if not isinstance(expected, str):
            raise ChecksetTypeError(f"Invalid expected hash for {relative}.")
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ChecksetBuildError(f"Pinned input hash mismatch: {root / relative}.")


def _read_latencies(path: Path) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for record in _read_jsonl(path):
        item_id = _required_str(record, "item_id")
        payload = record.get("payload")
        latency = payload.get("latency_seconds") if isinstance(payload, dict) else None
        result[item_id] = float(latency) if isinstance(latency, int | float) else None
    return result


def _content_sha256(row: JsonObject) -> str:
    data = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ChecksetTypeError(f"Expected JSON object in {path}.")
    return value


def _read_jsonl(path: Path) -> tuple[JsonObject, ...]:
    return tuple(_read_json_line(line, path) for line in path.read_text(encoding="utf-8").splitlines() if line)


def _read_json_line(line: str, path: Path) -> JsonObject:
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ChecksetTypeError(f"Expected JSON object rows in {path}.")
    return value


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ChecksetTypeError(f"{key} must be a string.")
    return value
