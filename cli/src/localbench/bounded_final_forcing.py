from __future__ import annotations

import asyncio
import json
import time

import httpx

from localbench._requests import backoff_seconds, item_result, utc_now
from localbench._response import ResponseParseError
from localbench._types import BenchmarkItem, ItemResult, JsonObject, ParsedCompletion, Usage
from localbench.budget_forcing import (
    ForcingFormat,
    _combine_server_timings,
    _ForcedStatus,
    _extract_completion,
    _forcing_decoding,
    _post_completion,
    _split_reopened_reasoning,
)
from localbench.lane_spec import BOUNDED_FINAL_MIN_FINAL, bounded_final_think_budget
from localbench.prompt_rendering import PromptRenderer


def bounded_final_answer_budget(total_cap: int, reasoning_tokens_used: int) -> int:
    min_final = min(BOUNDED_FINAL_MIN_FINAL, max(0, total_cap))
    return max(max(0, total_cap - max(0, reasoning_tokens_used)), min_final)


async def run_bounded_final_forced_item(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    model: str,
    item: BenchmarkItem,
    semaphore: asyncio.Semaphore,
    max_attempts: int,
    backoff_base: float,
    prompt_renderer: PromptRenderer,
    forcing_format: ForcingFormat,
) -> ItemResult:
    total_cap = _total_cap(item)
    think_budget = bounded_final_think_budget(total_cap, answer_reserve=_answer_reserve(item))
    decoding = _forcing_decoding(item["sampling_params"])
    prompt = prompt_renderer.render(item["messages"])
    url = f"{base_url.rstrip('/')}/completions"

    async with semaphore:
        started_at = utc_now()
        started_perf = time.perf_counter()
        last_error = "request was not attempted"
        for attempt in range(1, max_attempts + 1):
            try:
                parsed = await _bounded_final_two_pass(
                    client=client,
                    url=url,
                    headers=headers,
                    model=model,
                    prompt=prompt,
                    decoding=decoding,
                    total_cap=total_cap,
                    think_budget=think_budget,
                    forcing_format=forcing_format,
                )
                return item_result(item, started_at, started_perf, attempt, parsed=parsed)
            except _ForcedStatus as exc:
                last_error = exc.message
                if exc.retryable and attempt < max_attempts:
                    await asyncio.sleep(backoff_seconds(attempt, backoff_base))
                    continue
                return item_result(item, started_at, started_perf, attempt, error=last_error)
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
            except (json.JSONDecodeError, ResponseParseError) as exc:
                return item_result(
                    item,
                    started_at,
                    started_perf,
                    attempt,
                    error=f"{exc.__class__.__name__}: {exc}",
                    error_type=exc.__class__.__name__,
                )
        return item_result(item, started_at, started_perf, max_attempts, error=last_error)


async def _bounded_final_two_pass(
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    model: str,
    prompt: str,
    decoding: JsonObject,
    total_cap: int,
    think_budget: int,
    forcing_format: ForcingFormat,
) -> ParsedCompletion:
    if think_budget <= 0:
        think_text = ""
        think_finish = "length"
        think_usage = _empty_usage()
        think_timings = None
    else:
        think_data = await _post_completion(
            client,
            url,
            headers,
            model,
            prompt,
            think_budget,
            decoding,
            [forcing_format.close],
        )
        think_text, think_finish, think_usage, think_timings = _extract_completion(think_data)
    reasoning_tokens = _completion_tokens(think_usage)
    answer_budget = bounded_final_answer_budget(total_cap, reasoning_tokens)
    answer_prompt = f"{prompt}{think_text}{forcing_format.forced_close}"
    answer_data = await _post_completion(
        client,
        url,
        headers,
        model,
        answer_prompt,
        answer_budget,
        decoding,
        list(forcing_format.answer_stop),
    )
    answer_text, answer_finish, answer_usage, answer_timings = _extract_completion(answer_data)
    answer_text = _strip_answer_stop(answer_text, forcing_format.answer_stop)
    extra_reasoning, answer_text = _split_reopened_reasoning(answer_text, forcing_format)
    reasoning = (think_text + extra_reasoning).strip() or None
    return ParsedCompletion(
        response_text=answer_text.strip(),
        reasoning_text=reasoning,
        finish_reason="stop" if answer_finish == "stop" else "length",
        usage=_sum_usage(think_usage, answer_usage, reasoning_tokens),
        thinking_forced=think_finish != "stop",
        server_timings=_combine_server_timings(
            *([think_timings] if think_budget > 0 else []),
            answer_timings,
        ),
    )


def _total_cap(item: BenchmarkItem) -> int:
    total_cap = item.get("max_tokens")
    if not isinstance(total_cap, int) or isinstance(total_cap, bool):
        raise ValueError("ranked bounded-final forcing requires integer max_tokens")
    return total_cap


def _answer_reserve(item: BenchmarkItem) -> int:
    answer_reserve = item.get("answer_reserve")
    if isinstance(answer_reserve, int) and not isinstance(answer_reserve, bool):
        return max(0, answer_reserve)
    return BOUNDED_FINAL_MIN_FINAL


def _completion_tokens(usage: Usage) -> int:
    value = usage.get("completion_tokens")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _strip_answer_stop(answer_text: str, answer_stop: tuple[str, ...]) -> str:
    for stop in answer_stop:
        if answer_text.endswith(stop):
            return answer_text[: -len(stop)]
    return answer_text


def _empty_usage() -> Usage:
    return {
        "prompt_tokens": None,
        "completion_tokens": 0,
        "total_tokens": None,
    }


def _sum_usage(first: Usage, second: Usage, reasoning_tokens: int) -> Usage:
    def add(key: str) -> int | None:
        left = first.get(key)
        right = second.get(key)
        if left is None and right is None:
            return None
        return (left or 0) + (right or 0)

    return {
        "prompt_tokens": add("prompt_tokens"),
        "completion_tokens": add("completion_tokens"),
        "total_tokens": add("total_tokens"),
        "reasoning_tokens": reasoning_tokens,
    }
