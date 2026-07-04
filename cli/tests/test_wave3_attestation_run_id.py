from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from localbench.orchestrate import OrchestrateConfig, run_localbench
from test_orchestrate_agentic import (
    _SUITE_DIR,
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
            )

    # When: the orchestrator constructs LoopConfig for the agentic campaign.
    asyncio.run(scenario())

    # Then: attestations bind to the real campaign/run identifier, not the old constant.
    config = captured["config"]
    assert config.attestation_run_id == "agentic-run"
