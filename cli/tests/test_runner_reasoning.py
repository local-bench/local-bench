from __future__ import annotations

import asyncio

import httpx

from localbench.runner import run_benchmark


def test_run_benchmark_when_reasoning_content_present_records_item_reasoning() -> None:
    async def scenario() -> None:
        # Given an OpenAI-compatible endpoint that separates answer content and reasoning content.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "Answer: B",
                                "reasoning_content": "Check each option.",
                            },
                            "finish_reason": "stop",
                        },
                    ],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
                },
            )

        # When running one benchmark item through the shared local provider path.
        record = await run_benchmark(
            base_url="http://local/v1",
            api_key=None,
            model="demo-model",
            items=[
                {
                    "id": "item-1",
                    "messages": [{"role": "user", "content": "Pick B"}],
                    "sampling_params": {"temperature": 0},
                    "max_tokens": 16,
                },
            ],
            transport=httpx.MockTransport(handler),
        )

        # Then the answer remains scored content and the thinking audit trail is retained.
        result = record["results"][0]
        assert result["response_text"] == "Answer: B"
        assert result["reasoning_text"] == "Check each option."
        assert result["finish_reason"] == "stop"
        assert result["error"] is None

    asyncio.run(scenario())
