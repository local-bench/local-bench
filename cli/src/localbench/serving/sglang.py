from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject
from localbench.serving.model_artifact import ModelArtifact, resolve_snapshot_reference
from localbench.serving.readiness import ReadinessEvidence, verify_sglang_readiness
from localbench.serving.teardown import TeardownEvidence
from localbench.serving.vllm import (
    LaunchedVllmServer,
    ProcessPin,
    _cleanup_by_token,
    _cuda_version,
    _dtype_bytes,
    _positive_int,
    _process_identity_matches,
    _read_process_pin,
    _run_wsl,
    _wait_for_server_pid,
    refresh_vllm_process_ownership,
    teardown_vllm,
)

SGLANG_PINNED_VERSION = "0.5.13"
SGLANG_PINNED_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
SGLANG_CHUNKED_PREFILL_SIZE = 2048
SGLANG_CUDA_GRAPH_MAX_BS = 1


@dataclass(frozen=True, slots=True)
class SglangLaunchConfig:
    distro: str
    python_bin: str
    model_path: str
    model_id: str
    host: str
    port: int
    api_key: str
    ctx: int
    seed: int
    dtype: str
    kv_cache_dtype: str
    mamba_ssm_dtype: str
    quantization: str
    mem_fraction_static: str
    chat_template: str
    run_token: str
    expected_executable: str


@dataclass(frozen=True, slots=True)
class SglangBuildIdentity:
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
    package_tree_sha256: str
    runtime_identity_sha256: str


@dataclass(frozen=True, slots=True)
class SglangMemoryFit:
    weights_bytes: int
    kv_bytes: int
    mamba_state_bytes: int
    static_required_bytes: int
    total_vram_bytes: int
    mem_fraction_static: float
    static_budget_bytes: int
    non_static_required_bytes: int
    non_static_budget_bytes: int
    fits: bool

    def provenance(self) -> JsonObject:
        return {
            "weights_bytes": self.weights_bytes,
            "kv_bytes": self.kv_bytes,
            "mamba_state_bytes": self.mamba_state_bytes,
            "static_required_bytes": self.static_required_bytes,
            "total_vram_bytes": self.total_vram_bytes,
            "mem_fraction_static": self.mem_fraction_static,
            "static_budget_bytes": self.static_budget_bytes,
            "non_static_required_bytes": self.non_static_required_bytes,
            "non_static_budget_bytes": self.non_static_budget_bytes,
            "fits": self.fits,
        }


LaunchedSglangServer = LaunchedVllmServer


class SglangAdapter:
    runtime = "sglang"

    def resolve_model(
        self, ref: str, *, cache_dir: Path, run_dir: Path
    ) -> ModelArtifact:
        return resolve_snapshot_reference(ref, cache_dir=cache_dir, run_dir=run_dir)

    def build_identity(self, *, distro: str, python_bin: str) -> SglangBuildIdentity:
        identity, _help_text = collect_sglang_build_identity(
            distro=distro, python_bin=python_bin
        )
        return identity

    def launch(
        self, config: SglangLaunchConfig, *, log_path: Path
    ) -> LaunchedSglangServer:
        return launch_sglang(config, log_path=log_path)

    async def readiness(self, **kwargs: object) -> ReadinessEvidence:
        return await verify_sglang_readiness(**kwargs)

    def teardown(self, server: LaunchedSglangServer) -> TeardownEvidence:
        result = teardown_vllm(server)
        return TeardownEvidence(
            owned_process_tree=[str(value) for value in result["owned_process_tree"]],
            terminated=result["terminated"] is True,
            exit_code=result["exit_code"]
            if isinstance(result["exit_code"], int)
            else None,
            gpu_pids_after=[int(value) for value in result["gpu_pids_after"]],
            teardown_uncertain=result["teardown_uncertain"] is True,
        )


def sglang_serve_argv(config: SglangLaunchConfig) -> list[str]:
    # All flags below are from the pinned v0.5.13 Server Arguments reference:
    # https://github.com/sgl-project/sglang/blob/v0.5.13/docs/advanced_features/server_arguments.md
    return [
        config.python_bin,
        "-m",
        "sglang.launch_server",
        "--model-path",
        config.model_path,
        "--tokenizer-path",
        config.model_path,
        "--served-model-name",
        config.model_id,
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--api-key",
        config.api_key,
        "--context-length",
        str(config.ctx),
        "--max-running-requests",
        "1",
        "--random-seed",
        str(config.seed),
        "--dtype",
        config.dtype,
        "--kv-cache-dtype",
        config.kv_cache_dtype,
        "--mamba-ssm-dtype",
        config.mamba_ssm_dtype,
        "--quantization",
        config.quantization,
        "--mem-fraction-static",
        config.mem_fraction_static,
        "--load-format",
        "safetensors",
        "--chat-template",
        config.chat_template,
        "--sampling-defaults",
        "openai",
        "--device",
        "cuda",
        "--tp-size",
        "1",
        "--dp-size",
        "1",
        "--chunked-prefill-size",
        str(SGLANG_CHUNKED_PREFILL_SIZE),
        "--disable-radix-cache",
        "--disable-overlap-schedule",
        "--cuda-graph-max-bs",
        str(SGLANG_CUDA_GRAPH_MAX_BS),
        "--attention-backend",
        "triton",
        "--enable-deterministic-inference",
    ]


def validate_sglang_argv(argv: list[str], help_text: str) -> None:
    required = {
        "--model-path",
        "--tokenizer-path",
        "--served-model-name",
        "--host",
        "--port",
        "--api-key",
        "--context-length",
        "--max-running-requests",
        "--random-seed",
        "--dtype",
        "--kv-cache-dtype",
        "--mamba-ssm-dtype",
        "--quantization",
        "--mem-fraction-static",
        "--load-format",
        "--chat-template",
        "--sampling-defaults",
        "--device",
        "--tp-size",
        "--dp-size",
        "--chunked-prefill-size",
        "--disable-radix-cache",
        "--disable-overlap-schedule",
        "--cuda-graph-max-bs",
        "--attention-backend",
        "--enable-deterministic-inference",
    }
    missing = sorted(flag for flag in required if flag not in argv)
    supported = set(re.findall(r"(?<![\w-])--[a-z0-9][a-z0-9-]*", help_text, re.I))
    unsupported = sorted(flag for flag in required if flag not in supported)
    if missing:
        raise RuntimeError(
            f"SGLang strict argv missing required flags: {', '.join(missing)}"
        )
    if unsupported:
        raise RuntimeError(
            f"configured SGLang does not support required flags: {', '.join(unsupported)}"
        )
    if any(token.lower() == "auto" for token in argv):
        raise RuntimeError("SGLang strict argv contains an unresolved auto value")


def collect_sglang_build_identity(
    *, distro: str, python_bin: str
) -> tuple[SglangBuildIdentity, str]:
    interpreter = _run_wsl(distro, ["readlink", "-f", python_bin]).stdout.strip()
    package_version = _run_wsl(
        distro,
        [
            python_bin,
            "-c",
            "import importlib.metadata; print(importlib.metadata.version('sglang'))",
        ],
    ).stdout.strip()
    if package_version != SGLANG_PINNED_VERSION:
        raise RuntimeError(
            f"SGLang maintainer lane requires {SGLANG_PINNED_VERSION}, got {package_version or 'unreported'}"
        )
    help_text = _run_wsl(
        distro, [python_bin, "-m", "sglang.launch_server", "--help"]
    ).stdout
    executable_sha = _run_wsl(distro, ["sha256sum", interpreter]).stdout.split()[0]
    dependency_lock = _run_wsl(
        distro, [python_bin, "-m", "pip", "freeze", "--all"]
    ).stdout
    dependency_lock_sha256 = hashlib.sha256(dependency_lock.encode("utf-8")).hexdigest()
    package_tree_probe = _run_wsl(
        distro,
        [python_bin, "-c", _package_tree_probe_code()],
    ).stdout.strip()
    try:
        package_tree_evidence = json.loads(package_tree_probe)
    except json.JSONDecodeError as error:
        raise RuntimeError("SGLang installed package-tree identity is invalid") from error
    if not isinstance(package_tree_evidence, dict):
        raise RuntimeError("SGLang installed package-tree identity is invalid")
    package_tree_sha256 = package_tree_evidence.get("sha256")
    package_tree_file_count = package_tree_evidence.get("file_count")
    if (
        not isinstance(package_tree_sha256, str)
        or len(package_tree_sha256) != 64
        or not all(char in "0123456789abcdef" for char in package_tree_sha256)
        or not isinstance(package_tree_file_count, int)
        or isinstance(package_tree_file_count, bool)
        or package_tree_file_count <= 0
    ):
        raise RuntimeError("SGLang installed package-tree identity is incomplete")
    runtime_identity_sha256 = hashlib.sha256(
        (
            f"sglang={package_version}\n"
            f"package_tree={package_tree_sha256}\n"
        ).encode("utf-8")
    ).hexdigest()
    gpu = (
        _run_wsl(
            distro,
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
        )
        .stdout.strip()
        .splitlines()
    )
    nvidia_smi = _run_wsl(distro, ["nvidia-smi"]).stdout
    if (
        not interpreter
        or not help_text
        or len(executable_sha) != 64
        or not dependency_lock.strip()
        or not gpu
    ):
        raise RuntimeError("SGLang build identity is incomplete")
    fields = [field.strip() for field in gpu[0].split(",")]
    if len(fields) != 3 or not fields[0] or not fields[1]:
        raise RuntimeError("SGLang GPU/driver identity is incomplete")
    try:
        total_vram_bytes = int(fields[2]) * 1024 * 1024
    except ValueError as error:
        raise RuntimeError("SGLang GPU total-memory identity is invalid") from error
    identity = SglangBuildIdentity(
        executable_sha256=executable_sha,
        version_stdout=package_version,
        help_text_sha256=hashlib.sha256(help_text.encode("utf-8")).hexdigest(),
        device_name=fields[0],
        driver_version=fields[1],
        cuda_version=_cuda_version(nvidia_smi),
        help_text=help_text,
        package_version=package_version,
        dependency_lock_sha256=dependency_lock_sha256,
        expected_executable=interpreter,
        total_vram_bytes=total_vram_bytes,
        package_tree_sha256=package_tree_sha256,
        runtime_identity_sha256=runtime_identity_sha256,
    )
    return identity, help_text


def _package_tree_probe_code() -> str:
    return """\
import hashlib
import importlib.metadata as metadata
import json

distribution = metadata.distribution("sglang")
files = sorted(distribution.files or (), key=lambda value: str(value).replace("\\\\", "/"))
if not files:
    raise SystemExit("sglang distribution records no installed files")
digest = hashlib.sha256()
for relative in files:
    path = distribution.locate_file(relative)
    if not path.is_file():
        raise SystemExit(f"sglang distribution file is missing: {relative}")
    name = str(relative).replace("\\\\", "/").encode("utf-8")
    data = path.read_bytes()
    digest.update(name)
    digest.update(b"\\0")
    digest.update(str(len(data)).encode("ascii"))
    digest.update(b"\\0")
    digest.update(data)
print(json.dumps({"file_count": len(files), "sha256": digest.hexdigest()}, sort_keys=True))
"""


def launch_sglang(
    config: SglangLaunchConfig, *, log_path: Path
) -> LaunchedSglangServer:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    pid_file = f"/tmp/localbench-sglang-{config.run_token}.pid"
    token_executable = f"/tmp/localbench-sglang-{config.run_token}"
    command_argv = sglang_serve_argv(config)
    command_argv[0] = token_executable
    command = " ".join(shlex.quote(token) for token in command_argv)
    inner = (
        f"ln -sf {shlex.quote(config.python_bin)} {shlex.quote(token_executable)}; "
        f"echo $$ > {shlex.quote(pid_file)}; "
        f"export LOCALBENCH_RUN_TOKEN={shlex.quote(config.run_token)} CUDA_VISIBLE_DEVICES=0; "
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
            config.expected_executable,
            expected_start_time=leader_pin.start_time
            if leader_pin is not None
            else None,
        ):
            raise RuntimeError("SGLang launch process identity could not be pinned")
    except BaseException:
        _cleanup_by_token(config.distro, config.run_token, config.expected_executable)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()
        raise
    return LaunchedSglangServer(
        process,
        config.distro,
        server_pid,
        pid_file,
        log_handle,
        config.run_token,
        config.expected_executable,
        token_executable,
        leader_pin,
        {leader_pin.pid: leader_pin},
    )


def refresh_sglang_process_ownership(
    server: LaunchedSglangServer,
) -> tuple[ProcessPin, ...]:
    return refresh_vllm_process_ownership(server)


def quantization_config(artifact: ModelArtifact) -> str:
    if artifact.quant_label != "NVFP4":
        raise RuntimeError(
            "SGLang maintainer lane requires an NVFP4 safetensors snapshot"
        )
    return "compressed-tensors"


def compute_sglang_memory_fit(
    artifact: ModelArtifact,
    *,
    max_model_len: int,
    total_vram_bytes: int,
    mem_fraction_static: str,
) -> SglangMemoryFit:
    config_path = artifact.model_file / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "SGLang VRAM preflight requires a valid snapshot config.json"
        ) from error
    if not isinstance(config, dict):
        raise RuntimeError("SGLang VRAM preflight requires an object config.json")
    model_config = _text_model_config(config)
    layer_types = model_config.get("layer_types")
    if isinstance(layer_types, list):
        full_attention_layers = sum(
            1
            for value in layer_types
            if isinstance(value, str) and "full_attention" in value
        )
    else:
        full_attention_layers = _positive_int(model_config, "num_full_attention_layers")
    kv_heads = _positive_int(model_config, "num_key_value_heads")
    head_dim_value = model_config.get("head_dim")
    if (
        isinstance(head_dim_value, int)
        and not isinstance(head_dim_value, bool)
        and head_dim_value > 0
    ):
        head_dim = head_dim_value
    else:
        hidden_size = _positive_int(model_config, "hidden_size")
        attention_heads = _positive_int(model_config, "num_attention_heads")
        if hidden_size % attention_heads:
            raise RuntimeError(
                "SGLang VRAM preflight cannot derive an integral attention head_dim"
            )
        head_dim = hidden_size // attention_heads
    dtype_bytes = _dtype_bytes(model_config.get("torch_dtype") or model_config.get("dtype"))
    if full_attention_layers <= 0:
        raise RuntimeError(
            "SGLang VRAM preflight found no full-attention layers in config.json"
        )
    weights_bytes = sum(
        int(row["size_bytes"])
        for row in artifact.snapshot_files
        if isinstance(row.get("path"), str)
        and str(row["path"]).endswith(".safetensors")
    )
    kv_bytes = (
        full_attention_layers * kv_heads * head_dim * 2 * dtype_bytes * max_model_len
    )
    mamba_state_bytes = _sglang_mamba_state_bytes(model_config, layer_types)
    fraction = float(mem_fraction_static)
    static_budget_bytes = int(total_vram_bytes * fraction)
    non_static_budget_bytes = total_vram_bytes - static_budget_bytes
    non_static_required_bytes = _sglang_non_static_required_bytes(
        config, total_vram_bytes=total_vram_bytes
    )
    static_required_bytes = weights_bytes + kv_bytes + mamba_state_bytes
    result = SglangMemoryFit(
        weights_bytes=weights_bytes,
        kv_bytes=kv_bytes,
        mamba_state_bytes=mamba_state_bytes,
        static_required_bytes=static_required_bytes,
        total_vram_bytes=total_vram_bytes,
        mem_fraction_static=fraction,
        static_budget_bytes=static_budget_bytes,
        non_static_required_bytes=non_static_required_bytes,
        non_static_budget_bytes=non_static_budget_bytes,
        fits=(
            static_required_bytes <= static_budget_bytes
            and non_static_required_bytes <= non_static_budget_bytes
        ),
    )
    if not result.fits:
        raise RuntimeError(
            "SGLang pre-launch VRAM fit failed: "
            f"weights_bytes={weights_bytes}, kv_bytes={kv_bytes}, "
            f"mamba_state_bytes={mamba_state_bytes}, "
            f"static_required_bytes={static_required_bytes}, "
            f"static_budget_bytes={static_budget_bytes}, "
            f"non_static_required_bytes={non_static_required_bytes}, "
            f"non_static_budget_bytes={non_static_budget_bytes}, "
            f"total_vram_bytes={total_vram_bytes}, "
            f"mem_fraction_static={fraction}"
        )
    return result


def _text_model_config(config: JsonObject) -> JsonObject:
    text_config = config.get("text_config")
    return text_config if isinstance(text_config, dict) else config


def _sglang_mamba_state_bytes(
    config: JsonObject, layer_types: object
) -> int:
    if not isinstance(layer_types, list):
        return 0
    linear_layers = sum(
        1
        for value in layer_types
        if isinstance(value, str) and value in {"linear_attention", "mamba"}
    )
    if linear_layers == 0:
        return 0
    value_head_dim = _positive_int(config, "linear_value_head_dim")
    value_heads = _positive_int(config, "linear_num_value_heads")
    key_heads = _positive_int(config, "linear_num_key_heads")
    key_head_dim = _positive_int(config, "linear_key_head_dim")
    conv_kernel = _positive_int(config, "linear_conv_kernel_dim")
    conv_dim = value_head_dim * value_heads + 2 * key_heads * key_head_dim
    conv_bytes = conv_dim * (conv_kernel - 1) * 2
    ssm_dtype_bytes = _dtype_bytes(config.get("mamba_ssm_dtype") or "float32")
    temporal_bytes = value_heads * value_head_dim * key_head_dim * ssm_dtype_bytes
    # With radix cache disabled and max_running_requests=1, v0.5.13 sets the
    # Mamba cache size to one; MambaPool allocates size + 1 slots.
    return linear_layers * (conv_bytes + temporal_bytes) * 2


def _sglang_non_static_required_bytes(
    config: JsonObject, *, total_vram_bytes: int
) -> int:
    total_mib = total_vram_bytes / 1024**2
    piecewise_graph_sizes = (
        list(range(4, 33, 4))
        + list(range(48, 257, 16))
        + list(range(288, 513, 32))
        + list(range(576, 1025, 64))
        + list(range(1280, SGLANG_CHUNKED_PREFILL_SIZE + 1, 256))
    )
    # Mirrors v0.5.13 ServerArgs._handle_gpu_memory_settings for TP1/PP1:
    # metadata + chunked-prefill activations + CUDA graphs + parallel overhead
    # + piecewise CUDA-graph non-Torch memory. These allocations are outside
    # mem_fraction_static, which covers only weights plus KV/state pools.
    reserved_mib = (
        512
        + max(SGLANG_CHUNKED_PREFILL_SIZE, 2048) * 1.5
        + SGLANG_CUDA_GRAPH_MAX_BS * 2
        + 1024 / 8
        + len(piecewise_graph_sizes) * 8
    )
    if reserved_mib >= total_mib:
        return total_vram_bytes
    auto_static_fraction = round((total_mib - reserved_mib) / total_mib, 3)
    vision_config = config.get("vision_config")
    if isinstance(vision_config, dict):
        layers = vision_config.get("num_hidden_layers", 24)
        hidden = vision_config.get("hidden_size", 1024)
        if not isinstance(layers, int) or isinstance(layers, bool) or layers <= 0:
            layers = 24
        if not isinstance(hidden, int) or isinstance(hidden, bool) or hidden <= 0:
            hidden = 1024
        complexity_ratio = layers * hidden**2 / (24 * 1024**2)
        dynamic_factor = max(0.8, min(1.05, 1.0 - 0.1 * (complexity_ratio - 1.0)))
        auto_static_fraction *= 0.95 * dynamic_factor
    return total_vram_bytes - int(total_vram_bytes * auto_static_fraction)
