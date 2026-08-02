from __future__ import annotations

from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.check.types import CheckError
from localbench.submissions.canon import sha256_file

LCE_FLAGS: Final = ("-ctk", "f16", "-ctv", "f16", "--fit", "off", "-lv", "4")


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
        "repo_defaults_disabled": True,
        "runner": "mock",
        "server_defaults_disabled": True,
    }
