"""Online tokenizer-snapshot prefetch, isolated in a child interpreter.

huggingface_hub latches HF_HUB_OFFLINE at import time. The bench process
imports transformers inside an HF_HUB_OFFLINE=1 window
(prompt_rendering.load_hf_chat_template_tokenizer) before any online
acquisition can run, so in-process snapshot_download is permanently offline
once template introspection has executed (observed live 2026-07-30). A fresh
interpreter with the offline pins stripped from its env is the one sanctioned
online moment; the parent's offline posture stays intact.

Wire protocol v1 (treat as an untrusted boundary on the parent side):
  argv    = [repo_id, allow_patterns_json, revision_or_empty]
  stdout  = exactly one sentinel frame:
              LOCALBENCH_HF_PREFETCH_V1 {"status": "ok", "path": "<snapshot dir>"}
              LOCALBENCH_HF_PREFETCH_V1 {"status": "error",
                  "kind": "protocol"|"import"|"auth"|"not_found"|"network"|"other",
                  "message": "..."}
  exit    = 0 for ok, 1 for a structured error frame. Any other combination is
            a protocol violation the parent maps to a fixed curated error.
Frozen/embedded interpreters are unsupported for auto-prefetch (the project
ships a wheel; the parent validates sys.executable before spawning).
"""

from __future__ import annotations

import json
import sys

_SENTINEL = "LOCALBENCH_HF_PREFETCH_V1"


def _snapshot_download(*, repo_id: str, allow_patterns: list[str], revision: str | None) -> str:
    from huggingface_hub import snapshot_download

    return str(snapshot_download(repo_id=repo_id, allow_patterns=allow_patterns, revision=revision))


def _emit(payload: dict[str, str], *, code: int) -> int:
    sys.stdout.write(_SENTINEL + " " + json.dumps(payload) + "\n")
    sys.stdout.flush()
    return code


def main(argv: list[str]) -> int:
    try:
        repo_id = argv[0]
        allow_patterns = json.loads(argv[1])
        revision = argv[2] or None
        if not isinstance(repo_id, str) or not isinstance(allow_patterns, list):
            raise ValueError("argv types")
    except Exception as error:  # noqa: BLE001 - protocol boundary: argv parsing included
        return _emit({"status": "error", "kind": "protocol", "message": f"bad argv: {error}"}, code=1)
    try:
        from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, RepositoryNotFoundError
    except ImportError as error:
        return _emit({"status": "error", "kind": "import", "message": str(error)}, code=1)
    try:
        path = _snapshot_download(repo_id=repo_id, allow_patterns=allow_patterns, revision=revision)
    except GatedRepoError as error:
        return _emit({"status": "error", "kind": "auth", "message": str(error)}, code=1)
    except RepositoryNotFoundError as error:
        return _emit({"status": "error", "kind": "not_found", "message": str(error)}, code=1)
    except HfHubHTTPError as error:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        kind = "auth" if status_code in {401, 403} else "network"
        return _emit({"status": "error", "kind": kind, "message": str(error)}, code=1)
    except Exception as error:  # noqa: BLE001 - protocol boundary: everything becomes a frame
        return _emit(
            {
                "status": "error",
                "kind": "other",
                "message": f"{type(error).__name__}: {error}",
            },
            code=1,
        )
    return _emit({"status": "ok", "path": path}, code=0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
