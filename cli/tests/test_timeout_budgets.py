from __future__ import annotations

import asyncio
import json
from types import MappingProxyType

import httpx

from localbench._types import ChatMessage
from localbench.bounded_final_forcing import _bounded_final_two_pass
from localbench.budget_forcing import QWEN_FORCING
from localbench.execution_contract import ResolvedExecutionContract
from localbench.reasoning_registry import GENERIC_THINK_TAGS_32768_PROFILE
from localbench.runner import run_benchmark
from localbench.scoring.agentic_exec.chat_client import ChatCompletionsClient
from localbench.scoring.agentic_exec.model_client import GenerationParams
from localbench.timeout_budgets import (
    AGENTIC_CAMPAIGN_MAX_RUNS,
    HTTP_CONNECT_TIMEOUT_S,
    HTTP_POOL_TIMEOUT_S,
    HTTP_READ_FINALIZE_RESERVE_S,
    HTTP_WRITE_TIMEOUT_S,
    STATIC_ITEM_FINALIZE_RESERVE_S,
    STATIC_REQUEST_MAX_ATTEMPTS,
    derive_timeout_budget,
)


def _contract() -> ResolvedExecutionContract:
    return ResolvedExecutionContract(
        profile_id=GENERIC_THINK_TAGS_32768_PROFILE.id,
        selection_policy_id="fixture",
        selection_reason="fixture",
        template_source="fixture",
        raw_template_sha256=None,
        effective_template_sha256=None,
        chat_template_kwargs=MappingProxyType({"enable_thinking": True}),
        answer_stops=(),
        reasoning_mode="generic_think",
        reasoning_budget=32768,
        model_file_sha256="a" * 64,
        runtime_probe=None,
        prompt_renderer_engine="fixture",
        prompt_renderer_contract_version="fixture",
        prompt_renderer_context_sha256="b" * 64,
        budget=GENERIC_THINK_TAGS_32768_PROFILE.budget,
    )


def test_timeout_budget_uses_ceiling_generation_and_named_reserves() -> None:
    # Given: the resolved 32k execution-profile budget and one remaining static item.
    budget = GENERIC_THINK_TAGS_32768_PROFILE.budget

    # When: timeout bounds are derived at the supported throughput floor.
    derived = derive_timeout_budget(budget, remaining_static_items=1, remaining_agentic_tasks=0)

    # Then: the 32k generation allowance is ceil(32768 / 10), before explicit reserves.
    assert derived.generation_seconds(32768) == 3277
    assert derived.request_read_seconds(32768) == 3277 + HTTP_READ_FINALIZE_RESERVE_S
    assert derived.connect_seconds == HTTP_CONNECT_TIMEOUT_S
    assert derived.write_seconds == HTTP_WRITE_TIMEOUT_S
    assert derived.pool_seconds == HTTP_POOL_TIMEOUT_S
    assert derived.provenance == "profile-derived-10-tokens-per-second"
    assert derived.static_item_seconds == (
        STATIC_REQUEST_MAX_ATTEMPTS
        * (
            derived.request_read_seconds(32768)
            + derived.request_read_seconds(16384)
        )
        + STATIC_ITEM_FINALIZE_RESERVE_S
    )
    assert derived.campaign_seconds < 24 * 60 * 60

    agentic = derive_timeout_budget(
        budget,
        remaining_static_items=0,
        remaining_agentic_tasks=2,
    )
    assert agentic.campaign_seconds >= (
        2 * budget.per_task_timeout_s * AGENTIC_CAMPAIGN_MAX_RUNS
    )


def test_static_request_passes_profile_derived_split_timeout_to_http_transport() -> None:
    async def scenario() -> None:
        captured: list[dict[str, float]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(dict(request.extensions["timeout"]))
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        # Given: an actual 32768-token request under the resolved deep profile.
        item = {
            "id": "timeout-boundary",
            "messages": [{"role": "user", "content": "answer"}],
            "sampling_params": {"temperature": 0},
            "max_tokens": 32768,
        }

        # When: the runner reaches the real HTTP transport boundary.
        await run_benchmark(
            base_url="http://local/v1",
            model="fixture",
            items=[item],
            concurrency=1,
            max_attempts=1,
            transport=httpx.MockTransport(handler),
            execution_contract=_contract(),
        )

        # Then: connect/write/pool stay small and read covers ceil(32768/10) plus finalize.
        assert captured == [
            {
                "connect": HTTP_CONNECT_TIMEOUT_S,
                "read": 3277 + HTTP_READ_FINALIZE_RESERVE_S,
                "write": HTTP_WRITE_TIMEOUT_S,
                "pool": HTTP_POOL_TIMEOUT_S,
            },
        ]

    asyncio.run(scenario())


def test_legacy_request_keeps_the_explicit_caller_timeout() -> None:
    async def scenario() -> None:
        captured: list[dict[str, float]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(dict(request.extensions["timeout"]))
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        # Given: genuine legacy construction with no resolved execution budget.
        # When: a request crosses the transport with the caller's frozen timeout.
        await run_benchmark(
            base_url="http://local/v1",
            model="fixture",
            items=[
                {
                    "id": "legacy-timeout",
                    "messages": [{"role": "user", "content": "answer"}],
                    "sampling_params": {"temperature": 0},
                    "max_tokens": 16,
                },
            ],
            timeout=123.0,
            concurrency=1,
            max_attempts=1,
            transport=httpx.MockTransport(handler),
        )

        # Then: T6 does not reinterpret frozen legacy timeout behavior.
        assert captured == [
            {"connect": 123.0, "read": 123.0, "write": 123.0, "pool": 123.0},
        ]

    asyncio.run(scenario())


def test_resolved_agentic_client_derives_implicit_task_deadline_without_legacy_shadow(
    monkeypatch,
) -> None:
    captured: list[float | None] = []
    budget = derive_timeout_budget(
        GENERIC_THINK_TAGS_32768_PROFILE.budget,
        remaining_static_items=0,
        remaining_agentic_tasks=1,
    )

    class CapturingClient(ChatCompletionsClient):
        def _post(self, payload: dict[str, object]) -> tuple[int, str]:
            captured.append(self._attempt_timeout_s)
            return 200, json.dumps(
                {
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"completion_tokens": 1},
                },
            )

    # Given: a resolved-profile client with no benchmark-injected task deadline.
    monkeypatch.setattr("localbench.scoring.agentic_exec.chat_client.time.monotonic", lambda: 100.0)
    client = CapturingClient("http://local", "fixture", timeout_budget=budget)

    # When: the first per-turn request establishes its implicit task transport deadline.
    response = client.complete(
        [ChatMessage(role="user", content="answer")],
        GenerationParams(max_output_tokens=1024),
    )

    # Then: the task gets the profile's 3000s less the named 180s finalize/teardown reserve,
    # while the request remains bounded to the 133s token-derived turn allowance.
    assert response.text == "ok"
    assert client._deadline == 100.0 + 2820.0
    assert captured == [budget.request_read_seconds(1024)]


def test_legacy_agentic_client_retains_implicit_1620_second_transport_budget(monkeypatch) -> None:
    # Given: genuine legacy construction without a resolved timeout budget.
    monkeypatch.setattr("localbench.scoring.agentic_exec.chat_client.time.monotonic", lambda: 100.0)
    client = ChatCompletionsClient("http://local", "fixture")

    # When: the client establishes its implicit task transport deadline.
    remaining = client._remaining_transport_s()

    # Then: the frozen legacy 1800s watchdog less its 180s reserve remains unchanged.
    assert remaining == 1620.0
    assert client._deadline == 1720.0


def test_bounded_two_pass_uses_each_actual_pass_maximum_at_transport() -> None:
    async def scenario() -> None:
        captured: list[tuple[int, dict[str, float]]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            captured.append((payload["max_tokens"], dict(request.extensions["timeout"])))
            return httpx.Response(
                200,
                json={
                    "choices": [{"text": "done", "finish_reason": "stop"}],
                    "usage": {"completion_tokens": 1},
                },
            )

        derived = derive_timeout_budget(
            GENERIC_THINK_TAGS_32768_PROFILE.budget,
            remaining_static_items=1,
            remaining_agentic_tasks=0,
        )

        # Given: the profile-owned 32768-token think and 16384-token final passes.
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            # When: both requests cross the actual completions transport.
            await _bounded_final_two_pass(
                client=client,
                url="http://local/v1/completions",
                headers={},
                model="fixture",
                prompt="prompt",
                decoding={},
                total_cap=49152,
                think_budget=32768,
                static_final_tokens=16384,
                forcing_format=QWEN_FORCING,
                timeout_budget=derived,
            )

        # Then: neither pass inherits the client's default and each uses its own token maximum.
        assert captured == [
            (
                32768,
                {
                    "connect": HTTP_CONNECT_TIMEOUT_S,
                    "read": derived.request_read_seconds(32768),
                    "write": HTTP_WRITE_TIMEOUT_S,
                    "pool": HTTP_POOL_TIMEOUT_S,
                },
            ),
            (
                16384,
                {
                    "connect": HTTP_CONNECT_TIMEOUT_S,
                    "read": derived.request_read_seconds(16384),
                    "write": HTTP_WRITE_TIMEOUT_S,
                    "pool": HTTP_POOL_TIMEOUT_S,
                },
            ),
        ]

    asyncio.run(scenario())
