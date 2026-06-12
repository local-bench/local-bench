"""Best-effort run manifest collection."""

from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import httpx

from localbench._types import BenchmarkItem, JsonObject, JsonValue, Totals

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


async def collect_manifest(
    context: ManifestContext,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> JsonObject:
    """Collect a non-canonical manifest from endpoint, platform, and suite metadata."""
    reported_model = await _reported_model(context.endpoint, context.requested_model, transport)
    missing_fields = [*_MODEL_FIELDS, *_RUNTIME_FIELDS]
    if reported_model is None:
        missing_fields.append("endpoint.runtime_reported_model")
    return {
        "schema_version": "0.1",
        "suite": {
            "suite_version": context.suite_version,
            "tier": context.tier,
            "item_set_hashes": context.item_set_hashes,
            "lane": context.lane if context.lane in _LANES else "answer-only",
            "caps": _caps(context.sampling_by_bench),
        },
        "endpoint": {
            "kind": "local",
            "runtime_reported_model": reported_model,
            "api_provider": None,
        },
        "model": {
            "family": None,
            "quant_label": None,
            "file_name": None,
            "file_size_bytes": None,
            "file_sha256": "UNHASHED",
            "format": None,
            "tokenizer_digest": "unknown",
            "chat_template_digest": "endpoint-applied-unknown",
        },
        "runtime": {
            "name": None,
            "version": None,
            "kv_cache_quant": "unknown",
            "ctx_len_configured": None,
            "parallel_slots": None,
            "build_flags": None,
        },
        "hardware": _hardware(),
        "sampling": {
            "temperature": _common_sampling(context.sampling_by_bench, "temperature"),
            "top_p": _common_sampling(context.sampling_by_bench, "top_p"),
            "top_k": _common_sampling(context.sampling_by_bench, "top_k"),
            "min_p": _common_sampling(context.sampling_by_bench, "min_p"),
            "seed": _common_sampling(context.sampling_by_bench, "seed"),
            "thinking_mode": "n/a",
            "by_bench": context.sampling_by_bench,
        },
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
            "canonical": False,
            "missing_fields": missing_fields,
        },
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


def _caps(sampling_by_bench: Mapping[str, JsonObject]) -> JsonObject:
    return {
        "max_tokens_mcq": _max_tokens(sampling_by_bench, ("mmlu_pro",)),
        "max_tokens_math": _max_tokens(sampling_by_bench, ("genmath",)),
        "thinking_budget": 0,
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
