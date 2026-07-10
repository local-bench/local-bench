from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from localbench._types import JsonObject
from localbench.serving.model_artifact import ModelArtifact, resolve_snapshot_reference
from localbench.serving.readiness import ReadinessEvidence, verify_vllm_readiness
from localbench.serving.teardown import TeardownEvidence


@dataclass(frozen=True, slots=True)
class VllmLaunchConfig:
    distro: str
    vllm_bin: str
    model_path: str
    model_id: str
    host: str
    port: int
    api_key: str
    ctx: int
    seed: int
    dtype: str
    kv_cache_dtype: str
    quantization: str
    gpu_memory_utilization: str
    chat_template: str
    run_token: str


@dataclass(frozen=True, slots=True)
class VllmBuildIdentity:
    executable_sha256: str
    version_stdout: str
    help_text_sha256: str
    device_name: str
    driver_version: str
    cuda_version: str | None
    help_text: str


@dataclass(slots=True)
class LaunchedVllmServer:
    process: subprocess.Popen[str]
    distro: str
    server_pid: int
    pid_file: str
    log_handle: TextIO

    def close_log(self) -> None:
        self.log_handle.close()


class VllmAdapter:
    runtime = "vllm"

    def resolve_model(self, ref: str, *, cache_dir: Path, run_dir: Path) -> ModelArtifact:
        return resolve_vllm_model(ref, cache_dir=cache_dir, run_dir=run_dir)

    def build_identity(self, *, distro: str, vllm_bin: str) -> VllmBuildIdentity:
        identity, _help_text = collect_vllm_build_identity(distro=distro, vllm_bin=vllm_bin)
        return identity

    def launch(self, config: VllmLaunchConfig, *, log_path: Path) -> LaunchedVllmServer:
        return launch_vllm(config, log_path=log_path)

    async def readiness(
        self,
        *,
        base_url: str,
        model_id: str,
        model_path: str,
        api_key: str,
        seed: int,
    ) -> ReadinessEvidence:
        return await verify_vllm_readiness(
            base_url=base_url,
            model_id=model_id,
            model_path=model_path,
            api_key=api_key,
            seed=seed,
        )

    def teardown(self, server: LaunchedVllmServer) -> TeardownEvidence:
        result = teardown_vllm(server)
        return TeardownEvidence(
            owned_process_tree=[str(value) for value in result["owned_process_tree"]],
            terminated=result["terminated"] is True,
            exit_code=result["exit_code"] if isinstance(result["exit_code"], int) else None,
            gpu_pids_after=[int(value) for value in result["gpu_pids_after"]],
            teardown_uncertain=result["teardown_uncertain"] is True,
        )


def resolve_vllm_model(ref: str, *, cache_dir: Path, run_dir: Path) -> ModelArtifact:
    return resolve_snapshot_reference(ref, cache_dir=cache_dir, run_dir=run_dir)


def wsl_path(path: Path, *, distro: str) -> str:
    completed = _run_wsl(distro, ["wslpath", "-a", str(path.resolve())])
    value = completed.stdout.strip()
    if not value.startswith("/"):
        raise RuntimeError("WSL did not return an absolute model snapshot path")
    return value


def vllm_serve_argv(config: VllmLaunchConfig) -> list[str]:
    return [
        config.vllm_bin,
        "serve",
        config.model_path,
        "--served-model-name",
        config.model_id,
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--api-key",
        config.api_key,
        "--max-model-len",
        str(config.ctx),
        "--max-num-seqs",
        "1",
        "--seed",
        str(config.seed),
        "--dtype",
        config.dtype,
        "--kv-cache-dtype",
        config.kv_cache_dtype,
        "--mamba-cache-dtype",
        config.kv_cache_dtype,
        "--mamba-ssm-cache-dtype",
        config.kv_cache_dtype,
        "--quantization",
        config.quantization,
        "--gpu-memory-utilization",
        config.gpu_memory_utilization,
        "--load-format",
        "safetensors",
        "--tokenizer",
        config.model_path,
        "--chat-template",
        config.chat_template,
        "--no-enable-prefix-caching",
        "--no-enable-chunked-prefill",
        "--generation-config",
        "vllm",
        "--tensor-parallel-size",
        "1",
        "--disable-log-requests",
    ]


def validate_vllm_argv(argv: list[str], help_text: str) -> None:
    required = {
        "--served-model-name",
        "--host",
        "--port",
        "--api-key",
        "--max-model-len",
        "--max-num-seqs",
        "--seed",
        "--dtype",
        "--kv-cache-dtype",
        "--mamba-cache-dtype",
        "--mamba-ssm-cache-dtype",
        "--quantization",
        "--gpu-memory-utilization",
        "--load-format",
        "--tokenizer",
        "--chat-template",
        "--no-enable-prefix-caching",
        "--no-enable-chunked-prefill",
        "--generation-config",
        "--tensor-parallel-size",
        "--disable-log-requests",
    }
    missing_argv = sorted(flag for flag in required if flag not in argv)
    unsupported = sorted(flag for flag in required if flag not in help_text)
    if missing_argv:
        raise RuntimeError(f"vLLM strict argv missing required flags: {', '.join(missing_argv)}")
    if unsupported:
        raise RuntimeError(f"configured vLLM does not support required flags: {', '.join(unsupported)}")
    if any(token.lower() == "auto" for token in argv):
        raise RuntimeError("vLLM strict argv contains an unresolved auto value")


def collect_vllm_build_identity(*, distro: str, vllm_bin: str) -> tuple[VllmBuildIdentity, str]:
    version = _run_wsl(distro, [vllm_bin, "--version"]).stdout.strip()
    help_text = _run_wsl(distro, [vllm_bin, "serve", "--help"]).stdout
    executable = _run_wsl(distro, ["readlink", "-f", vllm_bin]).stdout.strip()
    executable_sha = _run_wsl(distro, ["sha256sum", executable]).stdout.split()[0]
    gpu = _run_wsl(
        distro,
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version",
            "--format=csv,noheader,nounits",
        ],
    ).stdout.strip().splitlines()
    cuda = _run_wsl(
        distro,
        ["nvidia-smi"],
    ).stdout
    if (
        not version
        or not help_text
        or not executable
        or len(executable_sha) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in executable_sha)
        or not gpu
    ):
        raise RuntimeError("vLLM build identity is incomplete")
    fields = [field.strip() for field in gpu[0].split(",")]
    if len(fields) != 2 or not fields[0] or not fields[1]:
        raise RuntimeError("vLLM GPU/driver identity is incomplete")
    cuda_version = _cuda_version(cuda)
    return (
        VllmBuildIdentity(
            executable_sha256=executable_sha,
            version_stdout=version,
            help_text_sha256=hashlib.sha256(help_text.encode("utf-8")).hexdigest(),
            device_name=fields[0],
            driver_version=fields[1],
            cuda_version=cuda_version,
            help_text=help_text,
        ),
        help_text,
    )


def launch_vllm(config: VllmLaunchConfig, *, log_path: Path) -> LaunchedVllmServer:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    pid_file = f"/tmp/localbench-vllm-{config.run_token}.pid"
    command = " ".join(shlex.quote(token) for token in vllm_serve_argv(config))
    inner = (
        f"echo $$ > {shlex.quote(pid_file)}; "
        "export VLLM_BATCH_INVARIANT=1 CUDA_VISIBLE_DEVICES=0; "
        f"exec {command}"
    )
    script = f"exec setsid bash -c {shlex.quote(inner)}"
    try:
        process = subprocess.Popen(
            ["wsl.exe", "-d", config.distro, "--exec", "bash", "-lc", script],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=dict(os.environ),
        )
    except BaseException:
        log_handle.close()
        raise
    try:
        server_pid = _wait_for_server_pid(config.distro, pid_file, process)
    except BaseException:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()
        raise
    return LaunchedVllmServer(process, config.distro, server_pid, pid_file, log_handle)


def teardown_vllm(server: LaunchedVllmServer, *, timeout_seconds: float = 30.0) -> JsonObject:
    owned_pids = _process_tree_pids(server.distro, server.server_pid)
    owned = [str(pid) for pid in owned_pids]
    _wsl_signal(server.distro, server.server_pid, "TERM")
    deadline = time.monotonic() + timeout_seconds
    while server.process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if server.process.poll() is None:
        _wsl_signal(server.distro, server.server_pid, "KILL")
        try:
            server.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.process.kill()
            server.process.wait(timeout=5)
    gpu_pids = _gpu_pids(server.distro)
    residual = [pid for pid in gpu_pids if pid in owned_pids]
    if residual:
        _wsl_signal(server.distro, server.server_pid, "KILL")
        deadline = time.monotonic() + min(timeout_seconds, 5.0)
        while residual and time.monotonic() < deadline:
            time.sleep(0.05)
            residual = [pid for pid in _gpu_pids(server.distro) if pid in owned_pids]
    _run_wsl(server.distro, ["rm", "-f", server.pid_file], check=False)
    return {
        "owned_process_tree": owned,
        "terminated": server.process.poll() is not None and not residual,
        "exit_code": server.process.poll(),
        "gpu_pids_after": residual,
        "teardown_uncertain": server.process.poll() is None or bool(residual),
    }


def _wait_for_server_pid(distro: str, pid_file: str, process: subprocess.Popen[str]) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"vLLM launch failed with exit code {process.returncode}")
        completed = _run_wsl(distro, ["cat", pid_file], check=False)
        value = completed.stdout.strip()
        if value.isdigit() and int(value) > 1:
            return int(value)
        time.sleep(0.05)
    raise RuntimeError("vLLM launch did not publish its WSL PID")


def _wsl_signal(distro: str, pid: int, signal: str) -> None:
    # Negative PID targets only the process group created by setsid; never a name sweep.
    _run_wsl(distro, ["kill", f"-{signal}", f"-{pid}"], check=False)


def _gpu_pids(distro: str) -> list[int]:
    completed = _run_wsl(
        distro,
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        check=False,
    )
    return [int(line.strip()) for line in completed.stdout.splitlines() if line.strip().isdigit()]


def _process_tree_pids(distro: str, root_pid: int) -> list[int]:
    completed = _run_wsl(distro, ["ps", "-eo", "pid=,ppid="], check=False)
    children: dict[int, list[int]] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and all(value.isdigit() for value in fields):
            pid, parent = (int(value) for value in fields)
            children.setdefault(parent, []).append(pid)
    owned = [root_pid]
    for pid in owned:
        owned.extend(child for child in children.get(pid, []) if child not in owned)
    return owned


def _run_wsl(
    distro: str,
    argv: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["wsl.exe", "-d", distro, "--exec", *argv],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown WSL error"
        raise RuntimeError(f"WSL command failed: {detail}")
    return completed


def quantization_config(artifact: ModelArtifact) -> str:
    if artifact.quant_label != "NVFP4":
        raise RuntimeError("vLLM maintainer lane requires an NVFP4 safetensors snapshot")
    return "compressed-tensors"


def _cuda_version(output: str) -> str | None:
    marker = "CUDA Version:"
    if marker not in output:
        return None
    value = output.split(marker, 1)[1].strip().split()[0]
    return value.rstrip("|") or None
