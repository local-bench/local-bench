from __future__ import annotations

import hashlib
import json
import os
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


@dataclass(frozen=True, slots=True)
class ExpectedItemCheckpoint:
    seq: int
    item_id: str
    item_hash: str


@dataclass(frozen=True, slots=True)
class PartialItemCheckpoint:
    seq: int
    item_id: str
    item_hash: str
    raw_result: JsonObject
    scored_item: JsonObject | None


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    record_type: str
    item_id: str
    item_hash: str
    seq: int
    payload: JsonObject


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
    raw_envelopes = [
        _record_envelope(paths, "raw_result", bench, result["id"], _payload_hash(result), seq, result)
        for seq, result in enumerate(raw_results)
    ]
    scored_envelopes = [
        _record_envelope(paths, "scored_item", bench, item["id"], _payload_hash(item), seq, item)
        for seq, item in enumerate(scored_items)
    ]
    atomic_write_bytes(_jsonl_bytes(raw_envelopes), raw_path)
    atomic_write_bytes(_jsonl_bytes(scored_envelopes), scored_path)
    write_bench_complete(paths, bench, raw_results, scored_items, aggregate)


def append_item_checkpoint(
    paths: CampaignPaths,
    bench: str,
    seq: int,
    item_hash: str,
    raw_result: ItemResult,
    scored_item: ScoredItem,
) -> None:
    paths.benchmarks_dir.mkdir(parents=True, exist_ok=True)
    raw = _record_envelope(paths, "raw_result", bench, raw_result["id"], item_hash, seq, raw_result)
    scored = _record_envelope(paths, "scored_item", bench, scored_item["id"], item_hash, seq, scored_item)
    _append_jsonl(_bench_path(paths, bench, "raw_results.jsonl"), raw)
    _append_jsonl(_bench_path(paths, bench, "scored_items.jsonl"), scored)


def append_scored_checkpoint(
    paths: CampaignPaths,
    bench: str,
    seq: int,
    item_hash: str,
    scored_item: ScoredItem,
) -> None:
    scored = _record_envelope(paths, "scored_item", bench, scored_item["id"], item_hash, seq, scored_item)
    _append_jsonl(_bench_path(paths, bench, "scored_items.jsonl"), scored)


def write_bench_complete(
    paths: CampaignPaths,
    bench: str,
    raw_results: list[ItemResult],
    scored_items: list[ScoredItem],
    aggregate: BenchAggregate,
) -> None:
    raw_path = _bench_path(paths, bench, "raw_results.jsonl")
    scored_path = _bench_path(paths, bench, "scored_items.jsonl")
    aggregate_path = _bench_path(paths, bench, "aggregate.json")
    complete_path = _bench_path(paths, bench, "complete.json")
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


def read_partial_item_checkpoints(
    paths: CampaignPaths,
    bench: str,
    expected_items: list[ExpectedItemCheckpoint],
) -> list[PartialItemCheckpoint]:
    raw_path = _bench_path(paths, bench, "raw_results.jsonl")
    scored_path = _bench_path(paths, bench, "scored_items.jsonl")
    expected = {(item.item_id, item.item_hash, item.seq): item for item in expected_items}
    raw_records = _records_by_expected_key(
        _read_checkpoint_records(raw_path, bench=bench, record_type="raw_result", truncate_torn=True),
        expected,
        raw_path,
    )
    scored_records = _records_by_expected_key(
        _read_checkpoint_records(scored_path, bench=bench, record_type="scored_item", truncate_torn=True),
        expected,
        scored_path,
    )
    checkpoints: list[PartialItemCheckpoint] = []
    for expected_item in expected_items:
        key = (expected_item.item_id, expected_item.item_hash, expected_item.seq)
        raw = raw_records.get(key)
        scored = scored_records.get(key)
        if raw is None and scored is not None:
            raise CheckpointCorruptionError(f"scored checkpoint without raw result for {bench}:{expected_item.item_id}")
        if raw is not None:
            checkpoints.append(
                PartialItemCheckpoint(
                    seq=expected_item.seq,
                    item_id=expected_item.item_id,
                    item_hash=expected_item.item_hash,
                    raw_result=raw.payload,
                    scored_item=scored.payload if scored is not None else None,
                )
            )
    return checkpoints


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
    raw_results = [
        _item_result(record.payload, raw_path)
        for record in _read_checkpoint_records(raw_path, bench=bench, record_type="raw_result", truncate_torn=False)
    ]
    scored_items = [
        _scored_item(record.payload, scored_path)
        for record in _read_checkpoint_records(
            scored_path, bench=bench, record_type="scored_item", truncate_torn=False
        )
    ]
    aggregate = _bench_aggregate(_read_object(aggregate_path), aggregate_path)
    if complete.get("raw_count") != len(raw_results) or complete.get("scored_count") != len(scored_items):
        raise CheckpointCorruptionError(f"checkpoint counts do not match for {bench}")
    return CompletedBench(bench, raw_results, scored_items, aggregate)


def _bench_path(paths: CampaignPaths, bench: str, suffix: str) -> Path:
    return paths.benchmarks_dir / f"{bench}.{suffix}"


def _jsonl_bytes(rows: list[JsonObject]) -> bytes:
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    return text.encode("utf-8")


def _append_jsonl(path: Path, row: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(json.dumps(row, sort_keys=True).encode("utf-8"))
        handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_checkpoint_records(
    path: Path,
    *,
    bench: str,
    record_type: str,
    truncate_torn: bool,
) -> list[CheckpointRecord]:
    if not path.exists():
        return []
    records: dict[tuple[str, str, str, int], CheckpointRecord] = {}
    payload_hashes: dict[tuple[str, str, str, int], str] = {}
    for line in _complete_jsonl_lines(path, truncate_torn=truncate_torn):
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise CheckpointCorruptionError(f"checkpoint row is not an object: {path}")
        record = _checkpoint_record(raw, path, bench=bench, record_type=record_type)
        key = (record.record_type, record.item_id, record.item_hash, record.seq)
        payload_hash = _payload_hash(record.payload)
        existing_hash = payload_hashes.get(key)
        if existing_hash is not None and existing_hash != payload_hash:
            raise CheckpointCorruptionError(f"conflicting duplicate checkpoint row in {path}")
        payload_hashes[key] = payload_hash
        records.setdefault(key, record)
    return [records[key] for key in sorted(records, key=lambda item: item[3])]


def _complete_jsonl_lines(path: Path, *, truncate_torn: bool) -> list[str]:
    data = path.read_bytes()
    if truncate_torn and data and not data.endswith(b"\n"):
        final_newline = data.rfind(b"\n")
        data = b"" if final_newline == -1 else data[: final_newline + 1]
    return data.decode("utf-8").splitlines()


def _record_envelope(
    paths: CampaignPaths,
    record_type: str,
    bench: str,
    item_id: str,
    item_hash: str,
    seq: int,
    payload: JsonObject,
) -> JsonObject:
    return {
        "record_type": record_type,
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "campaign_id": paths.root.name,
        "bench": bench,
        "item_id": item_id,
        "item_hash": item_hash,
        "seq": seq,
        "segment_id": "segment-1",
        "payload": payload,
        "payload_sha256": _payload_hash(payload),
    }


def _checkpoint_record(row: JsonObject, path: Path, *, bench: str, record_type: str) -> CheckpointRecord:
    if row.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointCorruptionError(f"checkpoint row in {path} has invalid schema")
    if row.get("record_type") != record_type:
        raise CheckpointCorruptionError(f"checkpoint row in {path} has invalid record_type")
    if row.get("bench") != bench:
        raise CheckpointCorruptionError(f"checkpoint row in {path} has invalid bench")
    item_id = row.get("item_id")
    item_hash = row.get("item_hash")
    seq = row.get("seq")
    if not isinstance(item_id, str) or not isinstance(item_hash, str):
        raise CheckpointCorruptionError(f"checkpoint row in {path} missing item identity")
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise CheckpointCorruptionError(f"checkpoint row in {path} missing integer seq")
    payload = _payload_from_record(row, path)
    payload_id = payload.get("id")
    if payload_id != item_id:
        raise CheckpointCorruptionError(f"checkpoint payload id mismatch in {path}")
    if record_type == "scored_item" and payload.get("bench") != bench:
        raise CheckpointCorruptionError(f"checkpoint scored payload bench mismatch in {path}")
    return CheckpointRecord(record_type, item_id, item_hash, seq, payload)


def _payload_from_record(row: JsonObject, path: Path) -> JsonObject:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise CheckpointCorruptionError(f"checkpoint row in {path} missing payload")
    expected = row.get("payload_sha256")
    if not isinstance(expected, str) or expected != _payload_hash(payload):
        raise CheckpointCorruptionError(f"checkpoint payload hash mismatch in {path}")
    return payload


def _records_by_expected_key(
    records: list[CheckpointRecord],
    expected: dict[tuple[str, str, int], ExpectedItemCheckpoint],
    path: Path,
) -> dict[tuple[str, str, int], CheckpointRecord]:
    by_key: dict[tuple[str, str, int], CheckpointRecord] = {}
    for record in records:
        key = (record.item_id, record.item_hash, record.seq)
        if key not in expected:
            raise CheckpointCorruptionError(f"checkpoint row in {path} does not match campaign item set")
        by_key[key] = record
    return by_key


def _payload_hash(payload: JsonObject) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


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
