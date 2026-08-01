from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx

from localbench.bounded_final_forcing import run_bounded_final_forced_item
from localbench.bounded_final_profiles import resolve_bounded_final_profile_from_introspection
from localbench.manifest import _caps
from localbench.prompt_rendering import TemplateIntrospection
from localbench.reasoning_registry import ExecutionProfileBudget


class _Renderer:
    def render(self, messages: list[dict[str, str]]) -> str:
        return "rendered-prompt"


def _generic_runtime():
    return resolve_bounded_final_profile_from_introspection(
        "generic_think_tags_32768_v1",
        TemplateIntrospection(
            answer_stop=("<|im_end|>",),
            chat_template_kwargs={"enable_thinking": True},
            supports_generic_thinking=True,
            supports_gemma_channel=False,
        ),
    )


def test_deep_profile_contract_budget_drives_forcing_and_manifest() -> None:
    # Given: the deep profile with a contract-owned budget that differs from its registry default.
    runtime = _generic_runtime()
    budget = ExecutionProfileBudget(
        static_think_tokens=123,
        static_final_tokens=456,
        static_max_generated_tokens=579,
        server_context_tokens=65536,
        agentic_max_turns=40,
        agentic_max_output_tokens_per_turn=1024,
        agentic_max_generated_tokens_per_task=65536,
        agentic_context_tokens=32768,
        kv_cache_k_dtype="f16",
        kv_cache_v_dtype="f16",
        context_fit_policy="exact-or-fail",
        context_extension_policy="none",
        per_task_timeout_s=3000,
    )
    contract = replace(
        runtime.contract,
        reasoning_budget=budget.static_think_tokens,
        budget=budget,
    )
    request_caps: list[int] = []

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            request_caps.append(json.loads(request.content)["max_tokens"])
            return httpx.Response(
                200,
                json={
                    "choices": [{"text": "Answer: A", "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await run_bounded_final_forced_item(
                client=client,
                base_url="http://local/v1",
                headers={},
                model="demo",
                item={
                    "id": "item-1",
                    "messages": [{"role": "user", "content": "test"}],
                    "sampling_params": {},
                    "max_tokens": 16384,
                },
                semaphore=asyncio.Semaphore(1),
                max_attempts=1,
                backoff_base=0.0,
                prompt_renderer=_Renderer(),
                forcing_format=runtime.forcing,
                execution_contract=contract,
            )

    # When: request shaping and manifest construction consume the resolved contract.
    asyncio.run(scenario())

    # Then: deep-profile consumers use its resolved tuple rather than forcing-format copies.
    assert request_caps == [123, 456]
    assert _caps({}, 0, contract)["thinking_budget"] == 123


def test_32768_profile_conformance_describes_its_additive_budget() -> None:
    # Given: the new 32k generic-thinking registry profile.
    runtime = _generic_runtime()

    # When: its conformance metadata is read by a consumer.
    conformance = runtime.entry.conformance

    # Then: each static component and their additive total agree with the owned tuple.
    assert conformance["think_cap"] == 32768
    assert conformance["min_final"] == 16384
    assert conformance["think_budget"] == "32768"
    assert conformance["answer_budget"] == "16384"
    assert conformance["max_generated_tokens"] == "32768 + 16384"
