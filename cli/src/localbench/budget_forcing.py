"""s1-style thinking-budget forcing for the local capped-thinking lane.

Small Qwen3-family reasoning models served by vLLM (``--reasoning-parser qwen3``) keep
thinking past the ``max_tokens`` cap without ever emitting ``</think>``. The reasoning
parser buffers chain-of-thought and only flushes ``reasoning_content`` on the closing tag,
so a response truncated mid-think comes back with BOTH ``content`` and ``reasoning_content``
empty -> no answer -> scored wrong. The locked lane is "capped-thinking, budget 8192" but
that graceful budget was never enforced for local vLLM.

This module enforces it with two-pass budget forcing on the RAW ``/v1/completions`` endpoint
(the chat endpoint loses the text on truncation; raw completions does not, because no
reasoning parser is in the path):

* Pass 1 (think): render the chat messages to a raw chat prompt ending at the assistant
  turn; ``max_tokens=think_budget``, ``stop=["</think>"]``. ``finish_reason == "stop"``
  means the model closed thinking within budget; ``"length"`` means the budget was
  exceeded (forced).
* Pass 2 (answer): ``prompt + thinking + "\\n</think>\\n\\n"``; ``max_tokens=answer_budget``,
  ``stop=["<|im_end|>"]`` -> the answer.

Pass 2 always runs (with ``stop=["</think>"]`` pass 1 halts before the answer is generated).
The historical Qwen3 ChatML renderer remains the default; off-family runs can supply an
HF-tokenizer chat-template renderer.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Final, assert_never

import httpx

from localbench._requests import (
    backoff_seconds,
    http_error,
    is_retryable_status,
    item_result,
    utc_now,
)
from localbench._response import ResponseParseError, parse_usage
from localbench._types import (
    BenchmarkItem,
    ChatMessage,
    ItemResult,
    JsonObject,
    ParsedCompletion,
    Usage,
)
from localbench.prompt_rendering import PromptRenderer, ReasoningActivation

# The locked methodology thinking budget for the capped-thinking lane.
CAPPED_THINKING_THINK_BUDGET: Final = 8192
_MIN_ANSWER_BUDGET: Final = 1024
_IM_END: Final = "<|im_end|>"
# Sampling keys that must never be forwarded into a /completions body verbatim.
_FORCING_OMIT_KEYS: Final = frozenset({"max_tokens", "chat_template_kwargs", "thinking_budget", "reasoning_effort", "stop"})


@dataclass(frozen=True, slots=True)
class ForcingFormat:
    close: str
    forced_close: str
    answer_stop: tuple[str, ...]
    reasoning_open: str | None = None
    reparse: str | None = None


QWEN_FORCING: Final = ForcingFormat("</think>", "\n</think>\n\n", ("<|im_end|>",))
GEMMA4_FORCING: Final = ForcingFormat(
    "<channel|>", "\n<channel|>", ("<turn|>",), "<|channel>thought\n",
    r"(?s)<\|channel>thought\n(.*?)<channel\|>",
)


def forcing_format_for_activation(activation: ReasoningActivation) -> ForcingFormat:
    match activation:
        case "gemma4":
            return GEMMA4_FORCING
        case "qwen3" | "granite" | "nemotron" | "r1":
            return QWEN_FORCING
        case unreachable:
            assert_never(unreachable)


class _ForcedStatus(Exception):
    """An HTTP status failure during a forced completion pass."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


def render_qwen3_chat_prompt(messages: list[ChatMessage]) -> str:
    """Render chat messages into a raw Qwen3 ChatML prompt ending at the assistant turn.

    The model itself emits ``<think>`` after the assistant header, so this MUST NOT inject a
    ``<think>`` tag or any enable_thinking sentinel.
    """
    parts = [f"<|im_start|>{message['role']}\n{message['content']}{_IM_END}\n" for message in messages]
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def answer_budget_for(item: BenchmarkItem, think_budget: int) -> int:
    """Tokens left for the forced answer after the thinking budget, with a floor."""
    total_cap = item.get("max_tokens")
    if not isinstance(total_cap, int) or isinstance(total_cap, bool):
        raise ValueError("ranked capped-thinking forcing requires integer max_tokens")
    return max(total_cap - think_budget, _MIN_ANSWER_BUDGET)


async def run_forced_item(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    model: str,
    item: BenchmarkItem,
    semaphore: asyncio.Semaphore,
    max_attempts: int,
    backoff_base: float,
    prompt_renderer: PromptRenderer | None = None,
    forcing_format: ForcingFormat = QWEN_FORCING,
) -> ItemResult:
    """Run one item with two-pass thinking-budget forcing; never raises on request failure."""
    think_budget = int(item["think_budget"])  # type: ignore[typeddict-item]
    answer_budget = answer_budget_for(item, think_budget)
    decoding = _forcing_decoding(item["sampling_params"])
    prompt = (
        render_qwen3_chat_prompt(item["messages"])
        if prompt_renderer is None
        else prompt_renderer.render(item["messages"])
    )
    url = f"{base_url.rstrip('/')}/completions"

    async with semaphore:
        started_at = utc_now()
        started_perf = time.perf_counter()
        last_error = "request was not attempted"
        for attempt in range(1, max_attempts + 1):
            try:
                parsed = await _forced_two_pass(
                    client=client,
                    url=url,
                    headers=headers,
                    model=model,
                    prompt=prompt,
                    decoding=decoding,
                    think_budget=think_budget,
                    answer_budget=answer_budget,
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


async def _forced_two_pass(
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    model: str,
    prompt: str,
    decoding: JsonObject,
    think_budget: int,
    answer_budget: int,
    forcing_format: ForcingFormat,
) -> ParsedCompletion:
    """Execute the think pass and the forced-answer pass; return a merged completion."""
    think_data = await _post_completion(
        client, url, headers, model, prompt, think_budget, decoding, [forcing_format.close],
    )
    think_text, think_finish, think_usage = _extract_completion(think_data)
    forced = think_finish != "stop"

    answer_prompt = f"{prompt}{think_text}{forcing_format.forced_close}"
    answer_data = await _post_completion(
        client, url, headers, model, answer_prompt, answer_budget, decoding, list(forcing_format.answer_stop),
    )
    answer_text, answer_finish, answer_usage = _extract_completion(answer_data)
    for stop in forcing_format.answer_stop:
        if answer_text.endswith(stop):
            answer_text = answer_text[: -len(stop)]
            break
    # The forced close does not always stop a small model from reasoning more in the answer
    # pass; keep only the text after its own final reasoning close as the scored answer.
    extra_reasoning, answer_text = _split_reopened_reasoning(answer_text, forcing_format)
    answer = answer_text.strip()
    reasoning = (think_text + extra_reasoning).strip() or None

    return ParsedCompletion(
        response_text=answer,
        reasoning_text=reasoning,
        finish_reason="stop" if answer_finish == "stop" else "length",
        usage=_sum_usage(think_usage, answer_usage),
        thinking_forced=forced,
    )


def _split_reopened_reasoning(answer_text: str, forcing_format: ForcingFormat) -> tuple[str, str]:
    if forcing_format.reparse is not None:
        matches = list(re.finditer(forcing_format.reparse, answer_text))
        if not matches:
            return "", answer_text
        last = matches[-1]
        return answer_text[: last.end()], answer_text[last.end():]
    if forcing_format.close not in answer_text:
        return "", answer_text
    return answer_text.rsplit(forcing_format.close, 1)


async def _post_completion(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    model: str,
    prompt: str,
    max_tokens: int,
    decoding: JsonObject,
    stop: list[str],
) -> JsonObject:
    body: JsonObject = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "stop": stop,
        **decoding,
    }
    response = await client.post(url, headers=headers, json=body)
    if is_retryable_status(response.status_code):
        raise _ForcedStatus(http_error(response), retryable=True)
    if response.status_code >= 400:
        raise _ForcedStatus(http_error(response), retryable=False)
    data = response.json()
    if not isinstance(data, dict):
        raise ResponseParseError("completion response is not an object")
    return data


def _extract_completion(data: JsonObject) -> tuple[str, str | None, Usage]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ResponseParseError("completion choices are missing")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ResponseParseError("first completion choice is not an object")
    text = choice.get("text")
    text = text if isinstance(text, str) else ""
    finish_reason = choice.get("finish_reason")
    finish_reason = finish_reason if isinstance(finish_reason, str) else None
    return text, finish_reason, parse_usage(data.get("usage"))


def _forcing_decoding(sampling_params: JsonObject) -> JsonObject:
    return {key: value for key, value in sampling_params.items() if key not in _FORCING_OMIT_KEYS}


def _sum_usage(first: Usage, second: Usage) -> Usage:
    def _add(key: str) -> int | None:
        left = first.get(key)
        right = second.get(key)
        if left is None and right is None:
            return None
        return (left or 0) + (right or 0)

    return {
        "prompt_tokens": _add("prompt_tokens"),
        "completion_tokens": _add("completion_tokens"),
        "total_tokens": _add("total_tokens"),
    }
