from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from localbench._types import JsonObject
from localbench.serving.model_artifact import ModelArtifact, resolve_snapshot_reference
from localbench.serving.readiness import ReadinessEvidence, verify_vllm_readiness
from localbench.serving.teardown import TeardownEvidence


# Fixed allowance for activations, CUDA graphs, kernels, and workspaces. This is
# deliberately charged inside gpu_memory_utilization rather than against spare VRAM.
VLLM_FIXED_HEADROOM_BYTES = 2 * 1024**3
_LOGGER = logging.getLogger(__name__)


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
    mamba_ssm_cache_dtype: str
    quantization: str
    gpu_memory_utilization: str
    chat_template: str
    run_token: str
    expected_executable: str


@dataclass(frozen=True, slots=True)
class VllmBuildIdentity:
    executable_sha256: str
    version_stdout: str
    help_text_sha256: str
    device_name: str
    driver_version: str
    cuda_version: str | None
    help_text: str
    package_version: str
    dependency_lock_sha256: str
    expected_executable: str
    total_vram_bytes: int
    runtime_identity_sha256: str


@dataclass(frozen=True, slots=True)
class VllmLogEvidence:
    deterministic_kernel_evidence: tuple[str, ...]
    deterministic_kernel_enabled: bool
    memory_allocations: JsonObject
    fit_failure: str | None


@dataclass(frozen=True, slots=True)
class VllmMemoryFit:
    weights_bytes: int
    kv_bytes: int
    headroom_bytes: int
    required_bytes: int
    total_vram_bytes: int
    gpu_memory_utilization: float
    budget_bytes: int
    fits: bool

    def provenance(self) -> JsonObject:
        return {
            "weights_bytes": self.weights_bytes,
            "kv_bytes": self.kv_bytes,
            "fixed_headroom_bytes": self.headroom_bytes,
            "required_bytes": self.required_bytes,
            "total_vram_bytes": self.total_vram_bytes,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "budget_bytes": self.budget_bytes,
            "fits": self.fits,
        }


@dataclass(frozen=True, slots=True)
class ProcessPin:
    pid: int
    ppid: int
    pgid: int
    start_time: int


@dataclass(slots=True)
class LaunchedVllmServer:
    process: subprocess.Popen[str]
    distro: str
    server_pid: int
    pid_file: str
    log_handle: TextIO
    run_token: str
    expected_executable: str
    token_executable: str
    leader_pin: ProcessPin
    captured_processes: dict[int, ProcessPin] = field(default_factory=dict)

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
        pinned_chat_template_sha256: str,
        api_key: str,
        seed: int,
    ) -> ReadinessEvidence:
        return await verify_vllm_readiness(
            base_url=base_url,
            model_id=model_id,
            pinned_chat_template_sha256=pinned_chat_template_sha256,
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
        config.mamba_ssm_cache_dtype,
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
    supported = set(re.findall(r"(?<![\w-])--[a-z0-9][a-z0-9-]*", help_text, re.IGNORECASE))
    unsupported = sorted(flag for flag in required if flag not in supported)
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
    venv_python = f"{vllm_bin.rsplit('/', 1)[0]}/python"
    interpreter = _run_wsl(distro, ["readlink", "-f", venv_python]).stdout.strip()
    package_version = _run_wsl(
        distro,
        [venv_python, "-c", "import importlib.metadata; print(importlib.metadata.version('vllm'))"],
    ).stdout.strip()
    dependency_lock = _run_wsl(
        distro,
        [venv_python, "-m", "pip", "freeze", "--all"],
    ).stdout
    dependency_lock_sha256 = hashlib.sha256(dependency_lock.encode("utf-8")).hexdigest()
    runtime_identity_sha256 = hashlib.sha256(
        f"vllm={package_version}\nlock={dependency_lock_sha256}\n".encode("utf-8")
    ).hexdigest()
    gpu = _run_wsl(
        distro,
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
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
        or not package_version
        or not interpreter
        or not dependency_lock.strip()
    ):
        raise RuntimeError("vLLM build identity is incomplete")
    fields = [field.strip() for field in gpu[0].split(",")]
    if len(fields) != 3 or not fields[0] or not fields[1]:
        raise RuntimeError("vLLM GPU/driver identity is incomplete")
    try:
        total_vram_bytes = int(fields[2]) * 1024 * 1024
    except ValueError as error:
        raise RuntimeError("vLLM GPU total-memory identity is invalid") from error
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
            package_version=package_version,
            dependency_lock_sha256=dependency_lock_sha256,
            expected_executable=interpreter,
            total_vram_bytes=total_vram_bytes,
            runtime_identity_sha256=runtime_identity_sha256,
        ),
        help_text,
    )


def launch_vllm(config: VllmLaunchConfig, *, log_path: Path) -> LaunchedVllmServer:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    pid_file = f"/tmp/localbench-vllm-{config.run_token}.pid"
    token_executable = f"/tmp/localbench-vllm-{config.run_token}"
    command_argv = vllm_serve_argv(config)
    expected_executable = config.expected_executable
    command_argv[0] = token_executable
    command = " ".join(shlex.quote(token) for token in command_argv)
    inner = (
        f"ln -sf {shlex.quote(config.vllm_bin)} {shlex.quote(token_executable)}; "
        f"echo $$ > {shlex.quote(pid_file)}; "
        f"export LOCALBENCH_RUN_TOKEN={shlex.quote(config.run_token)} "
        "VLLM_BATCH_INVARIANT=1 CUDA_VISIBLE_DEVICES=0; "
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
        leader_pin = _read_process_pin(config.distro, server_pid)
        if leader_pin is None or not _process_identity_matches(
            config.distro,
            server_pid,
            config.run_token,
            expected_executable,
            expected_start_time=leader_pin.start_time if leader_pin is not None else None,
        ):
            raise RuntimeError("vLLM launch process identity could not be pinned")
    except BaseException:
        _cleanup_by_token(config.distro, config.run_token, expected_executable)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()
        raise
    return LaunchedVllmServer(
        process,
        config.distro,
        server_pid,
        pid_file,
        log_handle,
        config.run_token,
        expected_executable,
        token_executable,
        leader_pin,
        {leader_pin.pid: leader_pin},
    )


def teardown_vllm(server: LaunchedVllmServer, *, timeout_seconds: float = 30.0) -> JsonObject:
    captured = _capture_owned_processes(server)
    owned = [str(pid) for pid in sorted(captured)]
    signaled = _signal_verified(server, captured, "TERM")
    deadline = time.monotonic() + timeout_seconds
    while server.process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if server.process.poll() is None:
        signaled = _signal_verified(server, captured, "KILL") or signaled
        try:
            server.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.process.kill()
            server.process.wait(timeout=5)
    residual = _verified_gpu_residuals(server, captured)
    if residual:
        signaled = _signal_verified(server, captured, "KILL") or signaled
        deadline = time.monotonic() + min(timeout_seconds, 5.0)
        while residual and time.monotonic() < deadline:
            time.sleep(0.05)
            residual = _verified_gpu_residuals(server, captured)
    _run_wsl(
        server.distro,
        ["rm", "-f", server.pid_file, server.token_executable],
        check=False,
    )
    return {
        "owned_process_tree": owned,
        "terminated": signaled and server.process.poll() is not None and not residual,
        "exit_code": server.process.poll(),
        "gpu_pids_after": residual,
        "teardown_uncertain": not signaled or server.process.poll() is None or bool(residual),
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


def _signal_verified(
    server: LaunchedVllmServer,
    captured: dict[int, ProcessPin],
    signal: str,
) -> bool:
    signaled = False
    group_signaled = False
    group_members = _current_group_members(server.distro, server.leader_pin.pgid)
    if group_members and all(
        pin.pid in captured and captured[pin.pid].start_time == pin.start_time
        for pin in group_members
    ):
        _run_wsl(
            server.distro,
            ["kill", f"-{signal}", "--", f"-{server.leader_pin.pgid}"],
            check=False,
        )
        signaled = True
        group_signaled = True
    elif group_members:
        _LOGGER.warning(
            "refusing to signal vLLM process group %s: a PID/start-time identity changed",
            server.leader_pin.pgid,
        )
    # A descendant may create a new process group. It is signalled individually only
    # when its PID/start-time pair is still the one captured in the teardown walk.
    for pin in captured.values():
        if group_signaled and pin.pgid == server.leader_pin.pgid:
            continue
        if not _pin_still_matches(server.distro, pin):
            _LOGGER.warning(
                "refusing to signal vLLM descendant PID %s: start-time identity changed",
                pin.pid,
            )
            continue
        _run_wsl(server.distro, ["kill", f"-{signal}", str(pin.pid)], check=False)
        signaled = True
    return signaled


def _cleanup_by_token(distro: str, run_token: str, expected_executable: str) -> None:
    for pin in _verified_token_processes(distro, run_token, expected_executable):
        if _pin_still_matches(distro, pin):
            _run_wsl(distro, ["kill", "-KILL", str(pin.pid)], check=False)


def _verified_token_pids(distro: str, run_token: str, expected_executable: str) -> list[int]:
    return [pin.pid for pin in _verified_token_processes(distro, run_token, expected_executable)]


def _verified_token_processes(
    distro: str,
    run_token: str,
    expected_executable: str,
) -> list[ProcessPin]:
    completed = _run_wsl(distro, ["pgrep", "-f", run_token], check=False)
    candidates = [int(value) for value in completed.stdout.split() if value.isdigit()]
    verified: list[ProcessPin] = []
    for pid in candidates:
        pin = _read_process_pin(distro, pid)
        if pin is not None and _process_identity_matches(
            distro,
            pid,
            run_token,
            expected_executable,
            expected_start_time=pin.start_time,
        ):
            verified.append(pin)
    return verified


def _process_identity_matches(
    distro: str,
    pid: int,
    run_token: str,
    expected_executable: str,
    *,
    expected_start_time: int | None = None,
) -> bool:
    completed = _run_wsl(
        distro,
        [
            "bash",
            "-lc",
            f"tr '\\0' ' ' < /proc/{pid}/cmdline; printf '\\n'; readlink -f /proc/{pid}/exe",
        ],
        check=False,
    )
    lines = completed.stdout.splitlines()
    if completed.returncode != 0 or len(lines) < 2:
        return False
    command_line, executable = lines[0], lines[-1].strip()
    expected = _run_wsl(distro, ["readlink", "-f", expected_executable], check=False).stdout.strip()
    pin = _read_process_pin(distro, pid)
    return (
        run_token in command_line
        and bool(expected)
        and executable == expected
        and pin is not None
        and (expected_start_time is None or pin.start_time == expected_start_time)
    )


def _refreshed_owned_pids(server: LaunchedVllmServer) -> list[int]:
    return sorted(_capture_owned_processes(server))


def _capture_owned_processes(server: LaunchedVllmServer) -> dict[int, ProcessPin]:
    if not _process_identity_matches(
        server.distro,
        server.leader_pin.pid,
        server.run_token,
        server.expected_executable,
        expected_start_time=server.leader_pin.start_time,
    ):
        return {
            pid: pin
            for pid, pin in server.captured_processes.items()
            if _pin_still_matches(server.distro, pin)
        }
    pins = {pin.pid: pin for pin in _all_process_pins(server.distro)}
    owned_ids = set(_descendant_ids(pins, server.leader_pin.pid))
    # Reparented workers remain owned when they are still in the pinned process group.
    owned_ids.update(pin.pid for pin in pins.values() if pin.pgid == server.leader_pin.pgid)
    current = {pid: pins[pid] for pid in owned_ids if pid in pins}
    server.captured_processes.update(current)
    return {
        pid: pin
        for pid, pin in server.captured_processes.items()
        if _pin_still_matches(server.distro, pin)
    }


def refresh_vllm_process_ownership(server: LaunchedVllmServer) -> tuple[ProcessPin, ...]:
    """Capture the live worker lineage before benchmark execution can outlive its leader."""
    return tuple(_capture_owned_processes(server).values())


def _descendant_ids(pins: dict[int, ProcessPin], root_pid: int) -> list[int]:
    children: dict[int, list[int]] = {}
    for pin in pins.values():
        children.setdefault(pin.ppid, []).append(pin.pid)
    owned = [root_pid]
    for pid in owned:
        owned.extend(child for child in children.get(pid, []) if child not in owned)
    return owned


def _all_process_pins(distro: str) -> list[ProcessPin]:
    completed = _run_wsl(distro, ["ps", "-e", "-o", "pid="], check=False)
    pins: list[ProcessPin] = []
    for value in completed.stdout.split():
        if value.isdigit():
            pin = _read_process_pin(distro, int(value))
            if pin is not None:
                pins.append(pin)
    return pins


def _current_group_members(distro: str, pgid: int) -> list[ProcessPin]:
    return [pin for pin in _all_process_pins(distro) if pin.pgid == pgid]


def _read_process_pin(distro: str, pid: int) -> ProcessPin | None:
    completed = _run_wsl(distro, ["cat", f"/proc/{pid}/stat"], check=False)
    text = completed.stdout.strip()
    marker = text.rfind(") ")
    if completed.returncode != 0 or marker < 0:
        return None
    fields = text[marker + 2 :].split()
    try:
        return ProcessPin(pid=pid, ppid=int(fields[1]), pgid=int(fields[2]), start_time=int(fields[19]))
    except (IndexError, ValueError):
        return None


def _pin_still_matches(distro: str, expected: ProcessPin) -> bool:
    current = _read_process_pin(distro, expected.pid)
    return current is not None and current.start_time == expected.start_time


def _verified_gpu_residuals(
    server: LaunchedVllmServer,
    captured: dict[int, ProcessPin],
) -> list[int]:
    return [
        pid
        for pid in _gpu_pids(server.distro)
        if pid in captured and _pin_still_matches(server.distro, captured[pid])
    ]


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


def compute_vllm_memory_fit(
    artifact: ModelArtifact,
    *,
    max_model_len: int,
    total_vram_bytes: int,
    gpu_memory_utilization: str,
) -> VllmMemoryFit:
    config_path = artifact.model_file / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("vLLM VRAM preflight requires a valid snapshot config.json") from error
    if not isinstance(config, dict):
        raise RuntimeError("vLLM VRAM preflight requires an object config.json")
    layer_types = config.get("layer_types")
    if isinstance(layer_types, list):
        full_attention_layers = sum(
            1 for value in layer_types if isinstance(value, str) and "full_attention" in value
        )
    else:
        full_attention_layers = _positive_int(config, "num_full_attention_layers")
    kv_heads = _positive_int(config, "num_key_value_heads")
    head_dim_value = config.get("head_dim")
    if isinstance(head_dim_value, int) and not isinstance(head_dim_value, bool) and head_dim_value > 0:
        head_dim = head_dim_value
    else:
        hidden_size = _positive_int(config, "hidden_size")
        attention_heads = _positive_int(config, "num_attention_heads")
        if hidden_size % attention_heads:
            raise RuntimeError("vLLM VRAM preflight cannot derive an integral attention head_dim")
        head_dim = hidden_size // attention_heads
    dtype_bytes = _dtype_bytes(config.get("torch_dtype"))
    if full_attention_layers <= 0:
        raise RuntimeError("vLLM VRAM preflight found no full-attention layers in config.json")
    weights_bytes = sum(
        int(row["size_bytes"])
        for row in artifact.snapshot_files
        if isinstance(row.get("path"), str) and str(row["path"]).endswith(".safetensors")
    )
    kv_bytes = full_attention_layers * kv_heads * head_dim * 2 * dtype_bytes * max_model_len
    utilization = float(gpu_memory_utilization)
    budget_bytes = int(total_vram_bytes * utilization)
    required_bytes = weights_bytes + kv_bytes + VLLM_FIXED_HEADROOM_BYTES
    result = VllmMemoryFit(
        weights_bytes=weights_bytes,
        kv_bytes=kv_bytes,
        headroom_bytes=VLLM_FIXED_HEADROOM_BYTES,
        required_bytes=required_bytes,
        total_vram_bytes=total_vram_bytes,
        gpu_memory_utilization=utilization,
        budget_bytes=budget_bytes,
        fits=required_bytes <= budget_bytes,
    )
    if not result.fits:
        raise RuntimeError(
            "vLLM pre-launch VRAM fit failed: "
            f"weights_bytes={weights_bytes}, kv_bytes={kv_bytes}, "
            f"headroom_bytes={VLLM_FIXED_HEADROOM_BYTES}, required_bytes={required_bytes}, "
            f"budget_bytes={budget_bytes}, total_vram_bytes={total_vram_bytes}, "
            f"gpu_memory_utilization={utilization}"
        )
    return result


def _positive_int(config: dict[str, object], key: str) -> int:
    value = config.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise RuntimeError(f"vLLM VRAM preflight requires positive config field {key}")


def _dtype_bytes(value: object) -> int:
    normalized = str(value).lower().replace("torch.", "")
    sizes = {"float16": 2, "bfloat16": 2, "float32": 4}
    if normalized not in sizes:
        raise RuntimeError(f"vLLM VRAM preflight does not support config torch_dtype={value!r}")
    return sizes[normalized]


def read_live_process_environment(
    server: LaunchedVllmServer,
    name: str,
) -> str | None:
    if not _process_identity_matches(
        server.distro,
        server.leader_pin.pid,
        server.run_token,
        server.expected_executable,
        expected_start_time=server.leader_pin.start_time,
    ):
        return None
    completed = _run_wsl(
        server.distro,
        ["bash", "-lc", f"tr '\\0' '\\n' < /proc/{server.leader_pin.pid}/environ"],
        check=False,
    )
    prefix = f"{name}="
    for line in completed.stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def parse_vllm_startup_log(path: Path) -> VllmLogEvidence:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    deterministic = tuple(
        line.strip()
        for line in text.splitlines()
        if _affirmative_determinism_line(line)
    )
    allocations: JsonObject = {}
    patterns = {
        "weights": r"(?:model\s+weights|weights)[^\n]*?([0-9]+(?:\.[0-9]+)?)\s*(GiB|MiB)",
        "kv_cache": r"(?:KV\s+cache|cache\s+size)[^\n]*?([0-9]+(?:\.[0-9]+)?)\s*(GiB|MiB)",
        "cuda_graph": r"(?:CUDA\s+graph|graph\s+memory)[^\n]*?([0-9]+(?:\.[0-9]+)?)\s*(GiB|MiB)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match is not None:
            allocations[key] = {"value": float(match.group(1)), "unit": match.group(2)}
    failure_match = re.search(
        r"([^\n]*(?:out of memory|insufficient memory|no available memory for the cache)[^\n]*)",
        text,
        re.IGNORECASE,
    )
    return VllmLogEvidence(
        deterministic_kernel_evidence=deterministic,
        deterministic_kernel_enabled=bool(deterministic),
        memory_allocations=allocations,
        fit_failure=failure_match.group(1).strip() if failure_match is not None else None,
    )


def _affirmative_determinism_line(line: str) -> bool:
    relevant = re.search(
        r"batch[ _-]?invariant|deterministic.{0,60}(?:kernel|cutlass|nvfp4)",
        line,
        re.IGNORECASE,
    )
    affirmative = re.search(
        r"\b(?:enabled|active|activated|selected|using)\b.{0,50}\b(?:kernel|cutlass|nvfp4|mode)\b|"
        r"\b(?:kernel|cutlass|nvfp4|mode)\b.{0,50}\b(?:enabled|active|activated|selected|using)\b",
        line,
        re.IGNORECASE,
    )
    negative = re.search(
        r"\b(?:disabled|unavailable|fallback|warning|warn|failed|failure|cannot|unsupported|not enabled)\b",
        line,
        re.IGNORECASE,
    )
    return relevant is not None and affirmative is not None and negative is None


def _cuda_version(output: str) -> str | None:
    marker = "CUDA Version:"
    if marker not in output:
        return None
    value = output.split(marker, 1)[1].strip().split()[0]
    return value.rstrip("|") or None
