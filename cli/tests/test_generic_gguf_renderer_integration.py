from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gguf_renderer_integration_support import (
    EXPECTED_INITIAL_PROMPT,
    FakeLaunch,
    LlamaStub,
    QWOPUS_TEMPLATE_TAIL,
    write_suite,
)
from localbench import cli as cli_mod
from localbench.execution_contract import structured_execution_profile
from localbench.orchestrate import OrchestrateConfig
from localbench.serving import runner as serving_runner
from localbench.serving.llama_cpp import BuildIdentity
from localbench.serving.model_artifact import ModelArtifact
from localbench.serving.readiness import ReadinessEvidence
from localbench.serving.teardown import TeardownEvidence
from localbench.submissions.canon import sha256_file


def test_public_cli_generic_gguf_runs_server_renderer_and_forced_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite_dir = write_suite(tmp_path / "suite")
    model = tmp_path / "qwopus.Q5_K_M.gguf"
    model.write_bytes(b"hermetic gguf artifact")
    server_bin = tmp_path / "llama-server.exe"
    server_bin.write_bytes(b"hermetic server")
    metadata_path = tmp_path / "gguf_metadata.json"
    metadata = {
        "tokenizer.chat_template": QWOPUS_TEMPLATE_TAIL,
        "tokenizer.ggml.eos_token_id": 0,
        "tokenizer.ggml.tokens": ["<|im_end|>"],
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    artifact = ModelArtifact(
        model_file=model,
        file_sha256=sha256_file(model),
        file_size_bytes=model.stat().st_size,
        gguf_metadata_sha256=sha256_file(metadata_path),
        tokenizer_digest="2" * 64,
        chat_template_digest=hashlib.sha256(
            QWOPUS_TEMPLATE_TAIL.encode("utf-8"),
        ).hexdigest(),
        gguf_metadata_path=metadata_path,
        model_family="qwen3",
        quant_label="Q5_K_M",
    )
    captured_profiles = []
    real_run_localbench = serving_runner.run_localbench

    async def capture_profile(config: OrchestrateConfig, **kwargs):
        profile = config.resolved_bounded_profile
        assert profile is not None
        assert profile.prompt_renderer is not None
        captured_profiles.append(profile)
        return await real_run_localbench(config, **kwargs)

    with LlamaStub() as stub:
        monkeypatch.setattr(cli_mod, "_preflight_execution_contract", lambda: None)
        monkeypatch.setattr(
            serving_runner,
            "resolve_artifact",
            lambda _options, _root: artifact,
        )
        monkeypatch.setattr(serving_runner, "allocate_port", lambda: stub.port)
        monkeypatch.setattr(
            serving_runner,
            "collect_build_identity",
            lambda _binary: _build_identity(),
        )
        monkeypatch.setattr(
            serving_runner,
            "validate_strict_argv_supported",
            lambda _argv, _help: None,
        )
        monkeypatch.setattr(
            serving_runner,
            "launch_llama_cpp",
            lambda _argv, *, cwd, log_path: FakeLaunch(),
        )
        monkeypatch.setattr(
            serving_runner,
            "verify_llama_cpp_readiness",
            _fake_readiness,
        )
        monkeypatch.setattr(
            serving_runner,
            "teardown_owned_server",
            lambda **_kwargs: TeardownEvidence(
                owned_process_tree=["1234"],
                terminated=True,
                exit_code=0,
                gpu_pids_after=[],
                teardown_uncertain=False,
            ),
        )
        monkeypatch.setattr(serving_runner, "run_localbench", capture_profile)
        out_dir = tmp_path / "run"
        exit_code = cli_mod.main(_cli_args(model, server_bin, suite_dir, out_dir))

    assert exit_code == 0
    assert len(captured_profiles) == 1
    contract = captured_profiles[0].contract
    assert contract.prompt_renderer_engine == "llama.cpp/apply-template"
    assert len(stub.completion_requests) == 2
    first, continuation = stub.completion_requests
    assert first["prompt"] == EXPECTED_INITIAL_PROMPT
    assert first["max_tokens"] == 32_768
    assert continuation["prompt"] == (
        EXPECTED_INITIAL_PROMPT + "reasoning tokens\n</think>\n\n"
    )
    assert continuation["max_tokens"] == 16_384
    assert all(
        value is not None and value.startswith("Bearer ")
        for value in stub.authorizations
    )
    record = json.loads(
        (out_dir / "localbench-run.json").read_text(encoding="utf-8"),
    )
    campaign = json.loads((out_dir / "campaign.json").read_text(encoding="utf-8"))
    campaign_contract = campaign["execution_profile"]
    manifest_profile = record["manifest"]["execution_profile"]
    assert campaign_contract["id"] == manifest_profile["id"]
    assert campaign_contract["selection_policy_id"] == manifest_profile["selection_policy_id"]
    assert campaign_contract["selection_reason"] == manifest_profile["selection_reason"]
    assert campaign_contract["chat_template_kwargs"] == manifest_profile["chat_template_kwargs"]
    assert campaign_contract["answer_stops"] == manifest_profile["answer_stops"]
    assert structured_execution_profile(manifest_profile) == manifest_profile
    assert record["manifest"]["suite"]["caps"]["thinking_budget"] == 32_768
    assert record["serving"]["resolved_runtime"]["reasoning"]["budget"] == 32_768


def _cli_args(
    model: Path,
    server_bin: Path,
    suite_dir: Path,
    out_dir: Path,
) -> list[str]:
    return [
        "bench",
        "--runtime",
        "llama.cpp",
        "--model-file",
        str(model),
        "--model-id",
        "qwopus",
        "--server-bin",
        str(server_bin),
        "--ctx",
        "32768",
        "--determinism",
        "strict",
        "--tier",
        "quick",
        "--bench",
        "mmlu_pro",
        "--lane",
        "bounded-final-v1",
        "--profile",
        "auto",
        "--gguf-repo-only",
        "--seed",
        "1234",
        "--max-items",
        "1",
        "--suite-dir",
        str(suite_dir),
        "--out",
        str(out_dir),
        "--no-submit",
        "--accept-suite-terms",
    ]


def _build_identity() -> BuildIdentity:
    return BuildIdentity(
        executable_sha256="e" * 64,
        dll_or_so_hashes={"ggml-cuda.dll": "d" * 64},
        version_stdout="llama.cpp b10076 305ba519a",
        source_repo="ggml-org/llama.cpp",
        source_commit="305ba519a",
        source_tag="b10076",
        build_flags="cuda",
        help_text_sha256="h" * 64,
        help_text="",
        list_devices_stdout="CUDA0",
        cuda_version="12.4",
    )


async def _fake_readiness(
    **_kwargs: str | int | Path,
) -> ReadinessEvidence:
    return ReadinessEvidence(
        health_200_at="2026-07-30T00:00:00Z",
        models_response_sha256="m" * 64,
        props_response_sha256="p" * 64,
        reported_model="qwopus",
        smoke_chat_sha256="s" * 64,
        tokenize_sha256="t" * 64,
        apply_template_sha256="a" * 64,
        total_slots=1,
        model_path="qwopus.Q5_K_M.gguf",
        chat_template=QWOPUS_TEMPLATE_TAIL,
        build_info="llama.cpp b10076 305ba519a",
    )
