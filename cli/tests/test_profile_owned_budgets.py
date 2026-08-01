from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx

from localbench.bounded_final_profiles import (
    BoundedFinalProfileRuntime,
    resolve_bounded_final_profile_from_introspection,
)
from localbench.bounded_final_forcing import run_bounded_final_forced_item
from localbench.orchestrate import _budget_audit
from localbench.prompt_rendering import TemplateIntrospection
from localbench.runner import run_benchmark


class _Renderer:
    def render(self, messages: list[dict[str, str]]) -> str:
        return "rendered-prompt"


_FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"
_BASE_SUITE_JSON_SHA256 = "6556314dc6111e595435209a793436955bac2e29c143dcd6bfe1164b74ea3430"
_BASE_MMLU_PRO_QUICK_SHA256 = "685cfe3985469d26eecff4fc4a0aaa6c31e1f1a0f070a86074c9b388119ac0ac"


def test_auto_generic_thinking_resolves_to_the_32768_profile() -> None:
    # Given: a canonical template with native generic thinking support.
    introspection = TemplateIntrospection(
        answer_stop=("<|im_end|>",),
        chat_template_kwargs={"enable_thinking": True},
        supports_generic_thinking=True,
        supports_gemma_channel=False,
    )

    # When: the bounded-final auto profile is resolved.
    runtime = resolve_bounded_final_profile_from_introspection("auto", introspection)

    # Then: ranked generic thinking uses the current 32k operating point.
    assert runtime.entry.id == "generic_think_tags_32768_v1"
    assert runtime.contract.budget.static_think_tokens == 32768
    assert runtime.contract.budget.static_final_tokens == 16384
    assert runtime.contract.budget.static_max_generated_tokens == 49152


def test_32768_profile_owns_request_caps_and_audit_promise() -> None:
    # Given: a resolved generic-thinking profile and an unchanged suite item cap.
    runtime = resolve_bounded_final_profile_from_introspection(
        "generic_think_tags_32768_v1",
        TemplateIntrospection(
            answer_stop=("<|im_end|>",),
            chat_template_kwargs={"enable_thinking": True},
            supports_generic_thinking=True,
            supports_gemma_channel=False,
        ),
    )
    request_caps: list[int] = []

    async def scenario() -> dict[str, object]:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            request_caps.append(body["max_tokens"])
            return httpx.Response(
                200,
                json={
                    "choices": [{"text": "Answer: A", "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await run_bounded_final_forced_item(
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
                execution_contract=runtime.contract,
            )
        return result

    # When: the two-pass request is sent under the resolved contract.
    result = asyncio.run(scenario())
    audit = _budget_audit(
        [
            {
                "bench": "mmlu_pro",
                "id": "item-1",
                "max_tokens": result["max_tokens"],
                "generated_tokens": {"total": 2},
            }
        ],
    )

    # Then: profile limits replace the suite item's legacy static budget.
    assert request_caps == [32768, 16384]
    assert audit["per_bench"]["mmlu_pro"]["max_promised_total"] == 49152


def test_release_profile_budgets_preserve_suite_and_8192_control() -> None:
    # Given: the frozen suite bytes and both selectable generic-thinking profiles.
    current = resolve_bounded_final_profile_from_introspection(
        "generic_think_tags_32768_v1",
        TemplateIntrospection(
            answer_stop=("<|im_end|>",),
            chat_template_kwargs={"enable_thinking": True},
            supports_generic_thinking=True,
            supports_gemma_channel=False,
        ),
    )
    legacy = resolve_bounded_final_profile_from_introspection(
        "generic_think_tags_8192_v1",
        TemplateIntrospection(
            answer_stop=("<|im_end|>",),
            chat_template_kwargs={"enable_thinking": True},
            supports_generic_thinking=True,
            supports_gemma_channel=False,
        ),
    )
    current_trace: list[int] = []
    legacy_trace: list[int] = []
    legacy_request_bytes: list[bytes] = []

    async def forced_trace(
        runtime: BoundedFinalProfileRuntime,
        traces: list[int],
        item_cap: int,
        request_bytes: list[bytes] | None = None,
    ) -> dict[str, object]:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            traces.append(body["max_tokens"])
            if request_bytes is not None:
                request_bytes.append(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [{"text": "reasoning", "finish_reason": "length"}],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": body["max_tokens"],
                        "total_tokens": body["max_tokens"] + 1,
                    },
                },
            )

        record = await run_benchmark(
            base_url="http://local/v1",
            model="demo",
            items=[
                {
                    "id": "item-1",
                    "messages": [{"role": "user", "content": "test"}],
                    "sampling_params": {},
                    "max_tokens": item_cap,
                    "think_budget": 8192,
                }
            ],
            lane="bounded-final-v1",
            transport=httpx.MockTransport(handler),
            prompt_renderer=_Renderer(),
            forcing_format=runtime.forcing,
        )
        return record["results"][0]

    async def scenario() -> tuple[dict[str, object], dict[str, object]]:
        return (
            await forced_trace(current, current_trace, 16384),
            await forced_trace(legacy, legacy_trace, 16384, legacy_request_bytes),
        )

    # When: the profile-owned and explicit legacy paths execute their forced requests.
    current_result, legacy_result = asyncio.run(scenario())
    audit = _budget_audit(
        [
            {
                "bench": "mmlu_pro",
                "id": "item-1",
                "max_tokens": current_result["max_tokens"],
                "generated_tokens": {"total": 2},
            }
        ],
    )

    # Then: the suite remains byte-stable, current caps are 32k/16k, and legacy stays 8k/8k.
    assert (
        hashlib.sha256((_FIXTURE_SUITE / "suite.json").read_bytes()).hexdigest()
        == _BASE_SUITE_JSON_SHA256
    )
    assert hashlib.sha256(
        (_FIXTURE_SUITE / "mmlu_pro_quick.jsonl").read_bytes(),
    ).hexdigest() == _BASE_MMLU_PRO_QUICK_SHA256
    assert current_trace == [32768, 16384]
    assert audit["per_bench"]["mmlu_pro"]["max_promised_total"] == 49152
    assert legacy_trace == [8192, 8192]
    assert legacy_request_bytes == [
        b'{"model":"demo","prompt":"rendered-prompt","max_tokens":8192,"stop":["</think>"]}',
        b'{"model":"demo","prompt":"rendered-promptreasoning\\n</think>\\n\\n","max_tokens":8192,"stop":["<|im_end|>"]}',
    ]
    assert legacy_result["max_tokens"] == 16384
