from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from localbench._types import JsonObject
from localbench.orchestrate import OrchestrateConfig
from localbench.serving import assembly
from localbench.serving import runner as serving_runner
from localbench.serving.bench import BenchRunConfig, build_orchestrate_config
from localbench.serving.llama_cpp import (
    BuildIdentity,
    LlamaCppLaunchConfig,
    collect_build_identity,
    strict_llama_cpp_argv,
    validate_strict_argv_supported,
)
from localbench.serving.model_artifact import ModelArtifact, resolve_model_file_artifact
from localbench.serving.readiness import ReadinessEvidence, verify_llama_cpp_readiness
from localbench.serving.options import ServeBenchOptions
from localbench.serving.runner import run_orchestrated_bench
from localbench.serving.teardown import TeardownEvidence
from localbench.cli import _parser
from localbench.persistence import atomic_write_json
from localbench.submissions.canon import sha256_file
from localbench.submissions.contracts import RESULT_BUNDLE_SCHEMA_VERSION
from localbench.submissions.foundation import validate_submission_bundle
from serving_helpers import flag_value, minimal_gguf, serving_evidence


FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"
SUITE_V1 = Path(__file__).resolve().parents[2] / "suite" / "v1"
SITE_RELEASE_ID = "suite-v1-partial-text-code-4axis-v1"
SITE_MANIFEST_SHA256 = "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7"
BANNED_RESULT_BUNDLE_FIELDS = {
    "schema",
    "composite",
    "trust_tier",
    "serving_verification_level",
    "source",
    "output_path",
}


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


def test_llama_cpp_reasoning_mapping_for_bounded_final_lane() -> None:
    reasoning = assembly.llama_cpp_reasoning_for_lane("bounded-final-v1", "answer_only_v1")

    assert reasoning.reasoning == "off"
    assert reasoning.reasoning_budget is None
    assert reasoning.reasoning_format == "deepseek"


@pytest.mark.parametrize(
    "profile",
    ["generic_think_tags_8192_v1", "gemma4_channel_8192_v1"],
)
def test_llama_cpp_reasoning_mapping_for_bounded_final_thinking_profiles(profile: str) -> None:
    reasoning = assembly.llama_cpp_reasoning_for_lane("bounded-final-v1", profile)

    assert reasoning.reasoning == "on"
    assert reasoning.reasoning_budget == 8192
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


def test_orchestrated_llama_cpp_final_writer_emits_compliant_publishable_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        # Given: a serving run with external process boundaries faked but the final writer intact.
        model = tmp_path / "Gemma-12B-Q4_K_M.gguf"
        model.write_bytes(minimal_gguf())
        server_bin = tmp_path / "llama-server.exe"
        server_bin.write_text("fake", encoding="utf-8")
        out_dir = tmp_path / "run"
        options = ServeBenchOptions(
            runtime="llama.cpp",
            model_file=model,
            model_ref=None,
            model_id="gemma",
            server_bin=server_bin,
            ctx=32768,
            determinism="strict",
            tier="standard",
            bench="mmlu_pro,ifbench,tc_json_v1,lcb",
            lane="answer-only",
            seed=1234,
            out=out_dir,
        )

        monkeypatch.setattr(serving_runner, "allocate_port", lambda: 49152)
        monkeypatch.setattr(serving_runner, "_needs_wsl_agentic", lambda _options: False)
        monkeypatch.setattr(serving_runner, "collect_build_identity", lambda _binary: _build_identity())
        monkeypatch.setattr(serving_runner, "validate_strict_argv_supported", lambda _argv, _help: None)
        monkeypatch.setattr(serving_runner, "launch_llama_cpp", lambda _argv, *, cwd, log_path: _FakeLaunch())
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
        monkeypatch.setattr(serving_runner, "run_localbench", _write_publishable_record)

        # When: the orchestrated serving runner completes its final localbench-run.json write.
        updated = await serving_runner.run_orchestrated_bench(options)
        written = json.loads((out_dir / "localbench-run.json").read_text(encoding="utf-8"))
        validation = validate_submission_bundle(out_dir / "localbench-run.json")

        # Then: the serialized result_bundle_v1 has no banned writer fields and remains publishable.
        assert BANNED_RESULT_BUNDLE_FIELDS.isdisjoint(written)
        assert BANNED_RESULT_BUNDLE_FIELDS.isdisjoint(updated)
        assert written["serving"]["trust_tier"] == "orchestrated-pinned-artifacts-v1"
        assert written["serving"]["verification_level"] == "orchestrated-pinned-artifacts-v1"
        assert validation["publishable"] is True
        assert validation["blocking_reasons"] == []

    asyncio.run(scenario())


class _FakeProcess:
    pid = 1234
    returncode = 0

    def terminate(self) -> None:
        return

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


class _FakeLaunch:
    process = _FakeProcess()
    job = object()
    job_handle = 1

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


async def _fake_readiness(**_kwargs: object) -> ReadinessEvidence:
    return ReadinessEvidence(
        health_200_at="2026-07-01T00:00:00Z",
        models_response_sha256="m" * 64,
        props_response_sha256="p" * 64,
        reported_model="gemma",
        smoke_chat_sha256="s" * 64,
        tokenize_sha256="t" * 64,
        apply_template_sha256="a" * 64,
        total_slots=1,
        model_path="model.gguf",
        chat_template="{{messages}}",
        build_info="llama.cpp b9852 fd1a05791",
    )


async def _write_publishable_record(
    config: OrchestrateConfig,
    *,
    transport: object | None = None,
    agentic_sandbox_factory: object | None = None,
    agentic_model_factory: object | None = None,
    agentic_task_ids: object | None = None,
    agentic_provenance_extra: object | None = None,
) -> JsonObject:
    record = _publishable_result_bundle(config)
    atomic_write_json(record, config.out or Path("localbench-run.json"))
    return record


def _publishable_result_bundle(config: OrchestrateConfig) -> JsonObject:
    model_file = config.model_file
    if model_file is None:
        raise AssertionError("serving writer test requires a resolved model file")
    model_sha = sha256_file(model_file)
    benches = {
        bench: {
            "n": 1,
            "n_errors": 0,
            "n_extraction_failures": 0,
            "raw_accuracy": 1.0,
            "chance_corrected": 1.0,
            "termination_rate": 1.0,
            "conditional_accuracy": 1.0,
        }
        for bench in ("mmlu_pro", "ifbench", "tc_json_v1", "lcb")
    }
    return {
        "schema_version": RESULT_BUNDLE_SCHEMA_VERSION,
        "run_started_at": "2026-07-01T00:00:00Z",
        "run_finished_at": "2026-07-01T00:00:01Z",
        "producer": "localbench-cli",
        "tier": "standard",
        "serving_mode": "external_openai_compatible_endpoint",
        "model": {
            "name": config.model,
            "file_sha256": model_sha,
            "tokenizer_digest": config.tokenizer_digest,
            "chat_template_digest": config.chat_template_digest,
        },
        "manifest": {
            "suite": {
                "suite_release_id": SITE_RELEASE_ID,
                "suite_manifest_sha256": SITE_MANIFEST_SHA256,
                "suite_hash_algorithm": "sha256-canonical-json-v1",
            },
            "sampling": {"temperature": 0.0, "top_k": 1, "seed": 1234},
            "model": {
                "family": config.model_family,
                "quant_label": config.quant_label,
                "file_name": model_file.name,
                "file_size_bytes": model_file.stat().st_size,
                "file_sha256": model_sha,
                "format": config.model_format,
                "tokenizer_digest": config.tokenizer_digest,
                "chat_template_digest": config.chat_template_digest,
            },
            "runtime": {
                "name": config.runtime_name,
                "version": config.runtime_version,
                "kv_cache_quant": config.kv_cache_quant,
                "ctx_len_configured": config.ctx_len_configured,
                "parallel_slots": config.parallel_slots,
            },
            "integrity": {
                "publishable": False,
                "blocking_reasons": [],
                "missing_required_fields": [],
            },
        },
        "axis_status": {"schema_version": "localbench.axis-status.v1", "axes": {}},
        "headline_complete": True,
        "scores": {
            "headline_score": 1.0,
            "partial_composite": 1.0,
            "partial_composite_scope": "measured_headline_axes",
            "measured_headline_weight": 0.5,
            "missing_headline_weight": 0.0,
            "known_headline_contribution": 1.0,
            "rank_scope": "partial-text-code-4axis-v1",
        },
        "benches": benches,
        "conformance": {"status": "headline-comparable"},
        "items": [],
        "totals": {},
        "warnings": [],
    }


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


def test_bench_parser_accepts_retry_errored_flag() -> None:
    # Given the bench subcommand's required arguments plus retry-errored resume mode.
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
            "--resume",
            "runs/bench/gemma",
            "--retry-errored",
        ]
    )

    # Then the retry intent is available to the bench command.
    assert args.command == "bench"
    assert args.resume == Path("runs/bench/gemma")
    assert args.retry_errored is True


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


def test_bench_parser_accepts_wsl_agentic_flags() -> None:
    # Given the bench subcommand's required arguments plus the WSL AppWorld knobs.
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
            "--bench",
            "appworld_c",
            "--wsl-venv-python",
            "~/appworld-harness/venv/bin/python3",
            "--appworld-root",
            "/home/michael/appworld-data",
        ],
    )

    # Then the values are available to the bench command.
    assert args.command == "bench"
    assert args.wsl_venv_python == "~/appworld-harness/venv/bin/python3"
    assert args.appworld_root == "/home/michael/appworld-data"


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


def test_collect_build_identity_derives_release_tag_from_unprefixed_version(tmp_path: Path) -> None:
    # Given: the real release --version format, which omits the bNNNN token.
    server = tmp_path / "llama-server.exe"
    server.write_bytes(b"server")

    def runner(argv: list[str]) -> str:
        if argv[-1] == "--version":
            return "version: 9852 (fd1a05791)\nbuilt with Clang 20.1.8 for Windows x86_64"
        if argv[-1] == "--help":
            return "--model\n"
        if argv[-1] == "--list-devices":
            return "CUDA0 RTX 5090"
        raise AssertionError(argv)

    # When: collecting build identity.
    identity = collect_build_identity(server, runner=runner)

    # Then: the release tag is derived as b<build-number>, matching the tagged form.
    assert identity.source_tag == "b9852"
    assert identity.source_commit == "fd1a05791"


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
        retry_errored=True,
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
    assert inner.retry_errored is True
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
        retry_errored=True,
        reasoning_activation="gemma4",
        hf_model_id="unsloth/gemma-4-12b-it",
    )
    evidence = serving_evidence(tmp_path, teardown_terminated=True)

    # When building the bench-managed run config.
    bench_run = assembly.bench_config(options, tmp_path / "localbench-run.json", "secret", 49152)
    inner = build_orchestrate_config(bench_run, evidence)

    # Then the same cap used by the run command reaches OrchestrateConfig.
    assert bench_run.max_items == 10
    assert bench_run.retry_errored is True
    assert bench_run.reasoning_activation == "gemma4"
    assert bench_run.hf_model_id == "unsloth/gemma-4-12b-it"
    assert inner.max_items == 10
    assert inner.retry_errored is True
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


def test_bounded_final_thinking_ctx_guard_rejects_context_below_suite_budget(tmp_path: Path) -> None:
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
        lane="bounded-final-v1",
        profile="generic_think_tags_8192_v1",
        seed=1234,
        suite_dir=FIXTURE_SUITE,
        out=tmp_path / "run",
    )

    with pytest.raises(RuntimeError, match=r"minimum ctx is 10304"):
        assembly.validate_capped_thinking_context(options)


def test_bounded_final_answer_only_ctx_guard_keeps_existing_noop(tmp_path: Path) -> None:
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=tmp_path / "model.gguf",
        model_ref=None,
        model_id="gemma",
        server_bin=tmp_path / "llama-server.exe",
        ctx=1,
        determinism="strict",
        tier="quick",
        bench="ifeval",
        lane="bounded-final-v1",
        profile="answer_only_v1",
        seed=1234,
        suite_dir=FIXTURE_SUITE,
        out=tmp_path / "run",
    )

    assembly.validate_capped_thinking_context(options)


def test_orchestrated_agentic_preflight_runs_before_server_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        # Given: an appworld_c bench run where the WSL preflight fails.
        model = tmp_path / "model.gguf"
        model.write_bytes(b"GGUF")
        server = tmp_path / "llama-server.exe"
        server.write_bytes(b"server")
        options = ServeBenchOptions(
            runtime="llama.cpp",
            model_file=model,
            model_ref=None,
            model_id="gemma",
            server_bin=server,
            ctx=32768,
            determinism="strict",
            tier="standard",
            bench="appworld_c",
            lane="capped-thinking",
            seed=1234,
            suite_dir=SUITE_V1,
            out=tmp_path / "run",
            max_items=1,
        )
        calls: list[str] = []

        artifact = ModelArtifact(
            model_file=model,
            file_sha256="0" * 64,
            file_size_bytes=4,
            model_format="GGUF",
            model_family="gemma",
            quant_label="Q4_K_M",
            gguf_metadata_path=tmp_path / "metadata.json",
            gguf_metadata_sha256="1" * 64,
            tokenizer_digest="2" * 64,
            chat_template_digest="3" * 64,
        )
        build = BuildIdentity(
            executable_sha256="4" * 64,
            dll_or_so_hashes={},
            version_stdout="llama.cpp b9852 fd1a05791",
            help_text="--model\n--alias\n",
            help_text_sha256="5" * 64,
            source_repo=None,
            source_commit="fd1a05791",
            source_tag="b9852",
            build_flags={},
            list_devices_stdout="CUDA0 RTX 5090",
            cuda_version=None,
        )

        import localbench.serving.runner as runner

        monkeypatch.setattr(runner, "resolve_artifact", lambda _options, _root: artifact)
        monkeypatch.setattr(runner, "server_bin", lambda _options: server)
        monkeypatch.setattr(runner, "collect_build_identity", lambda _binary: build)
        monkeypatch.setattr(runner, "allocate_port", lambda: 49152)
        monkeypatch.setattr(runner, "strict_llama_cpp_argv", lambda _config: [str(server)])
        monkeypatch.setattr(runner, "validate_strict_argv_supported", lambda _argv, _help: None)
        monkeypatch.setattr(runner, "server_fingerprint", lambda **_kwargs: "fp")

        def fail_preflight(**_kwargs: object) -> object:
            calls.append("preflight")
            raise RuntimeError("wsl preflight failed")

        def launch_server(*_args: object, **_kwargs: object) -> object:
            calls.append("launch")
            raise AssertionError("server launch must not happen after failed WSL preflight")

        monkeypatch.setattr(runner, "preflight_wsl_agentic", fail_preflight)
        monkeypatch.setattr(runner, "launch_llama_cpp", launch_server)

        # When / Then: preflight fails closed before the model server is launched.
        with pytest.raises(RuntimeError, match="wsl preflight failed"):
            await run_orchestrated_bench(options)
        assert calls == ["preflight"]

    asyncio.run(scenario())
