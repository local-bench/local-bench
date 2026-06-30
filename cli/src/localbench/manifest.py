"""Best-effort run manifest collection."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from localbench._types import BenchmarkItem, JsonObject, JsonValue, Totals
from localbench.scoring.scorecard import scorecard_identity
from localbench.submissions.canon import sha256_file

_MODEL_FIELDS: Final = (
    "model.family", "model.quant_label", "model.file_name", "model.file_size_bytes",
    "model.file_sha256", "model.format", "model.tokenizer_digest", "model.chat_template_digest",
)
_RUNTIME_FIELDS: Final = (
    "runtime.name", "runtime.version", "runtime.kv_cache_quant",
    "runtime.ctx_len_configured", "runtime.parallel_slots",
)
_LANES: Final = {"answer-only", "capped-thinking", "api-uncapped"}


@dataclass(frozen=True, slots=True)
class ManifestContext:
    endpoint: str
    requested_model: str
    suite_version: str
    tier: str
    lane: str
    item_set_hashes: dict[str, str]
    sampling_by_bench: dict[str, JsonObject]
    concurrency: int
    started_at: str
    finished_at: str
    wall_clock_s: float
    totals: Totals
    rendered_prompt_sample: BenchmarkItem | None
    suite_id: str | None = None
    suite_hash: str | None = None
    suite_source: str | None = None
    accepted_suite_terms: bool = False
    suite_license_manifest: JsonObject | None = None
    provider: str = "local"
    provider_notes: tuple[str, ...] = ()
    reasoning_effort: str | None = None
    thinking_budget: int = 0
    reasoning_registry_entry_id: str | None = None
    model_file: Path | None = None
    model_family: str | None = None
    quant_label: str | None = None
    model_format: str | None = None
    tokenizer_file: Path | None = None
    chat_template_file: Path | None = None
    runtime_name: str | None = None
    runtime_version: str | None = None
    kv_cache_quant: str | None = None
    ctx_len_configured: int | None = None
    parallel_slots: int | None = None
    build_flags: str | None = None
    runtime_backend: str | None = None
    cuda_version: str | None = None
    runner_build_id: str | None = None
    determinism_policy: str | None = None


async def collect_manifest(
    context: ManifestContext,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> JsonObject:
    """Collect a non-canonical manifest from endpoint, platform, and suite metadata."""
    reported_model = await _reported_model(context.endpoint, context.requested_model, transport)
    sampling: JsonObject = {
        "temperature": _common_sampling(context.sampling_by_bench, "temperature"),
        "top_p": _common_sampling(context.sampling_by_bench, "top_p"),
        "top_k": _common_sampling(context.sampling_by_bench, "top_k"),
        "min_p": _common_sampling(context.sampling_by_bench, "min_p"),
        "seed": _common_sampling(context.sampling_by_bench, "seed"),
        "thinking_mode": "n/a",
        "by_bench": context.sampling_by_bench,
    }
    if context.reasoning_effort is not None:
        sampling["reasoning_effort"] = context.reasoning_effort
    if context.reasoning_registry_entry_id is not None:
        sampling["reasoning_registry_entry_id"] = context.reasoning_registry_entry_id
    if context.determinism_policy is not None:
        sampling["determinism_policy"] = context.determinism_policy
    model = _model_identity(context)
    runtime = _runtime_identity(context)
    missing_fields = [
        field for field in (*_MODEL_FIELDS, *_RUNTIME_FIELDS) if _field_missing(model, runtime, field)
    ]
    if reported_model is None:
        missing_fields.append("endpoint.runtime_reported_model")
    scorecard = scorecard_identity(
        reasoning_registry_entry_id=context.reasoning_registry_entry_id,
    )
    return {
        "schema_version": "0.1",
        "suite": {
            "suite_id": context.suite_id,
            "suite_version": context.suite_version,
            "suite_hash": context.suite_hash,
            "source": context.suite_source,
            "tier": context.tier,
            "item_set_hashes": context.item_set_hashes,
            "lane": context.lane if context.lane in _LANES else "answer-only",
            "caps": _caps(context.sampling_by_bench, context.thinking_budget),
            "accepted_suite_terms": context.accepted_suite_terms,
            "license_manifest": context.suite_license_manifest or {"files": {}},
        },
        "scorecard": scorecard,
        "endpoint": {
            "kind": "local" if context.provider == "local" else "api",
            "runtime_reported_model": reported_model,
            "api_provider": None if context.provider == "local" else context.provider,
            "provider": context.provider,
            "divergence_notes": list(context.provider_notes),
        },
        "model": model,
        "runtime": runtime,
        "hardware": _hardware(),
        "sampling": sampling,
        "execution": {
            "client_version": "localbench 0.1.0",
            "concurrency": context.concurrency,
            "started_at": context.started_at,
            "finished_at": context.finished_at,
            "wall_clock_s": context.wall_clock_s,
            "measured_tok_s": {
                "prompt": _rate(context.totals["prompt_tokens"], context.wall_clock_s),
                "completion": _rate(context.totals["completion_tokens"], context.wall_clock_s),
            },
            "per_item_timing": "included in run record",
        },
        "rendered_prompt_sample": {
            "item_id": None if context.rendered_prompt_sample is None else context.rendered_prompt_sample["id"],
            "messages": [] if context.rendered_prompt_sample is None else context.rendered_prompt_sample["messages"],
        },
        "integrity": {
            "publishable": False,
            "validation_profile": "publishable-result-bundle-v1",
            "blocking_reasons": [],
            "missing_required_fields": missing_fields,
        },
        "provenance": _provenance(context, scorecard),
    }


async def _reported_model(
    endpoint: str,
    requested_model: str,
    transport: httpx.AsyncBaseTransport | None,
) -> str | None:
    async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
        try:
            response = await client.get(f"{endpoint.rstrip('/')}/models")
            if response.status_code >= 400:
                return None
            return _model_id(response.json(), requested_model)
        except (httpx.HTTPError, json.JSONDecodeError):
            return None


def _model_id(data: JsonValue, requested_model: str) -> str | None:
    if not isinstance(data, dict):
        return None
    models = data.get("data")
    if not isinstance(models, list):
        return None
    first_model = None
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if not isinstance(model_id, str):
            continue
        if model_id == requested_model:
            return model_id
        if first_model is None:
            first_model = model_id
    return first_model


def _model_identity(context: ManifestContext) -> JsonObject:
    model_file = context.model_file
    return {
        "family": context.model_family,
        "quant_label": context.quant_label,
        "file_name": None if model_file is None else model_file.name,
        "file_size_bytes": None if model_file is None else model_file.stat().st_size,
        "file_sha256": None if model_file is None else sha256_file(model_file),
        "format": context.model_format,
        "tokenizer_digest": _optional_file_hash(context.tokenizer_file),
        "chat_template_digest": _optional_file_hash(context.chat_template_file),
    }


def _runtime_identity(context: ManifestContext) -> JsonObject:
    runtime: JsonObject = {
        "name": context.runtime_name,
        "version": context.runtime_version,
        "kv_cache_quant": context.kv_cache_quant,
        "ctx_len_configured": context.ctx_len_configured,
        "parallel_slots": context.parallel_slots,
        "build_flags": context.build_flags,
    }
    if context.runtime_backend is not None:
        runtime["backend"] = context.runtime_backend
    if context.cuda_version is not None:
        runtime["cuda_version"] = context.cuda_version
    return runtime


def _optional_file_hash(path: Path | None) -> str | None:
    return None if path is None else sha256_file(path)


def _field_missing(model: JsonObject, runtime: JsonObject, dotted: str) -> bool:
    head, _, key = dotted.partition(".")
    source = model if head == "model" else runtime
    value = source.get(key)
    return value is None or value in {"", "unknown", "UNHASHED", "endpoint-applied-unknown"}


def _provenance(context: ManifestContext, scorecard: JsonObject) -> JsonObject:
    return {
        "localbench_repo_commit": _git_text("rev-parse", "HEAD"),
        "dirty_tree": _git_text("status", "--short") not in {None, ""},
        "cli_version": "0.1.0",
        "python_version": sys.version.split()[0],
        "dependency_lock_hash": _dependency_lock_hash(),
        "scorer_package_version": scorecard.get("scorecard_version"),
        "extractor_versions": scorecard.get("scorer_versions"),
        "runner_build_id": context.runner_build_id,
    }


def _dependency_lock_hash() -> str | None:
    cli_root = Path(__file__).resolve().parents[2]
    for name in ("uv.lock", "requirements.lock", "pyproject.toml"):
        path = cli_root / name
        if path.exists():
            return sha256_file(path)
    return None


def _git_text(*args: str) -> str | None:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _hardware() -> JsonObject:
    return {
        "gpus": _gpus(),
        "cpu": platform.processor() or platform.machine(),
        "ram_gb": None,
        "os": platform.platform(),
    }


def _gpus() -> list[JsonObject]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [_parse_gpu_line(line) for line in result.stdout.splitlines() if line.strip()]


def _parse_gpu_line(line: str) -> JsonObject:
    parts = [part.strip() for part in line.split(",")]
    name = parts[0] if parts else "unknown"
    memory = parts[1] if len(parts) > 1 else ""
    driver = parts[2] if len(parts) > 2 else "unknown"
    return {"name": name, "vram_mb": _memory_mb(memory), "driver": driver}


def _memory_mb(value: str) -> int | None:
    digits = "".join(char for char in value if char.isdigit())
    return int(digits) if digits else None


def _caps(sampling_by_bench: Mapping[str, JsonObject], thinking_budget: int = 0) -> JsonObject:
    return {
        "max_tokens_mcq": _max_tokens(sampling_by_bench, ("mmlu_pro",)),
        "max_tokens_math": _max_tokens(sampling_by_bench, ("genmath",)),
        "thinking_budget": thinking_budget,
    }


def _max_tokens(sampling_by_bench: Mapping[str, JsonObject], benches: tuple[str, ...]) -> int:
    values = [
        value
        for bench in benches
        if isinstance((value := sampling_by_bench.get(bench, {}).get("max_tokens")), int)
    ]
    return max(values) if values else 0


def _common_sampling(sampling_by_bench: Mapping[str, JsonObject], key: str) -> JsonValue:
    values = [params.get(key) for params in sampling_by_bench.values() if key in params]
    if not values:
        return None
    first = values[0]
    if all(value == first for value in values):
        return first
    return None


def _rate(tokens: int, seconds: float) -> float:
    return tokens / seconds if seconds > 0 else 0.0
