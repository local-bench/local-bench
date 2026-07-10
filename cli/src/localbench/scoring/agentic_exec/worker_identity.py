from __future__ import annotations

import hashlib
import importlib
import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path
from typing import Final

from localbench._types import JsonObject

_DISTRIBUTION_NAME: Final = "local-bench-ai"
_WORKER_MODULES: Final = (
    "localbench.scoring.agentic_exec.wsl_worker",
    "localbench.scoring.agentic_exec.protocol_c_loop",
    "localbench.scoring.agentic_exec.sandbox",
    "localbench.scoring.agentic_exec.sandbox_protocol",
    "localbench.scoring.agentic_exec.env_host",
)


def worker_implementation_identity() -> JsonObject:
    """Identify the installed distribution and exact worker sources imported from it."""
    try:
        version = metadata.version(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        version = ""
    module_hashes: JsonObject = {}
    for module_name in _WORKER_MODULES:
        module = importlib.import_module(module_name)
        source = getattr(module, "__file__", None)
        if not isinstance(source, str) or not source:
            raise RuntimeError(f"worker identity cannot locate imported module {module_name}")
        module_hashes[module_name] = _file_sha256(Path(source))
    digest_payload = {
        "schema": "localbench.worker-content.v1",
        "modules": module_hashes,
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()
    return {
        "localbench_distribution_version": version,
        "worker_content_sha256": digest,
        "worker_module_sha256": module_hashes,
    }


def _file_sha256(path: Path) -> str:
    source_path = path
    if path.suffix in {".pyc", ".pyo"}:
        try:
            candidate = Path(importlib.util.source_from_cache(str(path)))
        except ValueError:
            candidate = path
        if candidate.is_file():
            source_path = candidate
    # Git checkouts and wheel installs can differ only by CRLF/LF conversion. Hash normalized
    # Python source so equivalent installed implementations compare across Windows and WSL.
    return hashlib.sha256(source_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
