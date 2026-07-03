"""Per-item HTTP request execution for the runner."""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import httpx

from localbench._response import (
    ResponseParseError,
    empty_usage,
)
from localbench._types import BenchmarkItem, ItemResult, JsonObject, ParsedCompletion
from localbench.prompt_rendering import PromptRenderer

if TYPE_CHECKING:
    from localbench.budget_forcing import ForcingFormat
from localbench.providers import (
    Lane,
    Provider,
    ProviderPayloadError,
    ReasoningEffort,
    provider_for_name,
)

_MAX_HTTP_ERROR_SNIPPET_CHARS: Final = 200
_SECRET_PATTERNS: Final = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}"),
)


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
    provider: Provider | None = None,
    lane: Lane = "answer-only",
    effort: ReasoningEffort | None = None,
    base_url: str | None = None,
    prompt_renderer: PromptRenderer | None = None,
    forcing_format: ForcingFormat | None = None,
) -> ItemResult:
    """Run one item and return a result instead of raising on request failure."""
    request_provider = provider or provider_for_name("local")
    if (
        request_provider.name == "local"
        and lane == "capped-thinking"
        and isinstance(item.get("think_budget"), int)
        and base_url is not None
    ):
        # Local capped-thinking enforces the locked thinking budget with two-pass forcing on
        # the raw /completions endpoint (see budget_forcing). Lazy import avoids a cycle.
        from localbench.budget_forcing import run_forced_item

        if forcing_format is None:
            return await run_forced_item(
                client=client,
                base_url=base_url,
                headers=headers,
                model=model,
                item=item,
                semaphore=semaphore,
                max_attempts=max_attempts,
                backoff_base=backoff_base,
                prompt_renderer=prompt_renderer,
            )
        return await run_forced_item(
            client=client,
            base_url=base_url,
            headers=headers,
            model=model,
            item=item,
            semaphore=semaphore,
            max_attempts=max_attempts,
            backoff_base=backoff_base,
            prompt_renderer=prompt_renderer,
            forcing_format=forcing_format,
        )
    async with semaphore:
        started_at = utc_now()
        started_perf = time.perf_counter()
        last_error = "request was not attempted"
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=request_provider.build_payload(
                        model,
                        item["messages"],
                        decoding(item),
                        lane,
                        effort=effort,
                    ),
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
                parsed = request_provider.parse_response(response.json())
                return item_result(item, started_at, started_perf, attempt, parsed=parsed)
            except httpx.TransportError as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                if attempt < max_attempts:
                    await asyncio.sleep(backoff_seconds(attempt, backoff_base))
                    continue
                return item_result(
                    item,
                    started_at,
                    started_perf,
                    attempt,
                    error=last_error,
                    error_type=exc.__class__.__name__,
                )
            except (json.JSONDecodeError, ProviderPayloadError, ResponseParseError) as exc:
                return item_result(
                    item,
                    started_at,
                    started_perf,
                    attempt,
                    error=f"{exc.__class__.__name__}: {exc}",
                    error_type=exc.__class__.__name__,
                )
        return item_result(item, started_at, started_perf, max_attempts, error=last_error)


def headers(api_key: str | None) -> dict[str, str]:
    """Build request headers for optional bearer authentication."""
    return provider_for_name("local").headers(api_key)


def payload(model: str, item: BenchmarkItem) -> JsonObject:
    """Build the OpenAI-compatible chat completion request body."""
    return provider_for_name("local").build_payload(
        model,
        item["messages"],
        decoding(item),
        "answer-only",
    )


def decoding(item: BenchmarkItem) -> JsonObject:
    body: JsonObject = {**item["sampling_params"]}
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
    error_type: str | None = None,
) -> ItemResult:
    """Build a stable item result record."""
    finished_at = utc_now()
    result: ItemResult = {
        "id": item["id"],
        "response_text": None if parsed is None else parsed.response_text,
        "reasoning_text": None if parsed is None else parsed.reasoning_text,
        "finish_reason": None if parsed is None else parsed.finish_reason,
        "usage": empty_usage() if parsed is None else parsed.usage,
        "latency_seconds": time.perf_counter() - started_perf,
        "started_at": started_at,
        "finished_at": finished_at,
        "attempts": attempts,
        "error": error,
        "thinking_forced": False if parsed is None else parsed.thinking_forced,
    }
    if error_type is not None:
        result["error_type"] = error_type
    return result


def is_retryable_status(status_code: int) -> bool:
    """Return whether an HTTP status should be retried."""
    return status_code == 429 or status_code >= 500


def http_error(response: httpx.Response) -> str:
    """Format an HTTP failure for storage in an item result."""
    body = response.text.strip()
    detail = body if body else response.reason_phrase
    return f"HTTP {response.status_code}: {_redacted_snippet(detail)}"


def _redacted_snippet(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("***REDACTED***", redacted)
    return redacted[:_MAX_HTTP_ERROR_SNIPPET_CHARS]


def backoff_seconds(attempt: int, base: float) -> float:
    """Return exponential backoff delay with jitter."""
    delay = base * (2 ** (attempt - 1))
    if delay <= 0:
        return 0.0
    return delay + random.uniform(0, delay * 0.1)


def utc_now() -> str:
    """Return a UTC timestamp in ISO 8601 form."""
    return datetime.now(UTC).isoformat()
