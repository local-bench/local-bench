from __future__ import annotations

import asyncio
from pathlib import Path
from typing import NoReturn

import pytest

from localbench._types import JsonObject
from localbench.bounded_final_profiles import (
    BoundedFinalProfileChoice,
    BoundedFinalProfileRuntime,
)
from localbench.serving import runner as serving_runner
from localbench.serving.llama_cpp import BuildIdentity
from localbench.serving.model_artifact import ModelArtifact
from localbench.serving.options import ServeBenchOptions
from localbench.serving.readiness import ReadinessEvidence
from localbench.serving.teardown import RecordedProcessIdentity, TeardownEvidence


class _StopAfterProbe(RuntimeError):
    pass


class _FakeProcess:
    pid = 1234
    returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


class _FakeLaunch:
    process = _FakeProcess()
    job = object()
    job_handle = 1
    log_start_byte = 0
    identity = RecordedProcessIdentity(
        pid=1234,
        executable_path="C:/llama/llama-server.exe",
        commandline_sha256="c" * 64,
        process_birth_token="birth-token",
    )

    def close_log(self) -> None:
        return


def _build_identity() -> BuildIdentity:
    return BuildIdentity(
        executable_sha256="e" * 64,
        dll_or_so_hashes={"ggml-cuda.dll": "d" * 64},
        version_stdout="llama.cpp b9852 fd1a05791",
        source_repo="ggml-org/llama.cpp",
        source_commit="fd1a05791",
        source_tag="b9852",
        build_flags="cuda",
        help_text_sha256="h" * 64,
        help_text="",
        list_devices_stdout="CUDA0",
        cuda_version="12.4",
    )


async def _readiness(
    *,
    base_url: str,
    model_id: str,
    model_file: Path,
    api_key: str,
    seed: int,
) -> ReadinessEvidence:
    return ReadinessEvidence(
        health_200_at="2026-08-01T00:00:00Z",
        models_response_sha256="m" * 64,
        props_response_sha256="p" * 64,
        reported_model=model_id,
        smoke_chat_sha256="s" * 64,
        tokenize_sha256="t" * 64,
        apply_template_sha256="a" * 64,
        total_slots=1,
        model_path=str(model_file),
        chat_template="{{messages}}",
        build_info="llama.cpp b9852 fd1a05791",
    )


def _stop_after_probe(
    **_kwargs: str | int | bool | list[str] | dict[str, str] | JsonObject | None,
) -> NoReturn:
    raise _StopAfterProbe


def capacity_probe_calls_for_profile(
    runtime: BoundedFinalProfileRuntime,
    profile: BoundedFinalProfileChoice,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    server = tmp_path / "llama-server.exe"
    server.write_text("fake", encoding="utf-8")
    artifact = ModelArtifact(
        model_file=model,
        file_sha256="0" * 64,
        file_size_bytes=4,
        gguf_metadata_sha256="1" * 64,
        tokenizer_digest="2" * 64,
        chat_template_digest="3" * 64,
        gguf_metadata_path=tmp_path / "metadata.json",
        model_family="gemma",
        quant_label="Q4_K_M",
    )
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=model,
        model_ref=None,
        model_id="gemma",
        server_bin=server,
        ctx=65536,
        determinism="strict",
        tier="standard",
        bench="mmlu_pro",
        lane="bounded-final-v1",
        seed=1234,
        profile=profile,
        out=tmp_path / profile,
    )
    capacity_calls: list[int] = []

    async def record_capacity(
        *,
        base_url: str,
        api_key: str,
        required_context_tokens: int,
        run_dir: Path,
        serve_log_path: Path,
        serve_log_start_byte: int,
        server_identity: RecordedProcessIdentity,
        launch_argv: list[str],
    ) -> JsonObject:
        capacity_calls.append(required_context_tokens)
        return {"passed": True}

    monkeypatch.setattr(serving_runner, "preflight_agentic_if_needed", lambda *_args: None)
    monkeypatch.setattr(serving_runner, "resolve_artifact", lambda *_args: artifact)
    monkeypatch.setattr(serving_runner, "allocate_port", lambda: 49152)
    monkeypatch.setattr(
        serving_runner,
        "resolve_serving_execution_profile",
        lambda *_args, **_kwargs: runtime,
    )
    monkeypatch.setattr(serving_runner, "validate_capped_thinking_context", lambda *_args: None)
    monkeypatch.setattr(serving_runner, "server_bin", lambda _options: server)
    monkeypatch.setattr(serving_runner, "collect_build_identity", lambda _binary: _build_identity())
    monkeypatch.setattr(serving_runner, "strict_llama_cpp_argv", lambda _config: [str(server)])
    monkeypatch.setattr(serving_runner, "reconcile_agent_isolation", lambda argv, _help: argv)
    monkeypatch.setattr(serving_runner, "validate_strict_argv_supported", lambda *_args: None)
    monkeypatch.setattr(serving_runner, "server_fingerprint", lambda **_kwargs: "fingerprint")
    monkeypatch.setattr(serving_runner, "launch_llama_cpp", lambda *_args, **_kwargs: _FakeLaunch())
    monkeypatch.setattr(serving_runner, "verify_llama_cpp_readiness", _readiness)
    monkeypatch.setattr(serving_runner, "verify_llama_cpp_capacity", record_capacity)
    monkeypatch.setattr(serving_runner, "resume_identity", _stop_after_probe)
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

    with pytest.raises(_StopAfterProbe):
        asyncio.run(serving_runner.run_orchestrated_bench(options))
    return capacity_calls
