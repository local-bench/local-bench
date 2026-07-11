from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

import localbench.cli as cli_mod
import localbench.serving.runner as serving_runner
import localbench.serving.sglang as sglang
from localbench.serving.model_artifact import snapshot_artifact
from localbench.serving.options import ServeBenchOptions
from localbench.serving.provenance import serving_context
from localbench.serving.readiness import ReadinessError, verify_sglang_readiness
from localbench.suite_resolver import STATIC_EXEC_SUITE_ID
from serving_helpers import serving_evidence

_TEMPLATE_SNAPSHOT = Path(__file__).parent / "fixtures" / "sglang-template-probe"
_TEMPLATE_SHA256 = hashlib.sha256(
    (_TEMPLATE_SNAPSHOT / "chat_template.jinja").read_bytes()
).hexdigest()


def _completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _launch_config() -> sglang.SglangLaunchConfig:
    return sglang.SglangLaunchConfig(
        distro="MaintainerDistro",
        python_bin="/opt/sglang/bin/python",
        model_path="/mnt/c/model",
        model_id="demo",
        host="127.0.0.1",
        port=49152,
        api_key="secret",
        ctx=8192,
        seed=1234,
        dtype="bfloat16",
        kv_cache_dtype="bfloat16",
        mamba_ssm_dtype="float32",
        quantization="compressed-tensors",
        mem_fraction_static="0.80",
        chat_template="/mnt/c/model/chat_template.jinja",
        run_token="abc123",
        expected_executable="/opt/sglang/bin/python",
    )


def _server_info(**overrides: object) -> dict[str, object]:
    info: dict[str, object] = {
        "model_path": "/mnt/c/model",
        "tokenizer_path": "/mnt/c/model",
        "served_model_name": "demo",
        "chat_template": "/mnt/c/model/chat_template.jinja",
        "context_length": 8192,
        "max_running_requests": 1,
        "random_seed": 1234,
        "dtype": "bfloat16",
        "kv_cache_dtype": "bfloat16",
        "mamba_ssm_dtype": "float32",
        "quantization": "compressed-tensors",
        "mem_fraction_static": 0.80,
        "load_format": "safetensors",
        "sampling_defaults": "openai",
        "device": "cuda",
        "tp_size": 1,
        "dp_size": 1,
        "chunked_prefill_size": 2048,
        "disable_radix_cache": True,
        "disable_overlap_schedule": True,
        "cuda_graph_max_bs": 1,
        "attention_backend": "triton",
        "enable_deterministic_inference": True,
        "max_total_num_tokens": 12288,
        "version": "0.5.13",
    }
    info.update(overrides)
    return info


def _readiness_handler(server_info: dict[str, object]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "demo", "root": "demo"}]})
        if request.url.path == "/model_info":
            return httpx.Response(200, json={"model_path": "/mnt/c/model"})
        if request.url.path == "/server_info":
            return httpx.Response(200, json=server_info)
        if request.url.path == "/v1/tokenize":
            return httpx.Response(
                200, json={"tokens": [1, 2], "count": 2, "max_model_len": 8192}
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    return handler


def _readiness_kwargs(server_info: dict[str, object]) -> dict[str, object]:
    return {
        "base_url": "http://127.0.0.1:49152",
        "model_id": "demo",
        "model_path": "/mnt/c/model",
        "chat_template": "/mnt/c/model/chat_template.jinja",
        "pinned_chat_template_sha256": _TEMPLATE_SHA256,
        "api_key": "secret",
        "seed": 1234,
        "ctx": 8192,
        "dtype": "bfloat16",
        "kv_cache_dtype": "bfloat16",
        "mamba_ssm_dtype": "float32",
        "quantization": "compressed-tensors",
        "mem_fraction_static": "0.80",
        "local_snapshot_path": _TEMPLATE_SNAPSHOT,
        "local_token_ids_renderer": lambda _path, _messages: [1, 2],
        "transport": httpx.MockTransport(_readiness_handler(server_info)),
        "startup_timeout_seconds": 1,
        "poll_interval_seconds": 0,
    }


def test_sglang_strict_argv_uses_only_pinned_v0_5_13_flags() -> None:
    argv = sglang.sglang_serve_argv(_launch_config())
    fixture = (
        Path(__file__).parent / "fixtures" / "sglang-0.5.13-server-options.txt"
    ).read_text(encoding="utf-8")

    sglang.validate_sglang_argv(argv, fixture)

    assert argv[:3] == ["/opt/sglang/bin/python", "-m", "sglang.launch_server"]
    assert argv[argv.index("--max-running-requests") + 1] == "1"
    assert argv[argv.index("--chunked-prefill-size") + 1] == "2048"
    assert argv[argv.index("--attention-backend") + 1] == "triton"
    assert "--enable-deterministic-inference" in argv
    assert "auto" not in argv


def test_sglang_flag_validation_exact_matches_options() -> None:
    argv = sglang.sglang_serve_argv(_launch_config())
    fixture = (
        Path(__file__).parent / "fixtures" / "sglang-0.5.13-server-options.txt"
    ).read_text(encoding="utf-8")
    without_dtype = fixture.replace("--dtype\n", "")

    with pytest.raises(RuntimeError, match=r"required flags: --dtype"):
        sglang.validate_sglang_argv(argv, without_dtype)


def test_sglang_build_identity_pins_package_interpreter_and_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = (
        Path(__file__).parent / "fixtures" / "sglang-0.5.13-server-options.txt"
    ).read_text(encoding="utf-8")

    def fake_run(_distro: str, argv: list[str], *, check: bool = True):
        if argv[:2] == ["readlink", "-f"]:
            return _completed("/opt/sglang/bin/python\n")
        if argv[-2:] == ["freeze", "--all"]:
            return _completed("sglang==0.5.13\ntorch==2.11.0\n")
        if argv[-1] == "--help":
            return _completed(fixture)
        if "metadata.distribution" in " ".join(argv):
            return _completed(json.dumps({"file_count": 42, "sha256": "c" * 64}))
        if "importlib.metadata" in " ".join(argv):
            return _completed("0.5.13\n")
        if argv[0] == "sha256sum":
            return _completed("b" * 64 + "  /opt/sglang/bin/python\n")
        if argv[0] == "nvidia-smi" and len(argv) > 1:
            return _completed("NVIDIA RTX, 600.1, 32768\n")
        return _completed("NVIDIA-SMI 600.1 CUDA Version: 13.0 |\n")

    monkeypatch.setattr(sglang, "_run_wsl", fake_run)
    identity, help_text = sglang.collect_sglang_build_identity(
        distro="MaintainerDistro", python_bin="/opt/sglang/bin/python"
    )

    assert identity.package_version == "0.5.13"
    assert identity.expected_executable == "/opt/sglang/bin/python"
    assert identity.executable_sha256 == "b" * 64
    assert identity.total_vram_bytes == 32768 * 1024 * 1024
    assert len(identity.dependency_lock_sha256) == 64
    assert identity.package_tree_sha256 == "c" * 64
    assert identity.runtime_identity_sha256 == hashlib.sha256(
        f"sglang=0.5.13\npackage_tree={'c' * 64}\n".encode()
    ).hexdigest()
    assert help_text == fixture


def test_sglang_build_identity_rejects_unpinned_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(_distro: str, argv: list[str], *, check: bool = True):
        if argv[0] == "readlink":
            return _completed("/opt/sglang/bin/python\n")
        return _completed("0.5.12\n")

    monkeypatch.setattr(sglang, "_run_wsl", fake_run)
    with pytest.raises(RuntimeError, match=r"requires 0\.5\.13.*0\.5\.12"):
        sglang.collect_sglang_build_identity(
            distro="MaintainerDistro", python_bin="/opt/sglang/bin/python"
        )


def test_sglang_build_identity_rejects_missing_package_tree_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = (
        Path(__file__).parent / "fixtures" / "sglang-0.5.13-server-options.txt"
    ).read_text(encoding="utf-8")

    def fake_run(_distro: str, argv: list[str], *, check: bool = True):
        if argv[:2] == ["readlink", "-f"]:
            return _completed("/opt/sglang/bin/python\n")
        if argv[-2:] == ["freeze", "--all"]:
            return _completed("sglang==0.5.13\n")
        if argv[-1] == "--help":
            return _completed(fixture)
        if "metadata.distribution" in " ".join(argv):
            return _completed(json.dumps({"file_count": 0, "sha256": ""}))
        if "importlib.metadata" in " ".join(argv):
            return _completed("0.5.13\n")
        if argv[0] == "sha256sum":
            return _completed("b" * 64 + "  /opt/sglang/bin/python\n")
        if argv[0] == "nvidia-smi" and len(argv) > 1:
            return _completed("NVIDIA RTX, 600.1, 32768\n")
        return _completed("NVIDIA-SMI 600.1 CUDA Version: 13.0 |\n")

    monkeypatch.setattr(sglang, "_run_wsl", fake_run)
    with pytest.raises(RuntimeError, match="package-tree identity is incomplete"):
        sglang.collect_sglang_build_identity(
            distro="MaintainerDistro", python_bin="/opt/sglang/bin/python"
        )


def test_launch_sglang_uses_tokenized_interpreter_and_pid_scoped_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    class Process:
        returncode = None

        def poll(self):
            return None

    def fake_popen(argv, **_kwargs):
        captured.extend(argv)
        return Process()

    monkeypatch.setattr(sglang.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sglang, "_wait_for_server_pid", lambda *_args: 111)
    monkeypatch.setattr(
        sglang, "_read_process_pin", lambda *_args: sglang.ProcessPin(111, 1, 111, 10)
    )
    monkeypatch.setattr(
        sglang, "_process_identity_matches", lambda *_args, **_kwargs: True
    )

    launched = sglang.launch_sglang(_launch_config(), log_path=tmp_path / "serve.log")
    launched.close_log()

    script = captured[-1]
    assert "exec setsid bash -c" in script
    assert "echo $$" in script
    assert "/tmp/localbench-sglang-abc123" in script
    assert "LOCALBENCH_RUN_TOKEN=abc123" in script
    assert "CUDA_VISIBLE_DEVICES=0" in script


@pytest.mark.anyio
async def test_sglang_readiness_uses_server_reported_config_and_capacity() -> None:
    evidence = await verify_sglang_readiness(**_readiness_kwargs(_server_info()))

    assert evidence.reported_model == "demo"
    assert evidence.model_path == "/mnt/c/model"
    assert evidence.build_info == "0.5.13"
    assert evidence.resolved_runtime is not None
    assert evidence.resolved_runtime["enable_deterministic_inference"] is True
    assert evidence.resolved_runtime["max_total_num_tokens"] == 12288
    assert len(evidence.tokenize_sha256) == 64


@pytest.mark.anyio
async def test_sglang_readiness_polls_after_connection_refusal() -> None:
    attempts = 0

    def refused_then_healthy(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/health":
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("connection refused", request=request)
        return _readiness_handler(_server_info())(request)

    evidence = await verify_sglang_readiness(
        **{
            **_readiness_kwargs(_server_info()),
            "transport": httpx.MockTransport(refused_then_healthy),
        }
    )

    assert attempts == 2
    assert evidence.build_info == "0.5.13"


@pytest.mark.anyio
async def test_sglang_readiness_rejects_silent_determinism_fallback() -> None:
    with pytest.raises(ReadinessError, match="enable_deterministic_inference=False"):
        await verify_sglang_readiness(
            **_readiness_kwargs(_server_info(enable_deterministic_inference=False))
        )


@pytest.mark.anyio
async def test_sglang_readiness_rejects_unverified_context_fit() -> None:
    with pytest.raises(ReadinessError, match="max_total_num_tokens"):
        await verify_sglang_readiness(
            **_readiness_kwargs(_server_info(max_total_num_tokens=4096))
        )


@pytest.mark.anyio
async def test_sglang_readiness_rejects_template_token_id_mismatch() -> None:
    with pytest.raises(ReadinessError, match="token IDs do not match"):
        await verify_sglang_readiness(
            **{
                **_readiness_kwargs(_server_info()),
                "local_token_ids_renderer": lambda _path, _messages: [1, 3],
            }
        )


@pytest.mark.anyio
async def test_sglang_readiness_rejects_unrenderable_local_template() -> None:
    def cannot_render(_path: Path, _messages: list[dict[str, object]]) -> list[int]:
        raise ReadinessError("local template unverifiable")

    with pytest.raises(ReadinessError, match="unverifiable"):
        await verify_sglang_readiness(
            **{
                **_readiness_kwargs(_server_info()),
                "local_token_ids_renderer": cannot_render,
            }
        )


def test_sglang_prelaunch_vram_fit_uses_snapshot_weights_and_config(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "model.safetensors").write_bytes(b"w" * 1024)
    (snapshot / "config.json").write_text(
        '{"text_config":{"layer_types":["full_attention","linear_attention"],'
        '"num_key_value_heads":2,"head_dim":64,"dtype":"bfloat16",'
        '"linear_value_head_dim":128,"linear_num_value_heads":48,'
        '"linear_num_key_heads":16,"linear_key_head_dim":128,'
        '"linear_conv_kernel_dim":4,"mamba_ssm_dtype":"float32"},'
        '"vision_config":{"hidden_size":1152},'
        '"quantization_config":{"format":"nvfp4"}}',
        encoding="utf-8",
    )
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot / "chat_template.jinja").write_text("{{ messages }}", encoding="utf-8")
    artifact = snapshot_artifact(snapshot, run_dir=tmp_path / "run")
    assert artifact.mamba_ssm_dtype == "float32"

    fit = sglang.compute_sglang_memory_fit(
        artifact,
        max_model_len=8192,
        total_vram_bytes=32 * 1024**3,
        mem_fraction_static="0.80",
    )

    assert fit.weights_bytes == 1024
    assert fit.kv_bytes == 1 * 2 * 64 * 2 * 2 * 8192
    assert fit.mamba_state_bytes == (
        1 * ((128 * 48 + 2 * 16 * 128) * 3 * 2 + 48 * 128 * 128 * 4) * 2
    )
    assert fit.static_required_bytes == fit.weights_bytes + fit.kv_bytes + fit.mamba_state_bytes
    assert fit.non_static_budget_bytes == fit.total_vram_bytes - fit.static_budget_bytes
    assert fit.non_static_required_bytes > 4 * 1024**3
    assert fit.fits is True

    with pytest.raises(RuntimeError, match="non_static_required_bytes"):
        sglang.compute_sglang_memory_fit(
            artifact,
            max_model_len=8192,
            total_vram_bytes=16 * 1024**3,
            mem_fraction_static="0.80",
        )


def test_sglang_publishability_requires_resolved_determinism_and_memory(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "model.safetensors").write_bytes(b"weights")
    (snapshot / "config.json").write_text(
        '{"quantization_config":{"format":"nvfp4"}}', encoding="utf-8"
    )
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot / "chat_template.jinja").write_text("{{ messages }}", encoding="utf-8")
    artifact = replace(
        snapshot_artifact(snapshot, run_dir=tmp_path / "artifact-run"),
        requested_repo="owner/model",
        requested_revision="a" * 40,
    )
    serve_log = tmp_path / "run" / "serve.log"
    serve_log.parent.mkdir()
    serve_log.write_text("SGLang v0.5.13\n", encoding="utf-8")
    base = serving_evidence(tmp_path, teardown_terminated=True)
    evidence = replace(
        base,
        runtime="sglang",
        artifact=artifact,
        argv=["python", "--enable-deterministic-inference"],
        version_stdout="0.5.13",
        engine_version="0.5.13",
        dependency_lock_sha256="d" * 64,
        runtime_identity_sha256="r" * 64,
        installed_package_tree_sha256="p" * 64,
        applied_chat_template_sha256=artifact.chat_template_digest,
        device_name="NVIDIA RTX",
        driver_version="600.1",
        dtype="bfloat16",
        quantization="compressed-tensors",
        determinism_canary_passed=True,
        computed_memory_fit={"fits": True},
        memory_allocations={"kv_cache": {"value": 12288, "unit": "tokens"}},
        resolved_server_config={
            "version": "0.5.13",
            "enable_deterministic_inference": True,
            "attention_backend": "triton",
            "max_running_requests": 1,
        },
        serve_log_path=str(serve_log),
        reported_model=base.model_id,
    )

    assert serving_context(evidence).blocking_reasons == ()
    missing_tree = replace(evidence, installed_package_tree_sha256=None)
    assert (
        "runtime.installed_package_tree_identity_missing"
        in serving_context(missing_tree).blocking_reasons
    )
    fallback = replace(
        evidence,
        resolved_server_config={
            **(evidence.resolved_server_config or {}),
            "enable_deterministic_inference": False,
        },
    )
    assert (
        "runtime.deterministic_inference_unverified"
        in serving_context(fallback).blocking_reasons
    )


def test_cli_sglang_flags_reach_serve_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = None

    def fake_anyio_run(_function, options):
        nonlocal captured
        captured = options
        return {"benches": {}, "totals": {}, "warnings": []}

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda *_args, **_kwargs: None)
    code = cli_mod.main(
        [
            "bench",
            "--runtime",
            "sglang",
            "--model-ref",
            "hf://owner/model@" + "a" * 40,
            "--model-id",
            "demo",
            "--seed",
            "1234",
            "--wsl-distro",
            "MaintainerDistro",
            "--sglang-venv",
            "/opt/sglang",
            "--out",
            str(tmp_path / "run"),
        ]
    )

    assert code == 0
    assert captured.runtime == "sglang"
    assert captured.sglang_venv == "/opt/sglang"


@pytest.mark.anyio
async def test_runtime_sglang_dispatches_to_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reached = False

    class Adapter:
        def resolve_model(self, *_args, **_kwargs):
            nonlocal reached
            reached = True
            raise RuntimeError("adapter reached")

    monkeypatch.setattr(serving_runner, "SglangAdapter", Adapter)
    options = ServeBenchOptions(
        runtime="sglang",
        model_file=None,
        model_ref="hf://owner/model@" + "a" * 40,
        model_id="demo",
        server_bin=None,
        ctx=8192,
        determinism="strict",
        tier="quick",
        bench="all",
        lane="answer-only",
        seed=1234,
        suite=STATIC_EXEC_SUITE_ID,
        out=tmp_path / "run",
        wsl_distro="MaintainerDistro",
        sglang_venv="/opt/sglang",
    )

    with pytest.raises(RuntimeError, match="adapter reached"):
        await serving_runner.run_orchestrated_bench(options)
    assert reached is True


@pytest.mark.anyio
async def test_bounded_final_sglang_rejects_answer_only_auto_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        serving_runner, "effective_serving_profile", lambda _options: "answer_only_v1"
    )
    options = ServeBenchOptions(
        runtime="sglang",
        model_file=None,
        model_ref="hf://owner/model@" + "a" * 40,
        model_id="demo",
        server_bin=None,
        ctx=None,
        determinism="strict",
        tier="quick",
        bench="all",
        lane="bounded-final-v2",
        profile="auto",
        seed=1234,
        out=tmp_path / "run",
        wsl_distro="MaintainerDistro",
        sglang_venv="/opt/sglang",
    )
    with pytest.raises(
        serving_runner.SglangExecutionProfileMismatchError,
        match="resolved='answer_only_v1'.*expected='generic_think_tags_8192_v1'",
    ):
        await serving_runner.run_orchestrated_bench(options)
