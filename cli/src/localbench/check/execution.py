from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.check.types import CheckError
from localbench.submissions.canon import sha256_file

LCE_FLAGS: Final = ("-ctk", "f16", "-ctv", "f16", "--fit", "off", "-lv", "4")
_PROFILE_ROOT: Final = Path(os.environ.get("USERPROFILE", str(Path.home())))
DEFAULT_LCE_SERVER_BIN: Final = _PROFILE_ROOT / "llamacpp" / "b10076" / "llama-server.exe"


@dataclass(frozen=True, slots=True)
class LceLaunchConfig:
    model_file: Path
    run_dir: Path
    host: str
    port: int
    api_key: str
    server_bin: Path = DEFAULT_LCE_SERVER_BIN
    model_id: str = "localbench-check"


def lce_server_argv(config: LceLaunchConfig) -> list[str]:
    return [
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
        "32768",
        "--parallel",
        "1",
        "--no-cont-batching",
        "--batch-size",
        "2048",
        "--ubatch-size",
        "512",
        "-ctk",
        "f16",
        "-ctv",
        "f16",
        "--fit",
        "off",
        "--cache-ram",
        "0",
        "--no-context-shift",
        "--seed",
        "1234",
        "--jinja",
        "--reasoning",
        "on",
        "--reasoning-format",
        "deepseek",
        "--no-webui",
        "--no-agent",
        "-lv",
        "4",
        "--log-file",
        str(config.run_dir / "serve.log"),
    ]


def collect_lce_identity(binary_dir: Path, *, backend: str, props: JsonObject, driver: str) -> JsonObject:
    root = binary_dir.resolve()
    server = root / "llama-server.exe"
    if not server.is_file():
        raise CheckError(f"LCE-1 llama-server.exe is missing from {root}")
    binaries: JsonObject = {
        path.name: sha256_file(path)
        for path in sorted(root.iterdir(), key=lambda candidate: candidate.name.lower())
        if path.is_file() and path.suffix.lower() in {".exe", ".dll"}
    }
    template = props.get("chat_template")
    template_sha256 = hashlib.sha256(template.encode()).hexdigest() if isinstance(template, str) else None
    return {
        "backend": backend,
        "batch_size": 1,
        "binaries": binaries,
        "build": "b10076",
        "commit": "305ba51",
        "context_tokens": 32768,
        "cuda_version": "13.3",
        "driver": driver,
        "edition": "LCE-1",
        "effective_server_config": props,
        "flags": list(LCE_FLAGS),
        "prompt_rendering": "cli-owned",
        "prompt_template_sha256": template_sha256,
        "repo_defaults_disabled": True,
        "server_defaults_disabled": True,
    }


def mock_lce_identity() -> JsonObject:
    return {
        "backend": "mock",
        "batch_size": 1,
        "binaries": {},
        "build": "b10076",
        "commit": "305ba51",
        "context_tokens": 32768,
        "cuda_version": "13.3",
        "driver": "mock",
        "edition": "LCE-1",
        "effective_server_config": {"mock": True},
        "flags": list(LCE_FLAGS),
        "prompt_rendering": "cli-owned",
        "prompt_template_sha256": "0" * 64,
        "repo_defaults_disabled": True,
        "runner": "mock",
        "server_defaults_disabled": True,
    }
