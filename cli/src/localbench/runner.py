"""Async benchmark runner for OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from localbench._requests import run_item, utc_now
from localbench.budget_forcing import forcing_format_for_activation
from localbench._types import (
    BenchmarkItem,
    ChatMessage,
    ItemResult,
    JsonObject,
    JsonScalar,
    JsonValue,
    RunRecord,
    Totals,
    Usage,
)
from localbench.prompt_rendering import (
    PromptRenderer,
    ReasoningActivation,
    build_forced_prompt_renderer,
)
from localbench.providers import Lane, Provider, ReasoningEffort, provider_for_name

if TYPE_CHECKING:
    from localbench.budget_forcing import ForcingFormat

__all__ = [
    "BenchmarkItem",
    "ChatMessage",
    "ItemResult",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "RunRecord",
    "Totals",
    "Usage",
    "run_benchmark",
    "write_json",
]


async def run_benchmark(
    *,
    base_url: str,
    model: str,
    items: list[BenchmarkItem],
    api_key: str | None = None,
    concurrency: int = 4,
    timeout: float = 300.0,
    max_attempts: int = 3,
    transport: httpx.AsyncBaseTransport | None = None,
    backoff_base: float = 0.5,
    provider: Provider | None = None,
    lane: Lane = "answer-only",
    effort: ReasoningEffort | None = None,
    hf_model_id: str | None = None,
    reasoning_activation: ReasoningActivation = "qwen3",
    prompt_renderer: PromptRenderer | None = None,
    forcing_format: ForcingFormat | None = None,
) -> RunRecord:
    """Run benchmark items against an OpenAI-compatible chat endpoint."""
    request_provider = provider or provider_for_name("local")
    effective_concurrency = max(1, concurrency)
    effective_attempts = max(1, max_attempts)
    endpoint = base_url.rstrip("/")
    semaphore = asyncio.Semaphore(effective_concurrency)
    started_at = utc_now()
    started_perf = time.perf_counter()
    forced_prompt_renderer = prompt_renderer or (
        build_forced_prompt_renderer(hf_model_id, reasoning_activation)
        if request_provider.name == "local" and lane == "capped-thinking"
        else None
    )
    forced_format = forcing_format or forcing_format_for_activation(reasoning_activation)

    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        results = await asyncio.gather(
            *[
                run_item(
                    client=client,
                    url=request_provider.endpoint_url(endpoint),
                    headers=request_provider.headers(api_key),
                    model=model,
                    item=item,
                    semaphore=semaphore,
                    max_attempts=effective_attempts,
                    backoff_base=backoff_base,
                    provider=request_provider,
                    lane=lane,
                    effort=effort,
                    base_url=endpoint,
                    prompt_renderer=forced_prompt_renderer,
                    forcing_format=forced_format,
                )
                for item in items
            ],
        )

    active_wall_seconds = time.perf_counter() - started_perf
    finished_at = utc_now()
    return {
        "run": {
            "endpoint": endpoint,
            "model": model,
            "params": {
                "concurrency": effective_concurrency,
                "timeout_seconds": timeout,
                "max_attempts": effective_attempts,
            },
            "started_at": started_at,
            "finished_at": finished_at,
        },
        "totals": _totals(results, active_wall_seconds),
        "results": results,
    }


def write_json(record: RunRecord | JsonObject, path: str | Path) -> None:
    """Write a run record to a JSON file."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")


def _totals(results: list[ItemResult], active_wall_seconds: float) -> Totals:
    completion_tokens = _sum_usage(results, "completion_tokens")
    tokens_per_second = (
        completion_tokens / active_wall_seconds if active_wall_seconds > 0 else 0.0
    )
    return {
        "items": len(results),
        "errors": sum(1 for result in results if result["error"] is not None),
        "prompt_tokens": _sum_usage(results, "prompt_tokens"),
        "completion_tokens": completion_tokens,
        "total_tokens": _sum_usage(results, "total_tokens"),
        "active_wall_seconds": active_wall_seconds,
        "completion_tokens_per_second": tokens_per_second,
    }


def _sum_usage(results: list[ItemResult], key: str) -> int:
    return sum(
        value
        for result in results
        if isinstance((value := result["usage"][key]), int)
    )
