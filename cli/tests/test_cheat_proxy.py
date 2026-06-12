"""Tests for the adversarial cheat proxy attack harness."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from attack.cheat_proxy import CheatProxy, CheatProxyConfig
from localbench.orchestrate import OrchestrateConfig, run_localbench


FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_answer_injection_returns_gold_when_prompt_matches_fixture_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a cheat proxy loaded with the public fixture suite.
    proxy = CheatProxy.from_suite_dir(
        FIXTURE_SUITE,
        CheatProxyConfig(claimed_model="potato-7b-q2", fake_tok_s=35.0),
    )
    delays: list[float] = []
    monkeypatch.setattr(proxy, "delay", delays.append)

    # When known MCQ and genmath prompts are submitted.
    mcq = proxy.chat_completion(
        {
            "model": "ignored",
            "messages": [{"role": "user", "content": "Choose B."}],
        },
    )
    genmath = proxy.chat_completion(
        {
            "model": "ignored",
            "messages": [{"role": "user", "content": "Compute 10 / 2."}],
        },
    )

    # Then the proxy injects the public gold answers and calculates fake timing.
    mcq_text = _completion_text(mcq)
    genmath_text = _completion_text(genmath)
    assert "Answer: B" in mcq_text
    assert genmath_text.rstrip().endswith("5")
    assert len(delays) == 2
    assert all(delay > 0 for delay in delays)


def test_run_localbench_scores_near_perfect_when_using_in_process_proxy(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        # Given the orchestrator is pointed at an in-process cheat proxy transport.
        proxy = CheatProxy.from_suite_dir(
            FIXTURE_SUITE,
            CheatProxyConfig(claimed_model="potato-7b-q2", fake_tok_s=0.0),
        )

        # When localbench runs the fixture suite through that transport.
        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://cheat-proxy.test/v1",
                model="potato-7b-q2",
                suite_dir=FIXTURE_SUITE,
                out=tmp_path / "attack-run.json",
            ),
            transport=httpx.MockTransport(proxy.handle_httpx_request),
        )

        # Then server-side transcript scoring accepts the injected MCQ/genmath answers.
        assert record["manifest"]["endpoint"]["runtime_reported_model"] == "potato-7b-q2"
        assert record["benches"]["mmlu_pro"]["raw_accuracy"] == 1.0
        assert record["benches"]["genmath"]["raw_accuracy"] == 1.0
        assert record["benches"]["mmlu_pro"]["n_extraction_failures"] == 0
        assert record["benches"]["genmath"]["n_extraction_failures"] == 0
        assert (
            record["benches"]["mmlu_pro"]["chance_corrected"]
            + record["benches"]["genmath"]["chance_corrected"]
        ) / 2 == 1.0

    asyncio.run(scenario())


def _completion_text(response: dict[str, object]) -> str:
    choices = response["choices"]
    assert isinstance(choices, list)
    first_choice = choices[0]
    assert isinstance(first_choice, dict)
    message = first_choice["message"]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, str)
    return content
