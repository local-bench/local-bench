from __future__ import annotations

import json
from typing import Final

import httpx
import pytest

from localbench._types import BenchmarkItem, JsonObject
from localbench.bounded_final_profiles import (
    BoundedFinalProfileChoice,
    BoundedFinalProfileRequest,
    BoundedFinalProfileRuntime,
    resolve_bounded_final_profile,
)
from localbench.orchestrate import (
    _agentic_chat_template_kwargs_for_profile,
    _local_chat_template_kwargs,
)
from localbench.runner import run_benchmark
from localbench.scoring.agentic_exec.chat_client import ChatCompletionsClient
from localbench.scoring.agentic_exec.model_client import GenerationParams
from localbench.serving.agentic_support import agentic_chat_template_kwargs

_MODEL_SHA: Final = "a" * 64
_STOP: Final = "<|im_end|>"


def _runtime(
    control: str,
    profile: BoundedFinalProfileChoice,
) -> BoundedFinalProfileRuntime:
    metadata: JsonObject = {
        "tokenizer.chat_template": (
            f"{{% if {control} %}}<think>{{% endif %}}{_STOP}"
        ),
        "tokenizer.ggml.eos_token_id": 0,
        "tokenizer.ggml.tokens": [_STOP],
    }
    return resolve_bounded_final_profile(
        BoundedFinalProfileRequest(
            profile=profile,
            hf_model_id=None,
            model_file_sha256=_MODEL_SHA,
            gguf_metadata=metadata,
            gguf_repo_only=True,
        )
    )


@pytest.mark.parametrize(
    ("control", "profile", "expected"),
    [
        ("enable_thinking", "auto", {"enable_thinking": True}),
        ("thinking", "auto", {"thinking": True}),
        ("enable_thinking", "answer_only_v1", {"enable_thinking": False}),
        ("thinking", "answer_only_v1", {"thinking": False}),
    ],
)
@pytest.mark.anyio
async def test_contract_kwargs_reach_static_tool_and_agentic_request_bodies(
    control: str,
    profile: BoundedFinalProfileChoice,
    expected: dict[str, bool],
) -> None:
    # Given: Qwen- or Granite-style template controls resolved to one contract.
    runtime = _runtime(control, profile)
    captured: list[JsonObject] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert isinstance(payload, dict)
        captured.append(payload)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    static_item: BenchmarkItem = {
        "id": "static",
        "messages": [{"role": "user", "content": "static prompt"}],
        "sampling_params": {
            "max_tokens": 1,
            "chat_template_kwargs": _local_chat_template_kwargs(
                "bounded-final-v1",
                runtime,
            ),
        },
    }
    tool_item: BenchmarkItem = {
        "id": "tool",
        "messages": [{"role": "user", "content": "tool prompt"}],
        "sampling_params": {
            "max_tokens": 1,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "chat_template_kwargs": _local_chat_template_kwargs(
                "bounded-final-v1",
                runtime,
            ),
        },
    }

    # When: static, tool, and agentic request builders consume that contract.
    await run_benchmark(
        base_url="http://local/v1",
        model="fixture",
        items=[static_item, tool_item],
        concurrency=1,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
        lane="bounded-final-v1",
    )
    orchestrated_kwargs = _agentic_chat_template_kwargs_for_profile(
        "bounded-final-v1",
        runtime.contract,
    )
    serving_kwargs = agentic_chat_template_kwargs(
        "bounded-final-v1",
        runtime.contract,
    )
    client = ChatCompletionsClient(
        "http://local/v1",
        "fixture",
        chat_template_kwargs=serving_kwargs,
    )
    agentic_payload = client._build_payload(
        [{"role": "user", "content": "agentic prompt"}],
        GenerationParams(max_output_tokens=1),
    )

    # Then: every final body carries the exact key and boolean from the contract.
    assert runtime.contract.chat_template_kwargs == expected
    assert len(captured) == 2
    assert all(payload["chat_template_kwargs"] == expected for payload in captured)
    assert captured[0].get("tools") is None
    assert isinstance(captured[1].get("tools"), list)
    assert orchestrated_kwargs == expected
    assert serving_kwargs == expected
    assert agentic_payload["chat_template_kwargs"] == expected
