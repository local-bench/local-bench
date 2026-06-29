from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._scoring import BenchAggregate, ScoredItem
from localbench._types import ItemResult, JsonObject, JsonValue
from localbench.campaign import CampaignPaths
from localbench.persistence import atomic_write_bytes, atomic_write_json

CHECKPOINT_SCHEMA_VERSION: Final = "localbench-bench-checkpoint-v1"


@dataclass(frozen=True, slots=True)
class CompletedBench:
    name: str
    raw_results: list[JsonObject]
    scored_items: list[JsonObject]
    aggregate: JsonObject


class CheckpointCorruptionError(RuntimeError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def write_bench_checkpoint(
    paths: CampaignPaths,
    bench: str,
    raw_results: list[ItemResult],
    scored_items: list[ScoredItem],
    aggregate: BenchAggregate,
) -> None:
    paths.benchmarks_dir.mkdir(parents=True, exist_ok=True)
    raw_path = _bench_path(paths, bench, "raw_results.jsonl")
    scored_path = _bench_path(paths, bench, "scored_items.jsonl")
    aggregate_path = _bench_path(paths, bench, "aggregate.json")
    complete_path = _bench_path(paths, bench, "complete.json")
    atomic_write_bytes(_jsonl_bytes(raw_results), raw_path)
    atomic_write_bytes(_jsonl_bytes(scored_items), scored_path)
    atomic_write_json(aggregate, aggregate_path)
    complete: JsonObject = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "bench": bench,
        "raw_count": len(raw_results),
        "scored_count": len(scored_items),
        "raw_sha256": _sha256(raw_path),
        "scored_sha256": _sha256(scored_path),
        "aggregate_sha256": _sha256(aggregate_path),
    }
    atomic_write_json(complete, complete_path)


def completed_benches(paths: CampaignPaths) -> dict[str, CompletedBench]:
    completed: dict[str, CompletedBench] = {}
    if not paths.benchmarks_dir.exists():
        return completed
    for marker in sorted(paths.benchmarks_dir.glob("*.complete.json")):
        bench = marker.name.removesuffix(".complete.json")
        completed[bench] = read_completed_bench(paths, bench)
    return completed


def read_completed_bench(paths: CampaignPaths, bench: str) -> CompletedBench:
    complete_path = _bench_path(paths, bench, "complete.json")
    complete = _read_object(complete_path)
    if complete.get("schema_version") != CHECKPOINT_SCHEMA_VERSION or complete.get("bench") != bench:
        raise CheckpointCorruptionError(f"invalid complete marker for {bench}")
    raw_path = _bench_path(paths, bench, "raw_results.jsonl")
    scored_path = _bench_path(paths, bench, "scored_items.jsonl")
    aggregate_path = _bench_path(paths, bench, "aggregate.json")
    _validate_hash(complete, "raw_sha256", raw_path)
    _validate_hash(complete, "scored_sha256", scored_path)
    _validate_hash(complete, "aggregate_sha256", aggregate_path)
    raw_results = [_item_result(row, raw_path) for row in _read_jsonl(raw_path)]
    scored_items = [_scored_item(row, scored_path) for row in _read_jsonl(scored_path)]
    aggregate = _bench_aggregate(_read_object(aggregate_path), aggregate_path)
    if complete.get("raw_count") != len(raw_results) or complete.get("scored_count") != len(scored_items):
        raise CheckpointCorruptionError(f"checkpoint counts do not match for {bench}")
    return CompletedBench(bench, raw_results, scored_items, aggregate)


def _bench_path(paths: CampaignPaths, bench: str, suffix: str) -> Path:
    return paths.benchmarks_dir / f"{bench}.{suffix}"


def _jsonl_bytes(rows: list[JsonObject]) -> bytes:
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    return text.encode("utf-8")


def _read_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise CheckpointCorruptionError(f"checkpoint row is not an object: {path}")
        rows.append(raw)
    return rows


def _read_object(path: Path) -> JsonObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CheckpointCorruptionError(f"checkpoint file is not an object: {path}")
    return raw


def _validate_hash(complete: JsonObject, key: str, path: Path) -> None:
    expected = complete.get(key)
    if not isinstance(expected, str) or _sha256(path) != expected:
        raise CheckpointCorruptionError(f"checkpoint hash mismatch for {path.name}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _item_result(row: JsonObject, path: Path) -> JsonObject:
    _require_text(row, "id", path)
    return row


def _scored_item(row: JsonObject, path: Path) -> JsonObject:
    _require_text(row, "id", path)
    _require_text(row, "bench", path)
    return row


def _bench_aggregate(row: JsonObject, path: Path) -> JsonObject:
    for key in ("n", "n_errors", "n_extraction_failures"):
        value = row.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise CheckpointCorruptionError(f"aggregate {path} missing integer {key}")
    for key in ("raw_accuracy", "chance_corrected", "termination_rate", "conditional_accuracy"):
        value = row.get(key)
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise CheckpointCorruptionError(f"aggregate {path} missing number {key}")
    return row


def _require_text(row: JsonObject, key: str, path: Path) -> None:
    value: JsonValue | None = row.get(key)
    if not isinstance(value, str):
        raise CheckpointCorruptionError(f"checkpoint row in {path} missing string {key}")
