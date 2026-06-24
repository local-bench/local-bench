from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from localbench._suite import read_json_object, render_benches
from localbench._types import JsonObject, JsonValue
from localbench.run_schema import check_run_schema_version
from localbench.scoring.scorecard import scorecard_identity
from localbench.submissions.archive import json_object_from_bytes
from localbench.submissions.canon import (
    canonical_json_bytes,
    canonical_json_hash,
    deterministic_zip,
    jsonl_bytes,
    sha256_bytes,
)
from localbench.submissions.contracts import MANIFEST_SCHEMA_VERSION, SUBMISSION_FORMAT
from localbench.submissions.crypto import manifest_payload_sha, sign_manifest_payload
from localbench.submissions.validate import SubmissionValidationError
from localbench.suite_verify import suite_hash, verify_suite_dir


def pack_submission_bundle(
    *,
    run_path: Path,
    suite_dir: Path,
    model_name: str,
    signing_key_path: Path,
    out_path: Path,
    offline: bool,
    created_at: str | None = None,
    run_nonce: str | None = None,
) -> JsonObject:
    if not offline:
        raise SubmissionValidationError("only offline submission tickets are supported in M1")
    verify_suite_dir(suite_dir)
    run = _read_run(run_path)
    check_run_schema_version(run)
    records = _submission_items(run, suite_dir)
    file_bytes = {
        "items.jsonl": jsonl_bytes(records),
        "run.original.json": canonical_json_bytes(run) + b"\n",
    }
    payload = _manifest_payload(
        run=run,
        suite_dir=suite_dir,
        model_name=model_name,
        file_bytes=file_bytes,
        created_at=created_at or _utc_now(),
        run_nonce=run_nonce or uuid.uuid4().hex,
        item_count=len(records),
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "payload": payload,
        "payload_sha256": manifest_payload_sha(payload),
        "signature": sign_manifest_payload(payload, signing_key_path),
    }
    deterministic_zip(out_path, {"manifest.json": canonical_json_bytes(manifest) + b"\n", **file_bytes})
    return manifest


def _manifest_payload(
    *,
    run: JsonObject,
    suite_dir: Path,
    model_name: str,
    file_bytes: dict[str, bytes],
    created_at: str,
    run_nonce: str,
    item_count: int,
) -> JsonObject:
    run_manifest = _object(run.get("manifest"))
    run_suite = _object(run_manifest.get("suite"))
    run_scorecard = _object(run_manifest.get("scorecard"))
    scorecard = scorecard_identity(_string(run_scorecard.get("reasoning_registry_entry_id")))
    return {
        "submission_format": SUBMISSION_FORMAT,
        "created_at": created_at,
        "run_nonce": run_nonce,
        "ticket": {
            "mode": "offline",
            "submission_id": f"offline-{run_nonce}",
            "server_nonce": "offline",
            "account_id": None,
        },
        "cli": {"name": "localbench", "version": "0.1.0"},
        "suite": {
            "id": _string(run_suite.get("suite_id")) or _string(run.get("tier")) or "local-suite",
            "version": _string(run_suite.get("suite_version")),
            "hash": suite_hash(suite_dir),
            "tier": _string(run_suite.get("tier")) or _string(run.get("tier")) or "standard",
            "item_set_hashes": _object(run_suite.get("item_set_hashes")),
        },
        "scorecard": {
            "version": _string(scorecard.get("scorecard_version")) or "",
            "id": _string(scorecard.get("scorecard_id")) or "",
            "registry_digest": _string(scorecard.get("registry_digest")) or "",
            "reasoning_registry_entry_id": scorecard.get("reasoning_registry_entry_id"),
        },
        "lane": {
            "name": _string(run_suite.get("lane")) or "answer-only",
            "sampler": _object(_object(run_manifest.get("sampling")).get("by_bench")),
        },
        "model_claim": _model_claim(run, run_manifest, model_name),
        "files": [
            {"path": name, "sha256": sha256_bytes(data), "size": len(data)}
            for name, data in sorted(file_bytes.items())
        ],
        "counts": {"items_total": item_count, "by_bench": _counts_by_bench(run)},
    }


def _submission_items(run: JsonObject, suite_dir: Path) -> list[JsonObject]:
    suite = read_json_object(suite_dir / "suite.json")
    tier = _string(_object(_object(run.get("manifest")).get("suite")).get("tier")) or _string(run.get("tier")) or "standard"
    names = sorted({bench for item in _list(run.get("items")) if isinstance((bench := item.get("bench")), str)})
    rendered = render_benches(",".join(names), tier, None, suite_dir, suite, [])
    source = {(bench.name, _item_id(item)): dict(item) for bench in rendered for item in bench.source_items}
    requests = {(bench.name, item["id"]): dict(item) for bench in rendered for item in bench.benchmark_items}
    records: list[JsonObject] = []
    for index, item in enumerate(_list(run.get("items"))):
        bench = _string(item.get("bench")) or ""
        item_id = _string(item.get("id")) or ""
        source_item = source.get((bench, item_id), {})
        request = requests.get((bench, item_id), {})
        records.append(_item_record(index, bench, item_id, item, source_item, request))
    return records


def _item_record(
    index: int,
    bench: str,
    item_id: str,
    item: JsonObject,
    source_item: JsonObject,
    request: JsonObject,
) -> JsonObject:
    return {
        "schema_version": "localbench.submission-item.v1",
        "sequence_index": index,
        "bench": bench,
        "item_id": item_id,
        "suite_item_sha256": canonical_json_hash(source_item),
        "request": {
            "messages": request.get("messages") if isinstance(request.get("messages"), list) else [],
            "sampling_params": _object(request.get("sampling_params")),
            "max_tokens": request.get("max_tokens"),
        },
        "response": {
            "text": item.get("response_text"),
            "finish_reason": item.get("finish_reason"),
            "error": item.get("error"),
        },
        "usage": _object(item.get("usage")),
        "timing": {
            "latency_seconds": item.get("latency_seconds"),
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "attempts": item.get("attempts"),
        },
        "client_scoring": {
            "correct": item.get("correct"),
            "extracted": item.get("extracted"),
            "failure_kind": item.get("failure_kind"),
        },
    }


def _read_run(path: Path) -> JsonObject:
    return json_object_from_bytes(path.read_bytes(), str(path))


def _model_claim(run: JsonObject, manifest: JsonObject, model_name: str) -> JsonObject:
    model = _object(run.get("model"))
    manifest_model = _object(manifest.get("model"))
    return {
        "display_name": _string(model.get("name")) or model_name,
        "artifact_url": None,
        "gguf_sha256": manifest_model.get("file_sha256"),
        "tokenizer_sha256": manifest_model.get("tokenizer_digest"),
        "chat_template_sha256": manifest_model.get("chat_template_digest"),
        "quantization": manifest_model.get("quant_label"),
    }


def _counts_by_bench(run: JsonObject) -> JsonObject:
    counts: dict[str, int] = {}
    for item in _list(run.get("items")):
        bench = _string(item.get("bench"))
        if bench is not None:
            counts[bench] = counts.get(bench, 0) + 1
    return counts


def _item_id(item: JsonObject) -> str:
    for key in ("id", "question_id", "key"):
        value = item.get(key)
        if isinstance(value, str | int):
            return str(value)
    return "unknown"


def _object(value: JsonValue | None) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: JsonValue | None) -> list[JsonObject]:
    return [dict(item) for item in value] if isinstance(value, list) and all(isinstance(item, dict) for item in value) else []


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
