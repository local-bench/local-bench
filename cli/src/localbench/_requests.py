"""Per-item HTTP request execution for the runner."""

from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import UTC, datetime

import httpx

from localbench._response import (
    ResponseParseError,
    empty_usage,
    parse_chat_completion,
)
from localbench._types import BenchmarkItem, ItemResult, JsonObject, ParsedCompletion


async def run_item(
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    model: str,
    item: BenchmarkItem,
    semaphore: asyncio.Semaphore,
    max_attempts: int,
    backoff_base: float,
) -> ItemResult:
    """Run one item and return a result instead of raising on request failure."""
    async with semaphore:
        started_at = utc_now()
        started_perf = time.perf_counter()
        last_error = "request was not attempted"
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload(model, item),
                )
                if is_retryable_status(response.status_code):
                    last_error = http_error(response)
                    if attempt < max_attempts:
                        await asyncio.sleep(backoff_seconds(attempt, backoff_base))
                        continue
                    return item_result(item, started_at, started_perf, attempt, error=last_error)
                if response.status_code >= 400:
                    return item_result(
                        item,
                        started_at,
                        started_perf,
                        attempt,
                        error=http_error(response),
                    )
                parsed = parse_chat_completion(response.json())
                return item_result(item, started_at, started_perf, attempt, parsed=parsed)
            except httpx.TransportError as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                if attempt < max_attempts:
                    await asyncio.sleep(backoff_seconds(attempt, backoff_base))
                    continue
                return item_result(item, started_at, started_perf, attempt, error=last_error)
            except (json.JSONDecodeError, ResponseParseError) as exc:
                return item_result(
                    item,
                    started_at,
                    started_perf,
                    attempt,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
        return item_result(item, started_at, started_perf, max_attempts, error=last_error)


def headers(api_key: str | None) -> dict[str, str]:
    """Build request headers for optional bearer authentication."""
    request_headers = {"content-type": "application/json"}
    if api_key:
        request_headers["authorization"] = f"Bearer {api_key}"
    return request_headers


def payload(model: str, item: BenchmarkItem) -> JsonObject:
    """Build the OpenAI-compatible chat completion request body."""
    body: JsonObject = {
        "model": model,
        "messages": item["messages"],
        **item["sampling_params"],
    }
    if "max_tokens" in item:
        body["max_tokens"] = item["max_tokens"]
    return body


def item_result(
    item: BenchmarkItem,
    started_at: str,
    started_perf: float,
    attempts: int,
    *,
    parsed: ParsedCompletion | None = None,
    error: str | None = None,
) -> ItemResult:
    """Build a stable item result record."""
    finished_at = utc_now()
    return {
        "id": item["id"],
        "response_text": None if parsed is None else parsed.response_text,
        "finish_reason": None if parsed is None else parsed.finish_reason,
        "usage": empty_usage() if parsed is None else parsed.usage,
        "latency_seconds": time.perf_counter() - started_perf,
        "started_at": started_at,
        "finished_at": finished_at,
        "attempts": attempts,
        "error": error,
    }


def is_retryable_status(status_code: int) -> bool:
    """Return whether an HTTP status should be retried."""
    return status_code == 429 or status_code >= 500


def http_error(response: httpx.Response) -> str:
    """Format an HTTP failure for storage in an item result."""
    body = response.text.strip()
    detail = body if body else response.reason_phrase
    return f"HTTP {response.status_code}: {detail}"


def backoff_seconds(attempt: int, base: float) -> float:
    """Return exponential backoff delay with jitter."""
    delay = base * (2 ** (attempt - 1))
    if delay <= 0:
        return 0.0
    return delay + random.uniform(0, delay * 0.1)


def utc_now() -> str:
    """Return a UTC timestamp in ISO 8601 form."""
    return datetime.now(UTC).isoformat()
