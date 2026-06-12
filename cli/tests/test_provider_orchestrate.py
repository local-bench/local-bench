from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from localbench.orchestrate import OrchestrateConfig, run_localbench

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_run_localbench_when_openai_reasoning_provider_records_manifest_notes(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        # Given an OpenAI reasoning provider run through the real orchestrator path.
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "gpt-5-anchor"}]})
            payload = json.loads(request.content)
            captured.append(payload)
            assert "max_completion_tokens" in payload
            assert "max_tokens" not in payload
            assert "temperature" not in payload
            assert "chat_template_kwargs" not in payload
            return _completion("Answer: A", 5, 3)

        # When running one item with the explicit reasoning provider.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="https://api.openai.com/v1",
                model="gpt-5-anchor",
                suite_dir=FIXTURE_SUITE,
                out=tmp_path / "openai_reasoning.json",
                provider="openai-reasoning",
                max_items=1,
            ),
            transport=httpx.MockTransport(handler),
        )

        # Then provider formatting and manifest metadata are observable.
        assert captured
        assert record["manifest"]["endpoint"]["provider"] == "openai-reasoning"
        assert record["manifest"]["endpoint"]["api_provider"] == "openai-reasoning"
        assert record["manifest"]["endpoint"]["divergence_notes"] == [
            "greedy not enforceable; provider-default sampling",
        ]

    asyncio.run(scenario())


def _completion(text: str, prompt_tokens: int, completion_tokens: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": text},
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )
