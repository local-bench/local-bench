"""Async benchmark runner for OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx

from localbench._requests import headers, run_item, utc_now
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
) -> RunRecord:
    """Run benchmark items against an OpenAI-compatible chat endpoint."""
    effective_concurrency = max(1, concurrency)
    effective_attempts = max(1, max_attempts)
    endpoint = base_url.rstrip("/")
    semaphore = asyncio.Semaphore(effective_concurrency)
    started_at = utc_now()
    started_perf = time.perf_counter()

    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        results = await asyncio.gather(
            *[
                run_item(
                    client=client,
                    url=f"{endpoint}/chat/completions",
                    headers=headers(api_key),
                    model=model,
                    item=item,
                    semaphore=semaphore,
                    max_attempts=effective_attempts,
                    backoff_base=backoff_base,
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
