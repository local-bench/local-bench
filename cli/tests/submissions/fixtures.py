from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from localbench._scoring import aggregate, run_totals, score_bench
from localbench._suite import item_hashes, read_json_object, render_benches, suite_version
from localbench._types import ItemResult, JsonObject, Usage
from localbench.manifest import ManifestContext, collect_manifest
from localbench.runner import write_json
from localbench.scoring.axis_status import axis_status_for_benches
from localbench.submissions.foundation import normalize_result_bundle
from localbench.suite_verify import suite_hash

PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEINaxqiPDiYq1gpMivZnv4bRJ7Qd/fXn5PW18mrrmY8GS
-----END PRIVATE KEY-----
"""

FIXTURE_NAMES = {
    "valid",
    "tampered_aggregate",
    "tampered_item_correct",
    "tampered_output",
    "bad_signature",
    "wrong_scorecard",
    "wrong_suite_hash",
    "duplicate_item",
    "missing_item",
    "unknown_item",
    "path_traversal",
    "oversized_manifest",
}


@dataclass(frozen=True, slots=True)
class SubmissionFixtures:
    suite_dir: Path
    run_path: Path
    key_path: Path


async def build_submission_fixtures(tmp_path: Path) -> SubmissionFixtures:
    suite_dir = _write_suite(tmp_path / "suite")
    run_path = await _write_run(tmp_path / "run.json", suite_dir)
    key_path = tmp_path / "ed25519.pem"
    key_path.write_text(PRIVATE_KEY_PEM, encoding="utf-8")
    return SubmissionFixtures(suite_dir=suite_dir, run_path=run_path, key_path=key_path)


def mutate_zip_json(
    bundle_path: Path,
    out_path: Path,
    member: str,
    mutator,
    *,
    refresh_payload_sha: bool = False,
    signing_key_path: Path | None = None,
) -> Path:
    with zipfile.ZipFile(bundle_path, "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    data = json.loads(files[member].decode("utf-8"))
    data = mutator(data)
    if member == "manifest.json" and refresh_payload_sha:
        data = _refresh_manifest(data, signing_key_path)
    files[member] = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _write_zip(out_path, files)
    return out_path


def write_path_traversal_bundle(out_path: Path) -> Path:
    with zipfile.ZipFile(out_path, "w") as archive:
        archive.writestr("../manifest.json", "{}")
    return out_path


def write_oversized_manifest_bundle(out_path: Path) -> Path:
    payload = b'{"payload":"' + (b"x" * 300_000) + b'"}'
    _write_zip(out_path, {"manifest.json": payload})
    return out_path


def write_jsonl_bundle(
    bundle_path: Path,
    out_path: Path,
    mutator,
    *,
    signing_key_path: Path | None = None,
) -> Path:
    with zipfile.ZipFile(bundle_path, "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    records = [
        json.loads(line)
        for line in files["items.jsonl"].decode("utf-8").splitlines()
        if line.strip()
    ]
    mutated = mutator(records)
    files["items.jsonl"] = _jsonl_bytes(mutated)
    if signing_key_path is not None:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
        manifest["payload"]["files"] = [
            _refreshed_file_entry(entry, files)
            for entry in manifest["payload"]["files"]
        ]
        manifest["payload"]["counts"]["items_total"] = len(mutated)
        manifest = _refresh_manifest(manifest, signing_key_path)
        files["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _write_zip(out_path, files)
    return out_path


async def _write_run(path: Path, suite_dir: Path) -> Path:
    suite = read_json_object(suite_dir / "suite.json")
    warnings: list[str] = []
    rendered = render_benches("all", "standard", None, suite_dir, suite, warnings)
    assert warnings == []
    items = []
    item_files: list[str] = []
    results_by_bench: dict[str, list[ItemResult]] = {}
    for bench in rendered:
        item_files.append(bench.item_file)
        results = [_result(bench.benchmark_items[0]["id"], _answer_for(bench.name))]
        scored = score_bench(bench, results)
        items.extend(scored)
        results_by_bench[bench.name] = results
    totals = run_totals(items, 1.0)
    benches = {
        bench.name: aggregate(
            bench.name,
            [item for item in items if item["bench"] == bench.name],
            bench.baseline,
        )
        for bench in rendered
    }
    axis_status = axis_status_for_benches(benches)
    manifest = await collect_manifest(
        ManifestContext(
            endpoint="http://127.0.0.1:9/v1",
            requested_model="fixture-model",
            suite_version=suite_version(suite),
            tier="standard",
            lane="answer-only",
            item_set_hashes=item_hashes(suite_dir, item_files),
            sampling_by_bench={bench.name: bench.decoding for bench in rendered},
            concurrency=1,
            started_at="2026-06-24T00:00:00+00:00",
            finished_at="2026-06-24T00:00:01+00:00",
            wall_clock_s=1.0,
            totals={
                "items": totals["n_items"],
                "errors": totals["n_errors"],
                "prompt_tokens": totals["prompt_tokens"],
                "completion_tokens": totals["completion_tokens"],
                "total_tokens": totals["total_tokens"],
                "active_wall_seconds": 1.0,
                "completion_tokens_per_second": totals["completion_tokens_per_second"],
            },
            rendered_prompt_sample=rendered[0].benchmark_items[0],
            suite_id="fixture-suite-v1",
            suite_hash=suite_hash(suite_dir),
            suite_source="local",
        ),
    )
    run: JsonObject = {
        "schema": "localbench-run-v0",
        "schema_version": "localbench.run.v1",
        "submission_ticket_id": None,
        "server_nonce": None,
        "issued_at": None,
        "run_started_at": "2026-06-24T00:00:00+00:00",
        "run_finished_at": "2026-06-24T00:00:01+00:00",
        "source": "localbench-cli",
        "tier": "standard",
        "account": None,
        "model": {"name": "fixture-model"},
        "manifest": manifest,
        "axis_status": axis_status,
        "headline_complete": False,
        "benches": benches,
        "composite": 1.0,
        "conformance": {"status": "headline-comparable", "per_bench": {}},
        "items": items,
        "totals": totals,
        "warnings": [],
        "output_path": str(path),
    }
    run = normalize_result_bundle(run, suite_dir=suite_dir)
    write_json(run, path)
    return path


def _write_suite(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "mmlu_pro.jsonl").write_text(
        '{"id":"mmlu-1","question":"Pick A","options":["A","B"],"answer":"A"}\n',
        encoding="utf-8",
    )
    mmlu_hash = _sha(path / "mmlu_pro.jsonl")
    (path / "suite.json").write_text(
        json.dumps(
            {
                "id": "fixture-suite-v1",
                "version": "fixture-suite-v1",
                "benches": {
                    "mmlu_pro": {
                        "chance_correction_baseline": 0.5,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {
                            "standard": {
                                "file": "mmlu_pro.jsonl",
                                "item_count": 1,
                                "sha256": mmlu_hash,
                            },
                        },
                        "template_text": "{question}\n{options}",
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (path / "itemsets.lock.json").write_text(
        json.dumps({"files": {"mmlu_pro.jsonl": {"item_count": 1, "sha256": mmlu_hash}}}),
        encoding="utf-8",
    )
    return path


def _result(item_id: str, response_text: str) -> ItemResult:
    return {
        "id": item_id,
        "response_text": response_text,
        "reasoning_text": None,
        "finish_reason": "stop",
        "usage": _usage(),
        "latency_seconds": 0.0,
        "started_at": "2026-06-24T00:00:00+00:00",
        "finished_at": "2026-06-24T00:00:00+00:00",
        "attempts": 1,
        "error": None,
    }


def _usage() -> Usage:
    return {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


def _answer_for(bench: str) -> str:
    if bench == "mmlu_pro":
        return "Answer: A"
    return "ok"


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl_bytes(records: list[JsonObject]) -> bytes:
    return (
        "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records)
        + "\n"
    ).encode("utf-8")


def _refresh_manifest(manifest: JsonObject, signing_key_path: Path | None) -> JsonObject:
    from localbench.submissions.canon import canonical_json_hash
    from localbench.submissions.crypto import sign_manifest_payload

    manifest["payload_sha256"] = canonical_json_hash(manifest["payload"])
    if signing_key_path is not None:
        manifest["signature"] = sign_manifest_payload(manifest["payload"], signing_key_path)
    return manifest


def _refreshed_file_entry(entry: JsonObject, files: dict[str, bytes]) -> JsonObject:
    import hashlib

    path = str(entry["path"])
    data = files[path]
    return {**entry, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
