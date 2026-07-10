from __future__ import annotations

import subprocess
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

import localbench.cli as cli_mod
import localbench.serving.runner as serving_runner
import localbench.serving.vllm as vllm
import localbench.serving.assembly as serving_assembly
from localbench.manifest import ManifestContext, collect_manifest
from localbench.persistence import atomic_write_json
from localbench.serving.assembly import (
    VllmModelIdentityMismatchError,
    thread_vllm_model_identity,
)
from localbench.serving.model_artifact import (
    ModelArtifactError,
    parse_snapshot_reference,
    snapshot_artifact,
)
from localbench.serving.options import ServeBenchOptions
from localbench.serving.readiness import ReadinessError, verify_vllm_readiness
from localbench.serving.provenance import apply_serving_context, serving_context
from localbench.suite_resolver import STATIC_EXEC_SUITE_ID
from serving_helpers import serving_evidence


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _launch_config(tmp_path: Path) -> vllm.VllmLaunchConfig:
    return vllm.VllmLaunchConfig(
        distro="MaintainerDistro",
        vllm_bin="/opt/vllm/bin/vllm",
        model_path="/mnt/c/model",
        model_id="demo",
        host="127.0.0.1",
        port=49152,
        api_key="secret",
        ctx=32768,
        seed=1234,
        dtype="bfloat16",
        kv_cache_dtype="bfloat16",
        mamba_ssm_cache_dtype="float32",
        quantization="compressed-tensors",
        gpu_memory_utilization="0.92",
        chat_template="/mnt/c/model/chat_template.jinja",
        run_token="abc123",
    )


def test_snapshot_identity_is_deterministic_and_excludes_hf_cache_metadata(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "model-00001-of-00001.safetensors").write_bytes(b"weights")
    (snapshot / "config.json").write_text(
        '{"model_type":"qwen3_5_moe","mamba_ssm_dtype":"float32",'
        '"quantization_config":{"format":"nvfp4"}}',
        encoding="utf-8",
    )
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot / "chat_template.jinja").write_text("{{ messages }}", encoding="utf-8")
    hidden_cache = snapshot / ".cache" / "huggingface"
    hidden_cache.mkdir(parents=True)
    (hidden_cache / "download-state").write_text("first", encoding="utf-8")

    first = snapshot_artifact(snapshot, run_dir=tmp_path / "run-a")
    (hidden_cache / "download-state").write_text("changed", encoding="utf-8")
    second = snapshot_artifact(snapshot, run_dir=tmp_path / "run-b")

    assert first.snapshot_merkle_sha256 == second.snapshot_merkle_sha256
    assert first.snapshot_files == second.snapshot_files
    assert first.file_sha256 == first.snapshot_merkle_sha256
    assert first.quant_label == "NVFP4"
    assert first.mamba_ssm_dtype == "float32"
    assert all(not str(row["path"]).startswith(".cache/") for row in first.snapshot_files)


def test_snapshot_reference_requires_immutable_full_sha() -> None:
    parsed = parse_snapshot_reference("hf://owner/model@" + "a" * 40)
    assert parsed.repo_id == "owner/model"
    assert parsed.revision == "a" * 40
    with pytest.raises(ModelArtifactError, match="full 40-character SHA"):
        parse_snapshot_reference("hf://owner/model@main")
    with pytest.raises(ModelArtifactError, match="snapshot, not a #file"):
        parse_snapshot_reference("hf://owner/model@" + "a" * 40 + "#model.safetensors")


def test_vllm_model_ref_threads_hf_identity_and_rejects_mismatched_override(tmp_path: Path) -> None:
    revision = "a" * 40
    options = ServeBenchOptions(
        runtime="vllm",
        model_file=None,
        model_ref=f"hf://owner/model@{revision}",
        model_id="demo",
        server_bin=None,
        ctx=None,
        determinism="strict",
        tier="quick",
        bench="all",
        lane="bounded-final-v2",
        seed=1234,
        out=tmp_path / "run",
    )
    threaded = thread_vllm_model_identity(options)
    assert threaded.hf_model_id == "owner/model"
    assert threaded.hf_revision == revision

    with pytest.raises(VllmModelIdentityMismatchError, match="hf_model_id"):
        thread_vllm_model_identity(replace(options, hf_model_id="other/model"))


def test_vllm_ref_identity_is_used_by_auto_profile_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = None

    def fake_resolve(request):
        nonlocal captured
        captured = request
        return type("Runtime", (), {"entry": type("Entry", (), {"id": "generic_think_tags_8192_v1"})()})()

    monkeypatch.setattr(serving_assembly, "resolve_bounded_final_profile", fake_resolve)
    options = thread_vllm_model_identity(
        ServeBenchOptions(
            runtime="vllm",
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
        )
    )
    assert serving_assembly.effective_serving_profile(options) == "generic_think_tags_8192_v1"
    assert captured.hf_model_id == "owner/model"
    assert captured.hf_revision == "a" * 40


@pytest.mark.anyio
async def test_snapshot_directory_flows_through_manifest_writer_and_completed_provenance(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "model.safetensors").write_bytes(b"weights")
    (snapshot / "config.json").write_text(
        '{"model_type":"qwen3_5_moe","quantization_config":{"format":"nvfp4"}}',
        encoding="utf-8",
    )
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot / "chat_template.jinja").write_text("{{ messages }}", encoding="utf-8")
    artifact = snapshot_artifact(snapshot, run_dir=tmp_path / "run")
    artifact = replace(artifact, requested_repo="owner/model", requested_revision="a" * 40)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"data": [{"id": "demo"}]})
    )
    manifest = await collect_manifest(
        ManifestContext(
            endpoint="http://local/v1",
            requested_model="demo",
            suite_version="test",
            tier="quick",
            lane="bounded-final-v2",
            item_set_hashes={},
            sampling_by_bench={},
            concurrency=1,
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:01Z",
            wall_clock_s=1.0,
            totals={
                "items": 0,
                "errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "active_wall_seconds": 1.0,
                "completion_tokens_per_second": 0.0,
            },
            rendered_prompt_sample=None,
            model_file=artifact.model_file,
            model_file_sha256=artifact.file_sha256,
            model_file_size_bytes=artifact.file_size_bytes,
            model_family=artifact.model_family,
            quant_label=artifact.quant_label,
            model_format=artifact.model_format,
            tokenizer_digest=artifact.tokenizer_digest,
            chat_template_digest=artifact.chat_template_digest,
            runtime_name="vllm",
            runtime_version="0.24.0",
            kv_cache_quant="bfloat16",
            ctx_len_configured=8192,
            parallel_slots=1,
        ),
        transport=transport,
    )
    assert manifest["model"]["file_sha256"] == artifact.snapshot_merkle_sha256
    output = tmp_path / "run" / "localbench-run.json"
    atomic_write_json({"manifest": manifest}, output)
    serve_log = tmp_path / "run" / "serve.log"
    serve_log.write_text(
        "VLLM_BATCH_INVARIANT selected deterministic NVFP4 kernel\n"
        "model weights 22.1 GiB KV cache 0.7 GiB CUDA graph 0.3 GiB\n",
        encoding="utf-8",
    )
    evidence = replace(
        serving_evidence(tmp_path, teardown_terminated=True),
        runtime="vllm",
        artifact=artifact,
        version_stdout="0.24.0",
        engine_version="0.24.0",
        dependency_lock_sha256="d" * 64,
        runtime_identity_sha256="r" * 64,
        applied_chat_template_sha256=artifact.chat_template_digest,
        deterministic_kernel_evidence=("deterministic NVFP4 kernel",),
        determinism_canary_passed=True,
        memory_allocations={"weights": {"value": 22.1, "unit": "GiB"}},
        device_name="NVIDIA RTX",
        driver_version="600.1",
        dtype="bfloat16",
        quantization="compressed-tensors",
        env_allowlist={"VLLM_BATCH_INVARIANT": "1"},
        serve_log_path=str(serve_log),
    )
    completed = apply_serving_context({"manifest": manifest}, serving_context(evidence))
    atomic_write_json(completed, output)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["serving"]["model_snapshot"]["snapshot_merkle_sha256"] == artifact.file_sha256
    assert written["serving"]["verification_level"] == "orchestrated-pinned-artifacts-v1"


def test_vllm_startup_log_records_determinism_memory_and_fit_failure(tmp_path: Path) -> None:
    log = tmp_path / "serve.log"
    log.write_text(
        "VLLM_BATCH_INVARIANT: deterministic NVFP4 CUTLASS kernel selected\n"
        "model weights 22.1 GiB\nKV cache size 0.7 GiB\nCUDA graph memory 0.3 GiB\n",
        encoding="utf-8",
    )
    evidence = vllm.parse_vllm_startup_log(log)
    assert evidence.deterministic_kernel_evidence
    assert set(evidence.memory_allocations) == {"weights", "kv_cache", "cuda_graph"}
    assert evidence.fit_failure is None

    log.write_text("CUDA out of memory while allocating KV cache\n", encoding="utf-8")
    assert "out of memory" in (vllm.parse_vllm_startup_log(log).fit_failure or "")


def test_vllm_readiness_failure_is_rewritten_as_clear_memory_fit_error(
    tmp_path: Path,
) -> None:
    log = tmp_path / "serve.log"
    log.write_text("CUDA out of memory while allocating KV cache\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="startup memory fit failed: CUDA out of memory"):
        serving_runner._raise_memory_fit_error_if_present(
            log,
            ReadinessError("server never became ready"),
        )


def test_vllm_argv_pins_single_request_batch_invariant_engine_profile(tmp_path: Path) -> None:
    argv = vllm.vllm_serve_argv(_launch_config(tmp_path))
    help_text = (Path(__file__).parent / "fixtures" / "vllm-0.24-serve-help.txt").read_text(
        encoding="utf-8"
    )
    vllm.validate_vllm_argv(argv, help_text)

    assert argv[argv.index("--max-num-seqs") + 1] == "1"
    assert argv[argv.index("--seed") + 1] == "1234"
    assert argv[argv.index("--generation-config") + 1] == "vllm"
    assert argv[argv.index("--kv-cache-dtype") + 1] == "bfloat16"
    assert argv[argv.index("--quantization") + 1] == "compressed-tensors"
    assert argv[argv.index("--mamba-cache-dtype") + 1] == "bfloat16"
    assert argv[argv.index("--mamba-ssm-cache-dtype") + 1] == "float32"
    assert "--no-enable-prefix-caching" in argv
    assert "--no-enable-chunked-prefill" in argv
    assert "auto" not in argv


def test_collect_vllm_build_identity_is_stable_and_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(_distro: str, argv: list[str], *, check: bool = True):
        if argv[-1] == "--version":
            return _completed("vllm 0.24.0\n")
        if argv[-2:] == ["serve", "--help"]:
            return _completed("--max-num-seqs\n--dtype\n")
        if argv[0] == "readlink":
            return _completed("/opt/vllm/bin/vllm\n")
        if argv[0] == "sha256sum":
            return _completed("b" * 64 + "  /opt/vllm/bin/vllm\n")
        if argv[-2:] == ["freeze", "--all"]:
            return _completed("torch==2.9.0\nvllm==0.24.0\n")
        if argv[0].endswith("/python"):
            return _completed("0.24.0\n")
        if argv[0] == "nvidia-smi" and len(argv) > 1:
            return _completed("NVIDIA RTX, 600.1\n")
        return _completed("NVIDIA-SMI 600.1 CUDA Version: 13.0 |\n")

    monkeypatch.setattr(vllm, "_run_wsl", fake_run)
    first, first_help = vllm.collect_vllm_build_identity(
        distro="MaintainerDistro", vllm_bin="/opt/vllm/bin/vllm"
    )
    second, second_help = vllm.collect_vllm_build_identity(
        distro="MaintainerDistro", vllm_bin="/opt/vllm/bin/vllm"
    )

    assert first == second
    assert first_help == second_help
    assert first.executable_sha256 == "b" * 64
    assert first.device_name == "NVIDIA RTX"
    assert first.driver_version == "600.1"
    assert first.cuda_version == "13.0"
    assert first.package_version == "0.24.0"
    assert len(first.dependency_lock_sha256) == 64


def test_launch_vllm_closes_log_when_process_spawn_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vllm.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")))
    log_path = tmp_path / "serve.log"

    with pytest.raises(OSError, match="boom"):
        vllm.launch_vllm(_launch_config(tmp_path), log_path=log_path)

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("closed")


def test_launch_vllm_exports_batch_invariance_inside_pid_scoped_session(
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

    monkeypatch.setattr(vllm.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(vllm, "_wait_for_server_pid", lambda *_args: 111)

    launched = vllm.launch_vllm(_launch_config(tmp_path), log_path=tmp_path / "serve.log")
    launched.close_log()

    script = captured[-1]
    assert "exec setsid bash -c" in script
    assert "echo $$" in script
    assert "VLLM_BATCH_INVARIANT=1" in script
    assert "CUDA_VISIBLE_DEVICES=0" in script


@pytest.mark.anyio
async def test_vllm_readiness_timeout_is_fail_closed() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(503))
    with pytest.raises(ReadinessError, match="vLLM readiness timed out"):
        await verify_vllm_readiness(
            base_url="http://127.0.0.1:49152",
            model_id="demo",
            expected_chat_template="{{ messages }}",
            api_key="secret",
            seed=1234,
            transport=transport,
            startup_timeout_seconds=0,
            poll_interval_seconds=0,
        )


@pytest.mark.anyio
async def test_vllm_readiness_verifies_openai_model_version_and_smoke_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "demo", "root": "/mnt/c/model"}]})
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": "0.24.0"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    evidence = await verify_vllm_readiness(
        base_url="http://127.0.0.1:49152",
        model_id="demo",
        expected_chat_template="{{ messages }}",
        api_key="secret",
        seed=1234,
        transport=httpx.MockTransport(handler),
        startup_timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert evidence.reported_model == "demo"
    assert evidence.build_info == "0.24.0"
    assert evidence.total_slots is None
    assert evidence.model_path == "/mnt/c/model"
    assert len(evidence.apply_template_sha256) == 64
    assert len(evidence.smoke_chat_sha256) == 64


@pytest.mark.anyio
async def test_vllm_readiness_requires_server_reported_0_24_or_newer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "demo"}]})
        return httpx.Response(200, json={"version": "0.23.0"})

    with pytest.raises(ReadinessError, match=r">= 0\.24.*0\.23\.0"):
        await verify_vllm_readiness(
            base_url="http://127.0.0.1:49152",
            model_id="demo",
            expected_chat_template="{{ messages }}",
            api_key="secret",
            seed=1234,
            transport=httpx.MockTransport(handler),
            startup_timeout_seconds=1,
            poll_interval_seconds=0,
        )


def test_vllm_context_defaults_to_profile_requirement_and_allows_explicit_override(tmp_path: Path) -> None:
    options = ServeBenchOptions(
        runtime="vllm",
        model_file=None,
        model_ref="hf://owner/model@" + "a" * 40,
        model_id="demo",
        server_bin=None,
        ctx=None,
        determinism="strict",
        tier="quick",
        bench="all",
        lane="bounded-final-v2",
        seed=1234,
        out=tmp_path / "run",
    )
    assert serving_runner._vllm_max_model_len(options, "generic_think_tags_8192_v1") == 8192
    assert serving_runner._vllm_max_model_len(
        replace(options, vllm_max_model_len=12288), "generic_think_tags_8192_v1"
    ) == 12288


def _launched_server(process) -> vllm.LaunchedVllmServer:
    return vllm.LaunchedVllmServer(
        process,
        "MaintainerDistro",
        111,
        "/tmp/lb.pid",
        None,  # type: ignore[arg-type]
        "abc123",
        "/opt/vllm/bin/vllm",
        "/tmp/localbench-vllm-abc123",
    )


def test_teardown_vllm_refreshes_owned_tree_and_signals_only_verified_token_pids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            raise AssertionError("Windows fallback kill should not be needed")

    commands: list[list[str]] = []
    refreshed = iter(([111, 222], [111, 222, 333], [111, 222, 333]))
    monkeypatch.setattr(vllm, "_refreshed_owned_pids", lambda _server: list(next(refreshed)))
    monkeypatch.setattr(vllm, "_verified_token_pids", lambda *_args: [111])
    monkeypatch.setattr(vllm, "_gpu_pids", lambda _distro: [])
    monkeypatch.setattr(
        vllm,
        "_run_wsl",
        lambda _distro, argv, **_kwargs: (commands.append(argv), _completed())[1],
    )
    server = _launched_server(Process())

    evidence = vllm.teardown_vllm(server, timeout_seconds=0.2)

    assert evidence["owned_process_tree"] == ["111", "222", "333"]
    assert evidence["terminated"] is True
    assert evidence["gpu_pids_after"] == []
    assert [command for command in commands if command[0] == "kill"] == [["kill", "-TERM", "111"]]


def test_teardown_vllm_marks_persistent_worker_as_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = 0

        def poll(self):
            return 0

    monkeypatch.setattr(vllm, "_refreshed_owned_pids", lambda _server: [111, 222])
    monkeypatch.setattr(vllm, "_verified_token_pids", lambda *_args: [])
    monkeypatch.setattr(vllm, "_gpu_pids", lambda _distro: [222])
    monkeypatch.setattr(vllm, "_run_wsl", lambda *_args, **_kwargs: _completed())
    server = _launched_server(Process())

    evidence = vllm.teardown_vllm(server, timeout_seconds=0)

    assert evidence["terminated"] is False
    assert evidence["teardown_uncertain"] is True
    assert evidence["gpu_pids_after"] == [222]


def test_launch_pid_file_failure_locates_and_kills_only_run_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Process:
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    cleaned: list[tuple[str, str]] = []
    monkeypatch.setattr(vllm.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(
        vllm,
        "_wait_for_server_pid",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("pid missing")),
    )
    monkeypatch.setattr(
        vllm,
        "_cleanup_by_token",
        lambda _distro, token, executable: cleaned.append((token, executable)),
    )

    with pytest.raises(RuntimeError, match="pid missing"):
        vllm.launch_vllm(_launch_config(tmp_path), log_path=tmp_path / "serve.log")
    assert cleaned == [("abc123", "/opt/vllm/bin/vllm")]


def test_leader_pid_reuse_is_not_signaled(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        def poll(self):
            return 0

    commands: list[list[str]] = []
    monkeypatch.setattr(vllm, "_verified_token_pids", lambda *_args: [])
    monkeypatch.setattr(vllm, "_refreshed_owned_pids", lambda _server: [])
    monkeypatch.setattr(vllm, "_gpu_pids", lambda _distro: [])
    monkeypatch.setattr(
        vllm,
        "_run_wsl",
        lambda _distro, argv, **_kwargs: (commands.append(argv), _completed())[1],
    )
    evidence = vllm.teardown_vllm(_launched_server(Process()), timeout_seconds=0)
    assert not any(command[0] == "kill" for command in commands)
    assert evidence["teardown_uncertain"] is True


def test_refreshed_tree_includes_reparented_token_child(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _launched_server(object())
    monkeypatch.setattr(vllm, "_verified_token_pids", lambda *_args: [444])
    monkeypatch.setattr(vllm, "_process_tree_pids", lambda _distro, pid: [pid, 555])
    assert vllm._refreshed_owned_pids(server) == [444, 555]


def test_cli_vllm_flags_reach_serve_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
            "vllm",
            "--model-ref",
            "hf://owner/model@" + "a" * 40,
            "--model-id",
            "demo",
            "--ctx",
            "32768",
            "--seed",
            "1234",
            "--wsl-distro",
            "MaintainerDistro",
            "--vllm-venv",
            "/opt/vllm",
            "--out",
            str(tmp_path / "run"),
        ]
    )

    assert code == 0
    assert captured.runtime == "vllm"
    assert captured.wsl_distro == "MaintainerDistro"
    assert captured.vllm_venv == "/opt/vllm"


@pytest.mark.anyio
async def test_runtime_vllm_dispatches_to_adapter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reached = False

    class Adapter:
        def resolve_model(self, *_args, **_kwargs):
            nonlocal reached
            reached = True
            raise RuntimeError("adapter reached")

    monkeypatch.setattr(serving_runner, "VllmAdapter", Adapter)
    options = ServeBenchOptions(
        runtime="vllm",
        model_file=None,
        model_ref="hf://owner/model@" + "a" * 40,
        model_id="demo",
        server_bin=None,
        ctx=32768,
        determinism="strict",
        tier="quick",
        bench="all",
        lane="answer-only",
        seed=1234,
        suite=STATIC_EXEC_SUITE_ID,
        out=tmp_path / "run",
        wsl_distro="MaintainerDistro",
        vllm_venv="/opt/vllm",
    )

    with pytest.raises(RuntimeError, match="adapter reached"):
        await serving_runner.run_orchestrated_bench(options)
    assert reached is True


@pytest.mark.anyio
async def test_bounded_final_vllm_rejects_answer_only_auto_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(serving_runner, "effective_serving_profile", lambda _options: "answer_only_v1")
    options = ServeBenchOptions(
        runtime="vllm",
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
        vllm_venv="/opt/vllm",
    )
    with pytest.raises(
        serving_runner.VllmExecutionProfileMismatchError,
        match="resolved='answer_only_v1'.*expected='generic_think_tags_8192_v1'",
    ):
        await serving_runner.run_orchestrated_bench(options)
