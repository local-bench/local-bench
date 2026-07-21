from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

_DLL_PATTERNS: Final = ("ggml*.dll", "llama.dll", "cudart64_*.dll", "cublas64_*.dll")
LLAMA_CPP_REASONING_FORMAT: Final = "deepseek"
CAPPED_THINKING_REASONING_BUDGET: Final = 8192
LlamaCppReasoningMode: TypeAlias = Literal["on", "off"]


@dataclass(frozen=True, slots=True)
class LlamaCppReasoningConfig:
    reasoning: LlamaCppReasoningMode
    reasoning_budget: int | None
    reasoning_format: str = LLAMA_CPP_REASONING_FORMAT


@dataclass(frozen=True, slots=True)
class LlamaCppLaunchConfig:
    server_bin: Path
    model_file: Path
    model_id: str
    host: str
    port: int
    api_key: str
    ctx: int
    seed: int
    threads: int
    threads_batch: int
    run_dir: Path
    flash_attn: str = "on"
    reasoning: LlamaCppReasoningMode = "off"
    reasoning_budget: int | None = None
    reasoning_format: str = LLAMA_CPP_REASONING_FORMAT


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    executable_sha256: str
    dll_or_so_hashes: dict[str, str]
    version_stdout: str
    source_repo: str
    source_commit: str | None
    source_tag: str | None
    build_flags: str
    help_text_sha256: str
    help_text: str
    list_devices_stdout: str
    cuda_version: str | None


def strict_llama_cpp_argv(config: LlamaCppLaunchConfig) -> list[str]:
    if config.reasoning_format == "none":
        raise RuntimeError("strict llama.cpp argv must not use --reasoning-format none")
    argv = [
        str(config.server_bin),
        "--model",
        str(config.model_file.resolve()),
        "--alias",
        config.model_id,
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--api-key",
        config.api_key,
        "--ctx-size",
        str(config.ctx),
        "--n-gpu-layers",
        "999",
        "--device",
        "CUDA0",
        "--main-gpu",
        "0",
        "--split-mode",
        "none",
        "--fit",
        "off",
        "--parallel",
        "1",
        "--no-cont-batching",
        "--flash-attn",
        config.flash_attn,
        "--cache-type-k",
        "f16",
        "--cache-type-v",
        "f16",
        "--cache-ram",
        "0",
        "--ctx-checkpoints",
        "32",
        "--checkpoint-min-step",
        "8192",
        "--no-context-shift",
        "--batch-size",
        "2048",
        "--ubatch-size",
        "512",
        "--threads",
        str(config.threads),
        "--threads-batch",
        str(config.threads_batch),
        "--seed",
        str(config.seed),
        "--jinja",
        "--reasoning",
        config.reasoning,
    ]
    if config.reasoning_budget is not None:
        argv.extend(["--reasoning-budget", str(config.reasoning_budget)])
    argv.extend(
        [
            "--reasoning-format",
            config.reasoning_format,
            "--no-webui",
            "--no-agent",
            "--log-file",
            str(config.run_dir / "serve.log"),
        ],
    )
    return argv


def reconcile_agent_isolation(argv: list[str], help_text: str) -> list[str]:
    """Drop --no-agent for servers that predate the agent feature.

    The strict argv disables server-side agent execution wherever it exists. A
    build whose help exposes no agent surface at all cannot enable it, so the
    isolation the flag enforces holds inherently -- and passing the unknown
    flag would abort server startup. Builds that expose agent flags without a
    --no-agent disable keep the flag in argv and are rejected by
    validate_strict_argv_supported. Provenance is preserved either way: the
    build identity records the full help text and its sha256, and the server
    fingerprint records the argv actually used.
    """
    if "--no-agent" in help_text:
        return argv
    if "--agent" in help_text:
        return argv
    return [token for token in argv if token != "--no-agent"]


def validate_strict_argv_supported(argv: list[str], help_text: str) -> None:
    missing = sorted({token for token in argv if token.startswith("--") and token not in help_text})
    if missing:
        hint = (
            " (use a llama.cpp build that exposes these flags -- mainline b10050+ is known good -- "
            "or, for --no-agent, any build whose help shows no agent feature at all)"
        )
        raise RuntimeError(f"llama-server help does not expose required strict flags: {', '.join(missing)}{hint}")
    auto_values = [token for token in argv if token == "auto"]
    if auto_values:
        raise RuntimeError("strict llama.cpp argv contains forbidden auto value")


def collect_build_identity(
    server_bin: Path,
    *,
    runner: Callable[[list[str]], str] | None = None,
) -> BuildIdentity:
    resolved = server_bin.resolve()
    run = runner or _run_stdout
    version_stdout = run([str(resolved), "--version"]).strip()
    help_text = run([str(resolved), "--help"])
    list_devices_stdout = run([str(resolved), "--list-devices"]).strip()
    return BuildIdentity(
        executable_sha256=_sha256_file(resolved),
        dll_or_so_hashes=_adjacent_runtime_hashes(resolved.parent),
        version_stdout=version_stdout,
        source_repo="ggml-org/llama.cpp",
        source_commit=_first_regex(version_stdout, r"\b[0-9a-f]{8,40}\b"),
        source_tag=_source_tag(version_stdout),
        build_flags=version_stdout,
        help_text_sha256=hashlib.sha256(help_text.encode("utf-8")).hexdigest(),
        help_text=help_text,
        list_devices_stdout=list_devices_stdout,
        cuda_version=_first_regex(list_devices_stdout + "\n" + version_stdout, r"CUDA[\s/]+([0-9.]+)"),
    )


def _run_stdout(argv: list[str]) -> str:
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        env=_identity_env(),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{argv[-1]} failed for llama-server: {completed.stderr.strip()}")
    # llama.cpp prints --version to stderr and --help to stdout; combine so version/build
    # identity (source_commit, source_tag) is captured regardless of which stream it uses.
    return completed.stdout + completed.stderr


def _identity_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")
    return env


def _adjacent_runtime_hashes(directory: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for pattern in _DLL_PATTERNS:
        for path in sorted(directory.glob(pattern)):
            if path.is_file():
                hashes[path.name] = _sha256_file(path)
    return hashes


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_tag(version_stdout: str) -> str | None:
    tagged = _first_regex(version_stdout, r"\bb\d+\b")
    if tagged is not None:
        return tagged
    # Release binaries print "version: 9852 (fd1a05791)" without the bNNNN token;
    # the upstream release tag convention is b<build-number>.
    number = _first_regex(version_stdout, r"version:\s*(\d+)\b")
    return None if number is None else f"b{number}"


def _first_regex(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None
    if match.lastindex:
        return match.group(1)
    return match.group(0)
