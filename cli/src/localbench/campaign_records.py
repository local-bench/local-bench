from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._suite import RenderedBench, item_hashes, suite_version
from localbench._types import BenchmarkItem, JsonObject, JsonValue
from localbench.run_schema import RUN_SCHEMA_VERSION

CAMPAIGN_SCHEMA_VERSION: Final = "localbench-campaign-v1"
RUNNER_SCHEMA_VERSION: Final = "localbench-runner-v1"
SCORING_SCHEMA_VERSION: Final = "localbench-scoring-v1"
REQUEST_SCHEMA_VERSION: Final = "openai-chat-completions-v1"


@dataclass(frozen=True, slots=True)
class CampaignConfig:
    endpoint: str
    model: str
    suite_id: str
    suite_hash: str
    suite_dir: Path
    suite_terms_accepted: bool
    tier: str
    lane: str
    provider: str
    concurrency: int
    max_items: int | None
    max_tokens: int | None
    reasoning_effort: str | None
    reasoning_activation: str
    hf_model_id: str | None
    output_path: Path
    server_fingerprint: str | None = None
    resume_identity: str | None = None
    serve_fingerprint: JsonObject | None = None


def campaign_record(
    config: CampaignConfig,
    suite: JsonObject,
    suite_dir: Path,
    benches: list[RenderedBench],
    *,
    started_at: str,
) -> JsonObject:
    item_files = [bench.item_file for bench in benches]
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "source_of_truth": {
            "intended_inputs": "campaign.json",
            "completed_work": "benchmarks/*.raw_results.jsonl, benchmarks/*.scored_items.jsonl, benchmarks/*.complete.json",
            "advisory_state": "run.status.json",
            "derived_outputs": "benchmarks/*.aggregate.json, localbench-run.json",
        },
        "created_at": started_at,
        "suite": {
            "suite_id": config.suite_id,
            "suite_hash": config.suite_hash,
            "suite_dir": str(config.suite_dir),
            "suite_version": suite_version(suite),
            "suite_terms_accepted": config.suite_terms_accepted,
            "item_set_hashes": item_hashes(suite_dir, item_files),
        },
        "benches": [bench.name for bench in benches],
        "tier": config.tier,
        "lane": config.lane,
        "items": {
            "total": _total_items(benches),
            "ordered": _campaign_items(benches),
        },
        "prompting": {
            "prompt_renderer": None,
            "prompt_renderer_digest": _rendered_prompt_digest(benches),
            "template_digests": _template_digests(suite, suite_dir, benches),
            "chat_template_digest": None,
            "tokenizer_digest": None,
        },
        "model": {
            "declared_model_id": config.model,
            "hf_model_id": config.hf_model_id,
            "model_artifact_hash": None,
        },
        "sampling": _sampling_by_bench(benches, config),
        "provider": {
            "name": config.provider,
            "adapter_version": config.provider,
            "request_schema_version": REQUEST_SCHEMA_VERSION,
            "endpoint": _redacted_endpoint(config.endpoint),
        },
        "versions": {
            "runner_schema_version": RUNNER_SCHEMA_VERSION,
            "scoring_schema_version": SCORING_SCHEMA_VERSION,
            "run_schema_version": RUN_SCHEMA_VERSION,
        },
        "execution": {
            "concurrency": max(1, config.concurrency),
            "max_attempts": 3,
            "timeout_seconds": 300.0,
            "retry_policy": {"kind": "exponential-jitter", "base_seconds": 0.5},
        },
        "serve_fingerprint": _serve_fingerprint(config),
        "git": {"commit": _git_commit()},
        "env_summary": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
        },
    }


def item_hash(item: BenchmarkItem) -> str:
    payload = json.dumps(item, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _campaign_items(benches: list[RenderedBench]) -> list[JsonObject]:
    rows: list[JsonObject] = []
    seq = 0
    for bench in benches:
        for item in bench.benchmark_items:
            rows.append(
                {
                    "bench": bench.name,
                    "item_id": item["id"],
                    "item_hash": item_hash(item),
                    "seq": seq,
                },
            )
            seq += 1
    return rows


def _total_items(benches: list[RenderedBench]) -> int:
    return sum(len(bench.benchmark_items) for bench in benches)


def _rendered_prompt_digest(benches: list[RenderedBench]) -> str:
    rendered = [
        {"bench": bench.name, "messages": item["messages"]}
        for bench in benches
        for item in bench.benchmark_items
    ]
    payload = json.dumps(rendered, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _template_digests(
    suite: JsonObject,
    suite_dir: Path,
    benches: list[RenderedBench],
) -> JsonObject:
    bench_configs = suite.get("benches")
    if not isinstance(bench_configs, dict):
        return {}
    digests: JsonObject = {}
    for bench in benches:
        cfg = bench_configs.get(bench.name)
        if not isinstance(cfg, dict):
            continue
        digest = _template_digest(cfg, suite_dir)
        if digest is not None:
            digests[bench.name] = digest
    return digests


def _template_digest(bench_config: dict[str, JsonValue], suite_dir: Path) -> str | None:
    inline = bench_config.get("template_text")
    if isinstance(inline, str):
        return hashlib.sha256(inline.encode("utf-8")).hexdigest()
    template = bench_config.get("template")
    if not isinstance(template, str):
        return None
    path = suite_dir / template
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sampling_by_bench(
    benches: list[RenderedBench],
    config: CampaignConfig,
) -> JsonObject:
    sampling: JsonObject = {}
    for bench in benches:
        sampling[bench.name] = {
            "decoding": bench.decoding,
            "max_tokens_override": config.max_tokens,
            "reasoning_effort": config.reasoning_effort,
            "reasoning_activation": config.reasoning_activation,
            "capped_thinking": config.lane == "capped-thinking",
        }
    return sampling


def _serve_fingerprint(config: CampaignConfig) -> JsonObject:
    if config.serve_fingerprint is not None:
        return dict(config.serve_fingerprint)
    return {
        "serve_mode": None,
        "server_fingerprint": config.server_fingerprint,
        "resume_identity": config.resume_identity,
        "server_binary_hash": None,
        "server_build": None,
        "server_command_redacted": None,
        "model_artifact_hash": None,
        "sampler_flags": None,
        "context_length": None,
        "gpu_layers": None,
        "seed_policy": None,
    }


def _git_commit() -> str | None:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def _redacted_endpoint(endpoint: str) -> str:
    return endpoint.split("?", maxsplit=1)[0]
