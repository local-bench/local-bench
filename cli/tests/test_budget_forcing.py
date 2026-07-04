"""Tests for s1-style thinking-budget forcing on the local capped-thinking lane."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence

import httpx
import pytest

from localbench._types import JsonValue
from localbench.budget_forcing import (
    CAPPED_THINKING_THINK_BUDGET,
    answer_budget_for,
    render_qwen3_chat_prompt,
    run_forced_item,
)
from localbench.lane_conformance import assess_conformance
from localbench.manifest import _caps
from localbench.prompt_rendering import HfChatPromptRenderer
from localbench.runner import run_benchmark


def _completion(text: str, finish_reason: str, *, prompt_tokens: int, completion_tokens: int) -> dict:
    return {
        "choices": [{"text": text, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _item(think_budget: int | None = 8192, max_tokens: int = 16384) -> dict:
    item: dict = {
        "id": "item-1",
        "messages": [{"role": "user", "content": "Pick C"}],
        "sampling_params": {"temperature": 0},
        "max_tokens": max_tokens,
    }
    if think_budget is not None:
        item["think_budget"] = think_budget
    return item


# --- renderer ---------------------------------------------------------------


def test_render_qwen3_chat_prompt_single_user() -> None:
    rendered = render_qwen3_chat_prompt([{"role": "user", "content": "hi"}])
    assert rendered == "<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\n"
    # MUST NOT inject a <think> tag — the model emits it.
    assert "<think>" not in rendered


def test_render_qwen3_chat_prompt_system_and_user() -> None:
    rendered = render_qwen3_chat_prompt(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
    )
    assert rendered == (
        "<|im_start|>system\nS<|im_end|>\n"
        "<|im_start|>user\nU<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def test_answer_budget_floor_and_remainder() -> None:
    assert answer_budget_for(_item(think_budget=8192, max_tokens=16384), 8192) == 8192
    # Floor protects the answer phase when the budget eats the whole cap.
    assert answer_budget_for(_item(think_budget=16000, max_tokens=16384), 16000) == 1024


# --- two-pass forcing -------------------------------------------------------


def _forcing_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://local")


class _FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[dict[str, JsonValue]] = []

    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        **kwargs: bool,
    ) -> str:
        self.calls.append(
            {
                "messages": [dict(message) for message in conversation],
                "tokenize": tokenize,
                "add_generation_prompt": add_generation_prompt,
                "kwargs": kwargs,
            },
        )
        return f"rendered-{len(self.calls)}"


@pytest.mark.parametrize("activation", ["qwen3", "r1"])
def test_hf_renderer_leaves_qwen3_and_r1_activation_to_template(activation: str) -> None:
    tokenizer = _FakeTokenizer()
    renderer = HfChatPromptRenderer(tokenizer=tokenizer, activation=activation)

    rendered = renderer.render([{"role": "user", "content": "hi"}])

    assert rendered == "rendered-1"
    assert tokenizer.calls == [
        {
            "messages": [{"role": "user", "content": "hi"}],
            "tokenize": False,
            "add_generation_prompt": True,
            "kwargs": {},
        },
    ]


def test_hf_renderer_passes_granite_thinking_activation_kwarg() -> None:
    tokenizer = _FakeTokenizer()
    renderer = HfChatPromptRenderer(tokenizer=tokenizer, activation="granite")

    renderer.render([{"role": "user", "content": "hi"}])

    assert tokenizer.calls[0]["kwargs"] == {"thinking": True}


def test_hf_renderer_prepends_nemotron_system_message_when_absent() -> None:
    tokenizer = _FakeTokenizer()
    renderer = HfChatPromptRenderer(tokenizer=tokenizer, activation="nemotron")

    renderer.render([{"role": "user", "content": "hi"}])

    assert tokenizer.calls[0]["messages"] == [
        {"role": "system", "content": "detailed thinking on"},
        {"role": "user", "content": "hi"},
    ]
    assert tokenizer.calls[0]["kwargs"] == {}


def test_hf_renderer_does_not_duplicate_existing_nemotron_system_message() -> None:
    tokenizer = _FakeTokenizer()
    renderer = HfChatPromptRenderer(tokenizer=tokenizer, activation="nemotron")

    renderer.render(
        [{"role": "system", "content": "custom"}, {"role": "user", "content": "hi"}],
    )

    assert tokenizer.calls[0]["messages"] == [
        {"role": "system", "content": "custom"},
        {"role": "user", "content": "hi"},
    ]


def test_hf_renderer_caches_repeated_message_rendering() -> None:
    tokenizer = _FakeTokenizer()
    renderer = HfChatPromptRenderer(tokenizer=tokenizer, activation="granite")
    messages = [{"role": "user", "content": "hi"}]

    first = renderer.render(messages)
    second = renderer.render([{"role": "user", "content": "hi"}])

    assert first == second == "rendered-1"
    assert len(tokenizer.calls) == 1


def test_forced_when_thinking_exceeds_budget() -> None:
    async def scenario() -> None:
        seen: list[dict] = []
        expected_prompt = render_qwen3_chat_prompt(_item()["messages"])

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            seen.append(body)
            assert request.url.path == "/v1/completions"  # raw completions, never chat
            if body["stop"] == ["</think>"]:
                # Pass 1: model thinks past the budget, never closes </think>.
                assert body["max_tokens"] == 8192
                assert body["prompt"] == expected_prompt
                return httpx.Response(200, json=_completion(
                    "<think>\nlong reasoning", "length", prompt_tokens=10, completion_tokens=8192))
            # Pass 2: forced close, generate the answer.
            assert body["stop"] == ["<|im_end|>"]
            assert "</think>" in body["prompt"]
            assert body["max_tokens"] == 16384 - 8192
            return httpx.Response(200, json=_completion(
                "Answer: C", "stop", prompt_tokens=20, completion_tokens=5))

        async with _forcing_client(handler) as client:
            result = await run_forced_item(
                client=client,
                base_url="http://local/v1",
                headers={},
                model="qwen",
                item=_item(),
                semaphore=asyncio.Semaphore(1),
                max_attempts=3,
                backoff_base=0.0,
            )

        assert len(seen) == 2
        assert result["response_text"] == "Answer: C"
        assert result["reasoning_text"] == "<think>\nlong reasoning"
        assert result["finish_reason"] == "stop"  # the answer completed
        assert result["thinking_forced"] is True
        assert result["error"] is None
        # usage is summed across both passes
        assert result["usage"] == {"prompt_tokens": 30, "completion_tokens": 8197, "total_tokens": 8227}

    asyncio.run(scenario())


def test_forced_item_uses_configured_hf_renderer() -> None:
    async def scenario() -> None:
        tokenizer = _FakeTokenizer()
        renderer = HfChatPromptRenderer(tokenizer=tokenizer, activation="granite")
        seen_prompts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            seen_prompts.append(body["prompt"])
            if body["stop"] == ["</think>"]:
                return httpx.Response(200, json=_completion(
                    "<think>\ncustom reasoning", "length", prompt_tokens=10, completion_tokens=8192))
            return httpx.Response(200, json=_completion(
                "Answer: B", "stop", prompt_tokens=20, completion_tokens=5))

        async with _forcing_client(handler) as client:
            result = await run_forced_item(
                client=client,
                base_url="http://local/v1",
                headers={},
                model="granite",
                item=_item(),
                semaphore=asyncio.Semaphore(1),
                max_attempts=3,
                backoff_base=0.0,
                prompt_renderer=renderer,
            )

        assert seen_prompts[0] == "rendered-1"
        assert seen_prompts[1].startswith("rendered-1<think>\ncustom reasoning\n</think>")
        assert len(tokenizer.calls) == 1
        assert result["response_text"] == "Answer: B"

    asyncio.run(scenario())


def test_not_forced_when_thinking_closes_within_budget() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["stop"] == ["</think>"]:
                # Pass 1 closes </think> within budget -> finish_reason stop -> NOT forced.
                return httpx.Response(200, json=_completion(
                    "<think>\nshort", "stop", prompt_tokens=10, completion_tokens=40))
            return httpx.Response(200, json=_completion(
                "Answer: B", "stop", prompt_tokens=15, completion_tokens=4))

        async with _forcing_client(handler) as client:
            result = await run_forced_item(
                client=client, base_url="http://local/v1", headers={}, model="qwen",
                item=_item(), semaphore=asyncio.Semaphore(1), max_attempts=3, backoff_base=0.0)

        assert result["response_text"] == "Answer: B"
        assert result["thinking_forced"] is False
        assert result["finish_reason"] == "stop"

    asyncio.run(scenario())


def test_answer_truncation_reports_length_finish() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["stop"] == ["</think>"]:
                return httpx.Response(200, json=_completion(
                    "<think>\nx", "length", prompt_tokens=10, completion_tokens=8192))
            # Pass 2 itself runs out of tokens -> the answer is truncated.
            return httpx.Response(200, json=_completion(
                "The answer is", "length", prompt_tokens=20, completion_tokens=8192))

        async with _forcing_client(handler) as client:
            result = await run_forced_item(
                client=client, base_url="http://local/v1", headers={}, model="qwen",
                item=_item(), semaphore=asyncio.Semaphore(1), max_attempts=3, backoff_base=0.0)

        assert result["finish_reason"] == "length"
        assert result["thinking_forced"] is True

    asyncio.run(scenario())


def test_im_end_is_stripped_from_the_answer() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["stop"] == ["</think>"]:
                return httpx.Response(200, json=_completion(
                    "<think>\nx", "length", prompt_tokens=1, completion_tokens=1))
            return httpx.Response(200, json=_completion(
                "Answer: D<|im_end|>", "stop", prompt_tokens=1, completion_tokens=1))

        async with _forcing_client(handler) as client:
            result = await run_forced_item(
                client=client, base_url="http://local/v1", headers={}, model="qwen",
                item=_item(), semaphore=asyncio.Semaphore(1), max_attempts=3, backoff_base=0.0)

        assert result["response_text"] == "Answer: D"

    asyncio.run(scenario())


def test_re_reasoning_in_answer_pass_is_scrubbed_from_scored_text() -> None:
    # After the forced close a small model sometimes reasons more, emits its OWN </think>,
    # then answers. Only the text after that final </think> is the scored answer; the rest
    # folds back into reasoning_text so it never trips the leaked-CoT conformance gate.
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["stop"] == ["</think>"]:
                return httpx.Response(200, json=_completion(
                    "<think>\nbudget hit", "length", prompt_tokens=10, completion_tokens=8192))
            return httpx.Response(200, json=_completion(
                "more reasoning, points to F.\n</think>\n\nAnswer: F", "stop",
                prompt_tokens=20, completion_tokens=30))

        async with _forcing_client(handler) as client:
            result = await run_forced_item(
                client=client, base_url="http://local/v1", headers={}, model="qwen",
                item=_item(), semaphore=asyncio.Semaphore(1), max_attempts=3, backoff_base=0.0)

        assert result["response_text"] == "Answer: F"  # scrubbed: no </think> in scored text
        assert "</think>" not in result["response_text"]
        assert "more reasoning" in (result["reasoning_text"] or "")  # folded into the transcript
        assert result["thinking_forced"] is True

    asyncio.run(scenario())


def test_retryable_status_is_retried_then_errors() -> None:
    async def scenario() -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(503, text="overloaded")

        async with _forcing_client(handler) as client:
            result = await run_forced_item(
                client=client, base_url="http://local/v1", headers={}, model="qwen",
                item=_item(), semaphore=asyncio.Semaphore(1), max_attempts=3, backoff_base=0.0)

        assert calls["n"] == 3  # retried up to max_attempts on the think pass
        assert result["error"] is not None
        assert "503" in result["error"]

    asyncio.run(scenario())


# --- routing through run_benchmark -----------------------------------------


def test_run_benchmark_routes_local_capped_thinking_to_forcing() -> None:
    async def scenario() -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            body = json.loads(request.content)
            if body.get("stop") == ["</think>"]:
                return httpx.Response(200, json=_completion(
                    "<think>\nr", "length", prompt_tokens=5, completion_tokens=8192))
            return httpx.Response(200, json=_completion(
                "Answer: A", "stop", prompt_tokens=6, completion_tokens=3))

        record = await run_benchmark(
            base_url="http://local/v1", model="qwen", items=[_item()],
            lane="capped-thinking", transport=httpx.MockTransport(handler))

        assert paths == ["/v1/completions", "/v1/completions"]  # both passes, never chat
        result = record["results"][0]
        assert result["response_text"] == "Answer: A"
        assert result["thinking_forced"] is True

    asyncio.run(scenario())


def test_run_benchmark_answer_only_uses_chat_path_unchanged() -> None:
    async def scenario() -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "Answer: A"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}})

        record = await run_benchmark(
            base_url="http://local/v1", model="qwen", items=[_item()],
            lane="answer-only", transport=httpx.MockTransport(handler))

        assert paths == ["/v1/chat/completions"]  # single normal pass, no forcing
        assert record["results"][0]["response_text"] == "Answer: A"
        assert record["results"][0]["thinking_forced"] is False

    asyncio.run(scenario())


def test_capped_thinking_without_think_budget_uses_chat_path() -> None:
    async def scenario() -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "Answer: A"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}})

        record = await run_benchmark(
            base_url="http://local/v1", model="qwen", items=[_item(think_budget=None)],
            lane="capped-thinking", transport=httpx.MockTransport(handler))

        assert paths == ["/v1/chat/completions"]  # no think_budget -> no forcing

    asyncio.run(scenario())


# --- conformance + manifest interaction ------------------------------------


def test_forced_but_answered_run_is_headline_comparable() -> None:
    # A forced run produces non-empty response_text, a distinct reasoning_text, and
    # finish_reason "stop" -> the existing conformance gate must pass it.
    forced = [
        {"id": "x", "response_text": "Answer: A", "reasoning_text": "<think>...", "finish_reason": "stop"}
        for _ in range(50)
    ]
    report = assess_conformance(forced)
    assert report.status == "headline-comparable"
    assert report.no_final_answer_rate == 0.0
    assert report.truncation_rate == 0.0


def test_manifest_caps_records_thinking_budget() -> None:
    assert _caps({}, CAPPED_THINKING_THINK_BUDGET)["thinking_budget"] == 8192
    assert _caps({}, 0)["thinking_budget"] == 0
    # default keeps the old (no-forcing) behaviour
    assert _caps({})["thinking_budget"] == 0
