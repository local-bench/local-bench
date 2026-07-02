from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from localbench.orchestrate import OrchestrateConfig, UnsafeResumeError, run_localbench
from localbench.serving.fingerprint import server_fingerprint
from localbench.serving.provenance import (
    DETERMINISM_POLICY_ID,
    apply_serving_context,
    serving_context,
)
from serving_helpers import answer_a_handler, normalized_record, serving_evidence

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def test_serving_context_applies_block_policy_and_trust_tier(tmp_path: Path) -> None:
    # Given: complete pinned serving evidence and a normalized result bundle.
    evidence = serving_evidence(tmp_path, teardown_terminated=True)
    context = serving_context(evidence)
    record = normalized_record()

    # When: attaching serving provenance to the bundle.
    updated = apply_serving_context(record, context)

    # Then: the serving block, determinism policy object, and earned tier are present.
    assert updated["serving"]["verification_level"] == "orchestrated-pinned-artifacts-v1"
    assert updated["trust_tier"] == "orchestrated-pinned-artifacts-v1"
    assert updated["serving_verification_level"] == "orchestrated-pinned-artifacts-v1"
    assert updated["manifest"]["sampling"]["determinism_policy"]["policy_id"] == DETERMINISM_POLICY_ID
    assert updated["manifest"]["integrity"]["publishable"] is True
    assert updated["serving"]["resolved_runtime"]["reasoning"] == {
        "mode": "off",
        "budget": None,
        "format": "deepseek",
    }


def test_serving_context_degrades_when_teardown_is_uncertain(tmp_path: Path) -> None:
    # Given: otherwise complete evidence with a residual GPU PID after teardown.
    evidence = serving_evidence(tmp_path, teardown_terminated=False)

    # When: computing the serving context.
    context = serving_context(evidence)

    # Then: the run is publish-blocked and does not earn pinned-artifact trust.
    assert context.verification_level == "orchestrated-process-v1"
    assert context.trust_tier == "orchestrated-process-v1"
    assert context.publishable is False
    assert "serving.teardown_uncertain" in context.blocking_reasons


def test_run_localbench_refuses_resume_when_server_fingerprint_changes(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a campaign initialized with one server fingerprint.
        output_path = tmp_path / "campaign" / "localbench-run.json"
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
                server_fingerprint="fingerprint-a",
                serve_fingerprint={"server_fingerprint": "fingerprint-a"},
            ),
            transport=httpx.MockTransport(answer_a_handler),
        )
        output_path.unlink()

        # When / Then: resuming with a different fingerprint fails before new model calls.
        with pytest.raises(UnsafeResumeError, match="server_fingerprint"):
            await run_localbench(
                OrchestrateConfig(
                    endpoint="http://local/v1",
                    model="demo-model",
                    suite_dir=FIXTURE_SUITE,
                    bench="mmlu_pro",
                    max_items=1,
                    out=output_path,
                    resume=tmp_path / "campaign",
                    server_fingerprint="fingerprint-b",
                    serve_fingerprint={"server_fingerprint": "fingerprint-b"},
                ),
                transport=httpx.MockTransport(answer_a_handler),
            )

    asyncio.run(scenario())


def test_run_localbench_resume_segment_carries_server_fingerprint(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a completed campaign with a stable server fingerprint.
        output_path = tmp_path / "campaign" / "localbench-run.json"
        await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
                server_fingerprint="fingerprint-a",
                serve_fingerprint={"server_fingerprint": "fingerprint-a"},
            ),
            transport=httpx.MockTransport(answer_a_handler),
        )
        output_path.unlink()

        # When: resuming with the same fingerprint.
        resumed = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
                resume=tmp_path / "campaign",
                server_fingerprint="fingerprint-a",
                serve_fingerprint={"server_fingerprint": "fingerprint-a"},
            ),
            transport=httpx.MockTransport(answer_a_handler),
        )

        # Then: the resumed segment records the real fingerprint, not None.
        assert resumed["segments"][0]["server_fingerprint"] == "fingerprint-a"

    asyncio.run(scenario())


def test_server_fingerprint_hashes_artifact_runtime_argv_env_and_runtime_props() -> None:
    # Given: every score-relevant server fingerprint input.
    fingerprint = server_fingerprint(
        model_file_sha256="m" * 64,
        executable_sha256="e" * 64,
        argv=["llama-server.exe", "--parallel", "1"],
        env_allowlist={"CUDA_VISIBLE_DEVICES": "0"},
        ctx=32768,
        kv_cache_quant="k=f16,v=f16",
        parallel_slots=1,
        flash_attention="on",
        chat_template_digest="c" * 64,
    )

    # Then: the fingerprint is a sha256 hex digest over the canonical inputs.
    assert len(fingerprint) == 64
    assert fingerprint == server_fingerprint(
        model_file_sha256="m" * 64,
        executable_sha256="e" * 64,
        argv=["llama-server.exe", "--parallel", "1"],
        env_allowlist={"CUDA_VISIBLE_DEVICES": "0"},
        ctx=32768,
        kv_cache_quant="k=f16,v=f16",
        parallel_slots=1,
        flash_attention="on",
        chat_template_digest="c" * 64,
    )
