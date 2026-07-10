from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
import pytest

import localbench.cli as cli_mod
import localbench.serving.runner as serving_runner
import localbench.serving.vllm as vllm
from localbench.serving.model_artifact import (
    ModelArtifactError,
    parse_snapshot_reference,
    snapshot_artifact,
)
from localbench.serving.options import ServeBenchOptions
from localbench.serving.readiness import ReadinessError, verify_vllm_readiness
from localbench.suite_resolver import STATIC_EXEC_SUITE_ID


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
        '{"model_type":"qwen3_5_moe","quantization_config":{"format":"nvfp4"}}',
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
    assert all(not str(row["path"]).startswith(".cache/") for row in first.snapshot_files)


def test_snapshot_reference_requires_immutable_full_sha() -> None:
    parsed = parse_snapshot_reference("hf://owner/model@" + "a" * 40)
    assert parsed.repo_id == "owner/model"
    assert parsed.revision == "a" * 40
    with pytest.raises(ModelArtifactError, match="full 40-character SHA"):
        parse_snapshot_reference("hf://owner/model@main")
    with pytest.raises(ModelArtifactError, match="snapshot, not a #file"):
        parse_snapshot_reference("hf://owner/model@" + "a" * 40 + "#model.safetensors")


def test_vllm_argv_pins_single_request_batch_invariant_engine_profile(tmp_path: Path) -> None:
    argv = vllm.vllm_serve_argv(_launch_config(tmp_path))
    help_text = "\n".join(token for token in argv if token.startswith("--"))
    vllm.validate_vllm_argv(argv, help_text)

    assert argv[argv.index("--max-num-seqs") + 1] == "1"
    assert argv[argv.index("--seed") + 1] == "1234"
    assert argv[argv.index("--generation-config") + 1] == "vllm"
    assert argv[argv.index("--kv-cache-dtype") + 1] == "bfloat16"
    assert argv[argv.index("--quantization") + 1] == "compressed-tensors"
    assert argv[argv.index("--mamba-cache-dtype") + 1] == "bfloat16"
    assert argv[argv.index("--mamba-ssm-cache-dtype") + 1] == "bfloat16"
    assert "--no-enable-prefix-caching" in argv
    assert "--no-enable-chunked-prefill" in argv
    assert "auto" not in argv


def test_collect_vllm_build_identity_is_stable_and_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(_distro: str, argv: list[str], *, check: bool = True):
        if argv[-1] == "--version":
            return _completed("vllm 0.12.0\n")
        if argv[-2:] == ["serve", "--help"]:
            return _completed("--max-num-seqs\n--dtype\n")
        if argv[0] == "readlink":
            return _completed("/opt/vllm/bin/vllm\n")
        if argv[0] == "sha256sum":
            return _completed("b" * 64 + "  /opt/vllm/bin/vllm\n")
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
            model_path="/mnt/c/model",
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
            return httpx.Response(200, json={"data": [{"id": "demo"}]})
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": "0.12.0"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    evidence = await verify_vllm_readiness(
        base_url="http://127.0.0.1:49152",
        model_id="demo",
        model_path="/mnt/c/model",
        api_key="secret",
        seed=1234,
        transport=httpx.MockTransport(handler),
        startup_timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert evidence.reported_model == "demo"
    assert evidence.build_info == "0.12.0"
    assert evidence.total_slots == 1
    assert len(evidence.smoke_chat_sha256) == 64


def test_teardown_vllm_kills_only_recorded_wsl_process_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            raise AssertionError("Windows fallback kill should not be needed")

    signals: list[tuple[int, str]] = []
    gpu_results = iter(([222], []))
    monkeypatch.setattr(vllm, "_process_tree_pids", lambda _distro, _pid: [111, 222])
    monkeypatch.setattr(vllm, "_gpu_pids", lambda _distro: list(next(gpu_results)))
    monkeypatch.setattr(vllm, "_wsl_signal", lambda _distro, pid, signal: signals.append((pid, signal)))
    monkeypatch.setattr(vllm, "_run_wsl", lambda *_args, **_kwargs: _completed())
    server = vllm.LaunchedVllmServer(Process(), "MaintainerDistro", 111, "/tmp/lb.pid", None)  # type: ignore[arg-type]

    evidence = vllm.teardown_vllm(server, timeout_seconds=0.2)

    assert evidence["owned_process_tree"] == ["111", "222"]
    assert evidence["terminated"] is True
    assert evidence["gpu_pids_after"] == []
    assert signals == [(111, "TERM"), (111, "KILL")]


def test_teardown_vllm_marks_persistent_worker_as_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = 0

        def poll(self):
            return 0

    monkeypatch.setattr(vllm, "_process_tree_pids", lambda _distro, _pid: [111, 222])
    monkeypatch.setattr(vllm, "_gpu_pids", lambda _distro: [222])
    monkeypatch.setattr(vllm, "_wsl_signal", lambda *_args: None)
    monkeypatch.setattr(vllm, "_run_wsl", lambda *_args, **_kwargs: _completed())
    server = vllm.LaunchedVllmServer(Process(), "MaintainerDistro", 111, "/tmp/lb.pid", None)  # type: ignore[arg-type]

    evidence = vllm.teardown_vllm(server, timeout_seconds=0)

    assert evidence["terminated"] is False
    assert evidence["teardown_uncertain"] is True
    assert evidence["gpu_pids_after"] == [222]


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
