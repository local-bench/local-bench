"""Tests for the async OpenAI-compatible benchmark runner."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from localbench.runner import run_benchmark, write_json


def test_run_benchmark_when_request_succeeds() -> None:
    async def scenario() -> None:
        # Given an OpenAI-compatible endpoint that returns usage.
        seen_payloads = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payloads.append(json.loads(request.content))
            assert request.headers["authorization"] == "Bearer sk-test"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "Answer: C"},
                            "finish_reason": "stop",
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 3,
                        "total_tokens": 10,
                    },
                },
            )

        transport = httpx.MockTransport(handler)

        # When running one benchmark item.
        record = await run_benchmark(
            base_url="http://local/v1",
            api_key="sk-test",
            model="demo-model",
            items=[
                {
                    "id": "item-1",
                    "messages": [{"role": "user", "content": "Pick C"}],
                    "sampling_params": {"temperature": 0},
                    "max_tokens": 16,
                },
            ],
            transport=transport,
        )

        # Then the response and totals are captured.
        result = record["results"][0]
        assert seen_payloads == [
            {
                "model": "demo-model",
                "messages": [{"role": "user", "content": "Pick C"}],
                "temperature": 0,
                "max_tokens": 16,
            },
        ]
        assert result["response_text"] == "Answer: C"
        assert result["finish_reason"] == "stop"
        assert result["usage"] == {
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "total_tokens": 10,
        }
        assert result["error"] is None
        assert result["latency_seconds"] >= 0
        assert record["totals"]["items"] == 1
        assert record["totals"]["errors"] == 0
        assert record["totals"]["completion_tokens"] == 3
        assert record["totals"]["completion_tokens_per_second"] >= 0

    asyncio.run(scenario())


def test_run_benchmark_when_retryable_status_succeeds_later() -> None:
    async def scenario() -> None:
        # Given an endpoint that returns 429 before succeeding.
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, json={"error": "busy"})
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "done"},
                            "finish_reason": "stop",
                        },
                    ],
                    "usage": {"completion_tokens": 2},
                },
            )

        # When running with zero retry delay.
        record = await run_benchmark(
            base_url="http://local/v1/",
            api_key=None,
            model="demo-model",
            items=[
                {
                    "id": "item-1",
                    "messages": [{"role": "user", "content": "run"}],
                    "sampling_params": {},
                    "max_tokens": 4,
                },
            ],
            transport=httpx.MockTransport(handler),
            backoff_base=0,
        )

        # Then the item succeeds after a retry.
        assert attempts == 2
        assert record["results"][0]["response_text"] == "done"
        assert record["results"][0]["attempts"] == 2
        assert record["results"][0]["error"] is None

    asyncio.run(scenario())


def test_run_benchmark_when_hard_failure_records_item_error() -> None:
    async def scenario() -> None:
        # Given an endpoint returning a non-retryable client error.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="bad request")

        # When running the benchmark.
        record = await run_benchmark(
            base_url="http://local/v1",
            api_key=None,
            model="demo-model",
            items=[
                {
                    "id": "bad-item",
                    "messages": [{"role": "user", "content": "run"}],
                    "sampling_params": {},
                    "max_tokens": 4,
                },
            ],
            transport=httpx.MockTransport(handler),
        )

        # Then the error is recorded without raising.
        result = record["results"][0]
        assert result["response_text"] is None
        assert result["error"] == "HTTP 400: bad request"
        assert result["attempts"] == 1
        assert record["totals"]["errors"] == 1

    asyncio.run(scenario())


def test_run_benchmark_when_many_items_respects_concurrency_limit() -> None:
    async def scenario() -> None:
        # Given an endpoint that tracks overlapping requests.
        active = 0
        max_active = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "ok"},
                            "finish_reason": "stop",
                        },
                    ],
                    "usage": {"completion_tokens": 1},
                },
            )

        items = [
            {
                "id": f"item-{index}",
                "messages": [{"role": "user", "content": "run"}],
                "sampling_params": {},
                "max_tokens": 4,
            }
            for index in range(8)
        ]

        # When running with concurrency two.
        record = await run_benchmark(
            base_url="http://local/v1",
            api_key=None,
            model="demo-model",
            items=items,
            concurrency=2,
            transport=httpx.MockTransport(handler),
        )

        # Then no more than two requests overlap.
        assert max_active == 2
        assert record["totals"]["items"] == 8
        assert record["totals"]["errors"] == 0

    asyncio.run(scenario())


def test_run_benchmark_when_usage_is_missing_tolerates_response() -> None:
    async def scenario() -> None:
        # Given an endpoint that omits token usage.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "ok"},
                            "finish_reason": "length",
                        },
                    ],
                },
            )

        # When running the benchmark.
        record = await run_benchmark(
            base_url="http://local/v1",
            api_key=None,
            model="demo-model",
            items=[
                {
                    "id": "item-1",
                    "messages": [{"role": "user", "content": "run"}],
                    "sampling_params": {},
                    "max_tokens": 4,
                },
            ],
            transport=httpx.MockTransport(handler),
        )

        # Then usage fields are present as unknown values and totals treat them as zero.
        assert record["results"][0]["usage"] == {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
        assert record["totals"]["prompt_tokens"] == 0
        assert record["totals"]["completion_tokens"] == 0
        assert record["totals"]["total_tokens"] == 0

    asyncio.run(scenario())


def test_write_json_when_given_run_record(tmp_path: Path) -> None:
    # Given a small run record and an output path.
    record = {"run": {"id": "test"}, "results": []}
    output_path = tmp_path / "run.json"

    # When writing JSON.
    write_json(record, output_path)

    # Then the file contains formatted JSON.
    assert json.loads(output_path.read_text(encoding="utf-8")) == record
