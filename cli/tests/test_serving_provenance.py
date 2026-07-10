from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest

from localbench.orchestrate import OrchestrateConfig, UnsafeResumeError, run_localbench
from localbench.persistence import atomic_write_json
from localbench.serving.assembly import precheck_resume_identity
from localbench.serving.fingerprint import (
    normalize_ephemeral_argv,
    resume_identity,
    server_fingerprint,
)
from localbench.serving.provenance import (
    DETERMINISM_POLICY_ID,
    apply_serving_context,
    serving_context,
)
from serving_helpers import answer_a_handler, normalized_record, serving_evidence

FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"
BASE_ARGV = ["llama-server.exe", "--model", "model.gguf", "--port", "55419", "--parallel", "1"]
CURRENT_ARGV = ["llama-server.exe", "--model", "model.gguf", "--port", "60000", "--parallel", "1"]
ENV_ALLOWLIST = {"CUDA_VISIBLE_DEVICES": "0"}
MODEL_HASH = "m" * 64
EXE_HASH = "e" * 64
CHAT_TEMPLATE_DIGEST = "c" * 64
CTX = 32768
KV_CACHE_QUANT = "k=f16,v=f16"
PARALLEL_SLOTS = 1
FLASH_ATTENTION = "on"


def test_serving_context_applies_block_policy_and_trust_tier(tmp_path: Path) -> None:
    # Given: complete pinned serving evidence and a normalized result bundle.
    evidence = serving_evidence(tmp_path, teardown_terminated=True)
    serve_log = Path(evidence.serve_log_path)
    serve_log.parent.mkdir(parents=True, exist_ok=True)
    serve_log.write_bytes(b"local-only server log")
    context = serving_context(evidence)
    record = normalized_record()

    # When: attaching serving provenance to the bundle.
    updated = apply_serving_context(record, context)

    # Then: the serving block, determinism policy object, and earned tier are present.
    assert updated["serving"]["verification_level"] == "orchestrated-pinned-artifacts-v1"
    assert updated["serving"]["trust_tier"] == "orchestrated-pinned-artifacts-v1"
    assert "trust_tier" not in updated
    assert "serving_verification_level" not in updated
    assert updated["manifest"]["sampling"]["determinism_policy"]["policy_id"] == DETERMINISM_POLICY_ID
    assert updated["manifest"]["integrity"]["publishable"] is True
    assert updated["serving"]["resolved_runtime"]["reasoning"] == {
        "mode": "off",
        "budget": None,
        "format": "deepseek",
    }
    assert "serve_log_path" not in updated["serving"]
    assert updated["serving"]["serve_log_sha256"] == hashlib.sha256(
        b"local-only server log",
    ).hexdigest()


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


def test_normalize_ephemeral_argv_masks_only_port_token() -> None:
    # Given: a redacted launch argv with one ephemeral --port value.
    argv = [
        "llama-server.exe",
        "--port",
        "55419",
        "--api-key",
        "***REDACTED***",
        "--parallel",
        "1",
    ]

    # When: normalizing argv for resume identity.
    normalized = normalize_ephemeral_argv(argv)

    # Then: only the port token changes, the input is not mutated, and the operation is idempotent.
    assert normalized == [
        "llama-server.exe",
        "--port",
        "<EPHEMERAL>",
        "--api-key",
        "***REDACTED***",
        "--parallel",
        "1",
    ]
    assert argv[2] == "55419"
    assert normalize_ephemeral_argv(normalized) == normalized
    assert normalize_ephemeral_argv(["llama-server.exe", "--parallel", "1"]) == [
        "llama-server.exe",
        "--parallel",
        "1",
    ]


def test_resume_identity_ignores_only_ephemeral_port() -> None:
    # Given: two launch argvs that differ only by the allocated port.
    identity = _resume_identity(BASE_ARGV)

    # Then: port-only changes are stable, while provenance and non-port flag changes are not.
    assert identity == _resume_identity(CURRENT_ARGV)
    assert identity != _resume_identity(CURRENT_ARGV, model_file_sha256="x" * 64)
    assert identity != _resume_identity(CURRENT_ARGV, executable_sha256="x" * 64)
    assert identity != _resume_identity(CURRENT_ARGV, chat_template_digest="x" * 64)
    assert identity != _resume_identity(CURRENT_ARGV, ctx=65536)
    assert identity != _resume_identity(
        ["llama-server.exe", "--model", "other.gguf", "--port", "60000", "--parallel", "1"],
    )


def test_precheck_resume_identity_passes_new_record_with_port_only_change(tmp_path: Path) -> None:
    # Given: a campaign recorded with a resume identity derived from a previous ephemeral port.
    resume_dir = _write_campaign(
        tmp_path,
        {
            "resume_identity": _resume_identity(BASE_ARGV),
            "server_fingerprint": "recorded-exact-fingerprint",
        },
    )

    # When / Then: a current launch with a different port but same identity is allowed.
    precheck_resume_identity(resume_dir, _resume_identity(CURRENT_ARGV), **_precheck_inputs())


def test_precheck_resume_identity_refuses_new_record_binary_hash_change(tmp_path: Path) -> None:
    # Given: a campaign recorded with one binary hash in its resume identity.
    resume_dir = _write_campaign(tmp_path, {"resume_identity": _resume_identity(BASE_ARGV)})

    # When / Then: a current launch with a different binary hash is refused.
    with pytest.raises(RuntimeError, match="unsafe resume refused: resume identity changed"):
        precheck_resume_identity(
            resume_dir,
            _resume_identity(CURRENT_ARGV, executable_sha256="x" * 64),
            **_precheck_inputs(),
        )


def test_precheck_resume_identity_backfills_legacy_record_with_port_only_change(
    tmp_path: Path,
) -> None:
    # Given: a legacy serve_fingerprint shaped like the live canary record, without resume_identity.
    resume_dir = _write_campaign(tmp_path, _legacy_serve_fingerprint())

    # When / Then: the recorded identity is reconstructed with the port masked and matches.
    precheck_resume_identity(resume_dir, _resume_identity(CURRENT_ARGV), **_precheck_inputs())


@pytest.mark.parametrize(
    "field",
    ["server_command_redacted", "server_binary_hash", "model_artifact_hash", "context_length"],
)
def test_precheck_resume_identity_refuses_legacy_record_missing_reconstruction_field(
    tmp_path: Path,
    field: str,
) -> None:
    # Given: a legacy serve_fingerprint missing a field required to reconstruct identity.
    serve = _legacy_serve_fingerprint()
    del serve[field]
    resume_dir = _write_campaign(tmp_path, serve)

    # When / Then: the precheck fails closed instead of guessing.
    with pytest.raises(
        RuntimeError,
        match=f"unsafe resume refused: campaign.json serve_fingerprint is missing {field}",
    ):
        precheck_resume_identity(resume_dir, _resume_identity(CURRENT_ARGV), **_precheck_inputs())


def test_precheck_resume_identity_refuses_legacy_record_model_hash_mismatch(tmp_path: Path) -> None:
    # Given: a legacy campaign whose recorded model artifact hash differs from the current launch.
    serve = _legacy_serve_fingerprint()
    serve["model_artifact_hash"] = "x" * 64
    resume_dir = _write_campaign(tmp_path, serve)

    # When / Then: reconstructing the recorded identity diverges and resume is refused.
    with pytest.raises(RuntimeError, match="unsafe resume refused: resume identity changed"):
        precheck_resume_identity(resume_dir, _resume_identity(CURRENT_ARGV), **_precheck_inputs())


def test_precheck_resume_identity_refuses_missing_serve_fingerprint_section(tmp_path: Path) -> None:
    # Given: a campaign without the serving resume-gate section.
    resume_dir = tmp_path / "campaign"
    resume_dir.mkdir()
    atomic_write_json({}, resume_dir / "campaign.json")

    # When / Then: serve-mode resume fails closed.
    with pytest.raises(RuntimeError, match="unsafe resume refused: campaign.json serve_fingerprint"):
        precheck_resume_identity(resume_dir, _resume_identity(CURRENT_ARGV), **_precheck_inputs())


def test_run_localbench_refuses_resume_when_resume_identity_changes(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: a campaign initialized with one resume identity.
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
                resume_identity="identity-a",
                serve_fingerprint={
                    "server_fingerprint": "fingerprint-a",
                    "resume_identity": "identity-a",
                },
            ),
            transport=httpx.MockTransport(answer_a_handler),
        )
        output_path.unlink()

        # When / Then: resuming with a different identity fails before new model calls.
        with pytest.raises(UnsafeResumeError, match="resume_identity"):
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
                    resume_identity="identity-b",
                    serve_fingerprint={
                        "server_fingerprint": "fingerprint-b",
                        "resume_identity": "identity-b",
                    },
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
                resume_identity="identity-a",
                serve_fingerprint={
                    "server_fingerprint": "fingerprint-a",
                    "resume_identity": "identity-a",
                },
            ),
            transport=httpx.MockTransport(answer_a_handler),
        )
        output_path.unlink()

        # When: resuming with the same identity but a new per-launch exact fingerprint.
        resumed = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
                resume=tmp_path / "campaign",
                server_fingerprint="fingerprint-b",
                resume_identity="identity-a",
                serve_fingerprint={
                    "server_fingerprint": "fingerprint-b",
                    "resume_identity": "identity-a",
                },
            ),
            transport=httpx.MockTransport(answer_a_handler),
        )

        # Then: the current resumed segment records the exact fingerprint, not the identity.
        assert [segment["segment_id"] for segment in resumed["segments"]] == ["segment-1", "segment-2"]
        assert resumed["segments"][-1]["server_fingerprint"] == "fingerprint-b"

    asyncio.run(scenario())


def test_run_localbench_skips_legacy_missing_resume_identity_at_orchestrate_gate(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        # Given: a legacy campaign with no recorded resume_identity.
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

        # When: orchestrate sees only the current resume_identity because the recorded key is absent.
        resumed = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=FIXTURE_SUITE,
                bench="mmlu_pro",
                max_items=1,
                out=output_path,
                resume=tmp_path / "campaign",
                server_fingerprint="fingerprint-b",
                resume_identity="identity-b",
                serve_fingerprint={
                    "server_fingerprint": "fingerprint-b",
                    "resume_identity": "identity-b",
                },
            ),
            transport=httpx.MockTransport(answer_a_handler),
        )

        # Then: this gate skips legacy records; serve-mode resumes are fail-closed earlier.
        assert [segment["segment_id"] for segment in resumed["segments"]] == ["segment-1", "segment-2"]
        assert resumed["segments"][-1]["server_fingerprint"] == "fingerprint-b"

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


def _resume_identity(
    argv: list[str],
    *,
    model_file_sha256: str = MODEL_HASH,
    executable_sha256: str = EXE_HASH,
    ctx: int = CTX,
    chat_template_digest: str = CHAT_TEMPLATE_DIGEST,
) -> str:
    return resume_identity(
        model_file_sha256=model_file_sha256,
        executable_sha256=executable_sha256,
        argv=argv,
        env_allowlist=ENV_ALLOWLIST,
        ctx=ctx,
        kv_cache_quant=KV_CACHE_QUANT,
        parallel_slots=PARALLEL_SLOTS,
        flash_attention=FLASH_ATTENTION,
        chat_template_digest=chat_template_digest,
    )


def _precheck_inputs() -> dict:
    return {
        "chat_template_digest": CHAT_TEMPLATE_DIGEST,
        "env_allowlist": ENV_ALLOWLIST,
        "kv_cache_quant": KV_CACHE_QUANT,
        "parallel_slots": PARALLEL_SLOTS,
        "flash_attention": FLASH_ATTENTION,
    }


def _legacy_serve_fingerprint() -> dict:
    return {
        "server_fingerprint": "legacy-exact-fingerprint",
        "server_command_redacted": BASE_ARGV,
        "server_binary_hash": EXE_HASH,
        "model_artifact_hash": MODEL_HASH,
        "context_length": CTX,
    }


def _write_campaign(tmp_path: Path, serve_fingerprint: dict) -> Path:
    resume_dir = tmp_path / "campaign"
    resume_dir.mkdir()
    atomic_write_json({"serve_fingerprint": serve_fingerprint}, resume_dir / "campaign.json")
    return resume_dir
