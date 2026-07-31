from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from localbench.bounded_final_profiles import resolve_bounded_final_profile_from_introspection
from localbench.orchestrate import OrchestrateConfig, run_localbench
from localbench.prompt_rendering import TemplateIntrospection
from test_orchestrate_agentic import (
    _SUITE_DIR,
    _agentic_resume_seed,
    _fake_appworld_sandbox_factory,
    _v1_agentic_weight_handler,
)


def test_inline_agentic_loop_config_uses_campaign_run_identifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the inline agentic rerun seam is captured before executing the sandbox.
    import localbench.scoring.agentic_exec.funnel as funnel_mod
    from localbench.scoring.agentic_exec import scripted_agent as sa

    captured: dict[str, object] = {}

    class CapturedLoopConfig(Exception):
        pass

    def capture_config(**kwargs: object) -> object:
        captured["config"] = kwargs["config"]
        raise CapturedLoopConfig()

    monkeypatch.setattr(funnel_mod, "run_with_reruns", capture_config)

    async def scenario() -> None:
        with pytest.raises(CapturedLoopConfig):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=_SUITE_DIR,
                    tier="standard",
                    out=tmp_path / "agentic-run.json",
                    max_items=1,
                ),
                transport=httpx.MockTransport(_v1_agentic_weight_handler),
                agentic_sandbox_factory=_fake_appworld_sandbox_factory,
                agentic_model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
                agentic_task_ids=["fac291d_1"],
                agentic_canonical_task_ids=["fac291d_1"],
                agentic_resume_seed=_agentic_resume_seed(),
            )

    # When: the orchestrator constructs LoopConfig for the agentic campaign.
    asyncio.run(scenario())

    # Then: attestations bind to the real campaign/run identifier, not the old constant.
    config = captured["config"]
    assert config.attestation_run_id == "agentic-run"


def test_32768_contract_drives_loop_config_at_campaign_activation_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the resolved 32k execution contract and the real campaign activation seam.
    import localbench.scoring.agentic_exec.funnel as funnel_mod
    from localbench.scoring.agentic_exec import scripted_agent as sa

    runtime = resolve_bounded_final_profile_from_introspection(
        "generic_think_tags_32768_v1",
        TemplateIntrospection(
            answer_stop=("<|im_end|>",),
            chat_template_kwargs={"enable_thinking": True},
            supports_generic_thinking=True,
            supports_gemma_channel=False,
        ),
    )
    captured: dict[str, object] = {}

    class CapturedLoopConfig(Exception):
        pass

    def capture_config(**kwargs: object) -> object:
        captured["config"] = kwargs["config"]
        raise CapturedLoopConfig()

    monkeypatch.setattr(funnel_mod, "run_with_reruns", capture_config)

    async def scenario() -> None:
        with pytest.raises(CapturedLoopConfig):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=_SUITE_DIR,
                    tier="standard",
                    out=tmp_path / "agentic-32k.json",
                    max_items=1,
                    resolved_bounded_profile=runtime,
                ),
                transport=httpx.MockTransport(_v1_agentic_weight_handler),
                agentic_sandbox_factory=_fake_appworld_sandbox_factory,
                agentic_model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
                agentic_task_ids=["fac291d_1"],
                agentic_canonical_task_ids=["fac291d_1"],
                agentic_resume_seed=_agentic_resume_seed(),
            )

    # When: orchestration activates the agentic campaign worker.
    asyncio.run(scenario())

    # Then: all five loop budgets are the resolved contract tuple, with no legacy shadow.
    config = captured["config"]
    assert config.max_turns == 40
    assert config.max_output_tokens_per_turn == 1024
    assert config.max_generated_tokens_per_task == 65536
    assert config.context_window == 32768
    assert config.per_task_timeout_s == 3000
