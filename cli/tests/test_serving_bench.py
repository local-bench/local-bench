from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from localbench.serving import assembly
from localbench.serving.bench import BenchRunConfig, build_orchestrate_config
from localbench.serving.llama_cpp import (
    LlamaCppLaunchConfig,
    collect_build_identity,
    strict_llama_cpp_argv,
    validate_strict_argv_supported,
)
from localbench.serving.model_artifact import resolve_model_file_artifact
from localbench.serving.readiness import verify_llama_cpp_readiness
from localbench.serving.options import ServeBenchOptions
from localbench.serving.runner import run_orchestrated_bench
from localbench.cli import _parser
from serving_helpers import flag_value, minimal_gguf, serving_evidence


FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"


def _launch_config(
    tmp_path: Path,
    *,
    reasoning: str = "off",
    reasoning_budget: int | None = None,
    reasoning_format: str = "deepseek",
) -> LlamaCppLaunchConfig:
    model = tmp_path / "gemma.gguf"
    model.write_bytes(b"GGUF")
    return LlamaCppLaunchConfig(
        server_bin=Path("C:/llama/llama-server.exe"),
        model_file=model,
        model_id="gemma-4-12b-it-q4",
        host="127.0.0.1",
        port=49152,
        api_key="run-secret",
        ctx=32768,
        seed=1234,
        threads=8,
        threads_batch=8,
        run_dir=tmp_path,
        reasoning=reasoning,
        reasoning_budget=reasoning_budget,
        reasoning_format=reasoning_format,
    )


def test_llama_cpp_strict_argv_pins_score_impacting_flags(tmp_path: Path) -> None:
    # Given: a strict GGUF launch configuration.
    config = _launch_config(tmp_path)

    # When: the argv is constructed.
    argv = strict_llama_cpp_argv(config)

    # Then: every score-impacting strict-lane knob is explicit and no auto value is used.
    assert argv[:3] == [
        str(Path("C:/llama/llama-server.exe")),
        "--model",
        str(config.model_file.resolve()),
    ]
    assert flag_value(argv, "--alias") == "gemma-4-12b-it-q4"
    assert flag_value(argv, "--host") == "127.0.0.1"
    assert flag_value(argv, "--port") == "49152"
    assert flag_value(argv, "--ctx-size") == "32768"
    assert flag_value(argv, "--n-gpu-layers") == "999"
    assert flag_value(argv, "--fit") == "off"
    assert flag_value(argv, "--parallel") == "1"
    assert "--no-cont-batching" in argv
    assert flag_value(argv, "--flash-attn") == "on"
    assert flag_value(argv, "--cache-type-k") == "f16"
    assert flag_value(argv, "--cache-type-v") == "f16"
    assert "--no-context-shift" in argv
    assert flag_value(argv, "--reasoning") == "off"
    assert "--reasoning-budget" not in argv
    assert flag_value(argv, "--reasoning-format") == "deepseek"
    assert "--no-webui" in argv
    assert "--no-agent" in argv
    assert "auto" not in argv


def test_llama_cpp_strict_argv_for_capped_thinking_enables_budget(tmp_path: Path) -> None:
    # Given: the capped-thinking lane's pinned reasoning configuration.
    config = _launch_config(tmp_path, reasoning="on", reasoning_budget=8192)

    # When: the argv is constructed.
    argv = strict_llama_cpp_argv(config)

    # Then: native reasoning is enabled with the locked budget and Gemma parser.
    assert flag_value(argv, "--reasoning") == "on"
    assert flag_value(argv, "--reasoning-budget") == "8192"
    assert flag_value(argv, "--reasoning-format") == "deepseek"
    assert "auto" not in argv


def test_llama_cpp_reasoning_mapping_for_answer_only_lane() -> None:
    # Given / When: the local serving answer-only lane is mapped to llama.cpp reasoning flags.
    reasoning = assembly.llama_cpp_reasoning_for_lane("answer-only")

    # Then: thought parsing stays active while generation-level reasoning is disabled.
    assert reasoning.reasoning == "off"
    assert reasoning.reasoning_budget is None
    assert reasoning.reasoning_format == "deepseek"


def test_llama_cpp_reasoning_mapping_for_capped_thinking_lane() -> None:
    # Given / When: the local serving capped-thinking lane is mapped to llama.cpp reasoning flags.
    reasoning = assembly.llama_cpp_reasoning_for_lane("capped-thinking")

    # Then: native reasoning is enabled with the locked methodology v1.2 budget.
    assert reasoning.reasoning == "on"
    assert reasoning.reasoning_budget == 8192
    assert reasoning.reasoning_format == "deepseek"


def test_llama_cpp_reasoning_mapping_rejects_api_uncapped_lane() -> None:
    # Given / When / Then: API-uncapped is not a local llama.cpp serving lane.
    with pytest.raises(RuntimeError, match="api-uncapped.*not supported.*llama.cpp"):
        assembly.llama_cpp_reasoning_for_lane("api-uncapped")


def test_orchestrated_llama_cpp_rejects_api_uncapped_before_model_resolution(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: an api-uncapped lane request against local llama.cpp serving.
        options = ServeBenchOptions(
            runtime="llama.cpp",
            model_file=None,
            model_ref=None,
            model_id="gemma",
            server_bin=None,
            ctx=32768,
            determinism="strict",
            tier="standard",
            bench="all",
            lane="api-uncapped",
            seed=1234,
            out=tmp_path / "run",
        )

        # When / Then: lane validation fails before model or server resolution.
        with pytest.raises(RuntimeError, match="api-uncapped.*not supported.*llama.cpp"):
            await run_orchestrated_bench(options)

    asyncio.run(scenario())


def test_bench_parser_accepts_max_items_flag() -> None:
    # Given the bench subcommand's required arguments plus a real-suite item cap.
    parser = _parser()

    # When parsing the CLI surface.
    args = parser.parse_args(
        [
            "bench",
            "--runtime",
            "llama.cpp",
            "--model-file",
            "model.gguf",
            "--model-id",
            "gemma",
            "--ctx",
            "32768",
            "--seed",
            "1234",
            "--max-items",
            "10",
        ]
    )

    # Then the cap is available to the bench command.
    assert args.command == "bench"
    assert args.max_items == 10


def test_bench_parser_accepts_capped_thinking_reasoning_flags() -> None:
    # Given the bench subcommand's required arguments plus capped-thinking family flags.
    parser = _parser()

    # When parsing the CLI surface.
    args = parser.parse_args(
        [
            "bench",
            "--runtime",
            "llama.cpp",
            "--model-file",
            "model.gguf",
            "--model-id",
            "gemma",
            "--ctx",
            "32768",
            "--seed",
            "1234",
            "--lane",
            "capped-thinking",
            "--reasoning-activation",
            "gemma4",
            "--hf-model-id",
            "unsloth/gemma-4-12b-it",
        ]
    )

    # Then both values are available to the bench command.
    assert args.command == "bench"
    assert args.reasoning_activation == "gemma4"
    assert args.hf_model_id == "unsloth/gemma-4-12b-it"


def test_validate_strict_argv_supported_fails_closed_when_help_omits_required_flag(
    tmp_path: Path,
) -> None:
    # Given: an argv with a pinned flag missing from the binary help text.
    argv = strict_llama_cpp_argv(_launch_config(tmp_path))
    help_text = "\n".join(flag for flag in argv if flag.startswith("--") and flag != "--fit")

    # When / Then: support validation refuses instead of silently dropping the knob.
    with pytest.raises(RuntimeError, match="--fit"):
        validate_strict_argv_supported(argv, help_text)


def test_collect_build_identity_hashes_binary_and_adjacent_runtime_files(tmp_path: Path) -> None:
    # Given: a pinned native runtime directory and mocked identity commands.
    server = tmp_path / "llama-server.exe"
    server.write_bytes(b"server")
    (tmp_path / "ggml-cuda.dll").write_bytes(b"ggml")
    (tmp_path / "cudart64_13.dll").write_bytes(b"cuda")
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> str:
        calls.append(argv)
        if argv[-1] == "--version":
            return "llama.cpp b9852 fd1a05791 CUDA build"
        if argv[-1] == "--help":
            return "--model\n--alias\n--fit\n"
        if argv[-1] == "--list-devices":
            return "CUDA0 RTX 5090"
        raise AssertionError(argv)

    # When: collecting build identity.
    identity = collect_build_identity(server, runner=runner)

    # Then: the executable, DLLs, help text, version, source tag, and commit are captured.
    assert calls == [[str(server), "--version"], [str(server), "--help"], [str(server), "--list-devices"]]
    assert identity.executable_sha256 == hashlib.sha256(b"server").hexdigest()
    assert identity.dll_or_so_hashes == {
        "cudart64_13.dll": hashlib.sha256(b"cuda").hexdigest(),
        "ggml-cuda.dll": hashlib.sha256(b"ggml").hexdigest(),
    }
    assert identity.help_text_sha256 == hashlib.sha256(b"--model\n--alias\n--fit\n").hexdigest()
    assert identity.source_tag == "b9852"
    assert identity.source_commit == "fd1a05791"
    assert identity.list_devices_stdout == "CUDA0 RTX 5090"


def test_resolve_model_file_artifact_dumps_and_hashes_gguf_metadata(tmp_path: Path) -> None:
    # Given: a minimal GGUF with embedded model and tokenizer metadata.
    model = tmp_path / "Gemma-12B-Q4_K_M.gguf"
    model.write_bytes(minimal_gguf())

    # When: resolving the artifact first.
    artifact = resolve_model_file_artifact(model, run_dir=tmp_path / "run")

    # Then: file identity, metadata, tokenizer, and template digests are persisted.
    assert artifact.file_sha256 == hashlib.sha256(model.read_bytes()).hexdigest()
    assert artifact.file_size_bytes == model.stat().st_size
    assert artifact.model_format == "GGUF"
    assert artifact.quant_label == "Q4_K_M"
    assert artifact.model_family == "gemma"
    assert artifact.gguf_metadata_path.name == "gguf_metadata.json"
    metadata = json.loads(artifact.gguf_metadata_path.read_text(encoding="utf-8"))
    assert metadata["general.architecture"] == "gemma"
    assert artifact.gguf_metadata_sha256 == hashlib.sha256(
        artifact.gguf_metadata_path.read_bytes(),
    ).hexdigest()
    assert artifact.tokenizer_digest is not None
    assert artifact.chat_template_digest is not None


def test_readiness_records_endpoint_evidence_after_health_transition(tmp_path: Path) -> None:
    async def scenario() -> None:
        # Given: llama.cpp readiness endpoints that transition from loading to ready.
        health_statuses = [503, 200]
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path == "/health":
                return httpx.Response(health_statuses.pop(0))
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "gemma"}]})
            if request.url.path == "/props":
                return httpx.Response(
                    200,
                    json={
                        "total_slots": 1,
                        "model_path": str(tmp_path / "gemma.gguf"),
                        "chat_template": "{{messages}}",
                        "build_info": "cuda",
                    },
                )
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})
            if request.url.path == "/tokenize":
                return httpx.Response(200, json={"tokens": [1, 2]})
            if request.url.path == "/apply-template":
                return httpx.Response(200, json={"prompt": "ready"})
            return httpx.Response(404)

        # When: verifying readiness through the OpenAI-compatible surface.
        evidence = await verify_llama_cpp_readiness(
            base_url="http://local",
            model_id="gemma",
            model_file=tmp_path / "gemma.gguf",
            api_key="secret",
            seed=1234,
            transport=httpx.MockTransport(handler),
            poll_interval_seconds=0,
        )

        # Then: health, model identity, props, smoke, tokenizer, and template evidence are hashed.
        assert seen_paths == [
            "/health",
            "/health",
            "/v1/models",
            "/props",
            "/v1/chat/completions",
            "/tokenize",
            "/apply-template",
        ]
        assert evidence.reported_model == "gemma"
        assert evidence.total_slots == 1
        assert evidence.model_path == str(tmp_path / "gemma.gguf")
        assert len(evidence.models_response_sha256) == 64
        assert len(evidence.props_response_sha256) == 64
        assert len(evidence.smoke_chat_sha256) == 64

    asyncio.run(scenario())


def test_bench_orchestrate_config_forces_strict_local_lane(tmp_path: Path) -> None:
    # Given: fully resolved serving evidence for a bench-managed llama.cpp run.
    evidence = serving_evidence(tmp_path, teardown_terminated=True)
    config = BenchRunConfig(
        endpoint="http://127.0.0.1:49152/v1",
        api_key="secret",
        model_id="gemma",
        suite="core-text-v1",
        bench="all",
        tier="standard",
        lane="answer-only",
        seed=1234,
        suite_dir=None,
        suite_source=None,
        out=tmp_path / "run" / "localbench-run.json",
        resume=None,
        max_items=10,
        reasoning_activation="gemma4",
        hf_model_id="unsloth/gemma-4-12b-it",
    )

    # When: building the inner run_localbench config.
    inner = build_orchestrate_config(config, evidence)

    # Then: the headline lane is serialized and provenance-complete.
    assert inner.provider == "local"
    assert inner.concurrency == 1
    assert inner.sampler_temperature == 0.0
    assert inner.sampler_top_k == 1
    assert inner.sampler_seed == 1234
    assert inner.max_items == 10
    assert inner.reasoning_activation == "gemma4"
    assert inner.hf_model_id == "unsloth/gemma-4-12b-it"
    assert inner.runtime_name == "llama.cpp"
    assert inner.runtime_backend == "cuda"
    assert inner.parallel_slots == 1
    assert inner.kv_cache_quant == "k=f16,v=f16"
    assert inner.model_format == "GGUF"
    assert inner.tokenizer_digest == evidence.artifact.tokenizer_digest
    assert inner.tokenizer_digest_source == "gguf.embedded"
    assert inner.chat_template_digest == evidence.artifact.chat_template_digest
    assert inner.chat_template_digest_source == "gguf.embedded"
    assert inner.server_fingerprint == evidence.server_fingerprint
    assert inner.resume_identity == evidence.resume_identity
    assert inner.serve_fingerprint is not None
    assert inner.serve_fingerprint["resume_identity"] == evidence.resume_identity
    assert inner.serve_fingerprint["reasoning"] == {
        "mode": "off",
        "budget": None,
        "format": "deepseek",
    }


def test_serving_bench_config_threads_max_items_to_inner_orchestrate_config(tmp_path: Path) -> None:
    # Given serving options for a capped real-suite bench run.
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=tmp_path / "model.gguf",
        model_ref=None,
        model_id="gemma",
        server_bin=tmp_path / "llama-server.exe",
        ctx=32768,
        determinism="strict",
        tier="standard",
        bench="ifbench",
        lane="capped-thinking",
        seed=1234,
        out=tmp_path / "run",
        max_items=10,
        reasoning_activation="gemma4",
        hf_model_id="unsloth/gemma-4-12b-it",
    )
    evidence = serving_evidence(tmp_path, teardown_terminated=True)

    # When building the bench-managed run config.
    bench_run = assembly.bench_config(options, tmp_path / "localbench-run.json", "secret", 49152)
    inner = build_orchestrate_config(bench_run, evidence)

    # Then the same cap used by the run command reaches OrchestrateConfig.
    assert bench_run.max_items == 10
    assert bench_run.reasoning_activation == "gemma4"
    assert bench_run.hf_model_id == "unsloth/gemma-4-12b-it"
    assert inner.max_items == 10
    assert inner.reasoning_activation == "gemma4"
    assert inner.hf_model_id == "unsloth/gemma-4-12b-it"


def test_capped_thinking_ctx_guard_rejects_context_below_suite_budget(tmp_path: Path) -> None:
    # Given: capped-thinking serving options for the fixture suite with max_tokens=64.
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=tmp_path / "model.gguf",
        model_ref=None,
        model_id="gemma",
        server_bin=tmp_path / "llama-server.exe",
        ctx=10303,
        determinism="strict",
        tier="quick",
        bench="ifeval",
        lane="capped-thinking",
        seed=1234,
        suite_dir=FIXTURE_SUITE,
        out=tmp_path / "run",
    )

    # When / Then: the server launch is refused before work can burn the suite.
    with pytest.raises(RuntimeError, match=r"minimum ctx is 10304"):
        assembly.validate_capped_thinking_context(options)


def test_capped_thinking_ctx_guard_allows_context_at_suite_budget(tmp_path: Path) -> None:
    # Given: the same capped-thinking suite with enough ctx for reasoning, output, and prompt headroom.
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=tmp_path / "model.gguf",
        model_ref=None,
        model_id="gemma",
        server_bin=tmp_path / "llama-server.exe",
        ctx=10304,
        determinism="strict",
        tier="quick",
        bench="ifeval",
        lane="capped-thinking",
        seed=1234,
        suite_dir=FIXTURE_SUITE,
        out=tmp_path / "run",
    )

    # When / Then: a compliant ctx passes without raising.
    assembly.validate_capped_thinking_context(options)
