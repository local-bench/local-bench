from __future__ import annotations

import hashlib

from localbench.one_shot.types import OneShotArtifact

REV_A = "a" * 40
REV_B = "b" * 40
SHA_A = "1" * 64
MODEL_BYTES = b"GGUF one-shot fixture"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


MODEL_SHA = sha256(MODEL_BYTES)


def one_shot_artifact(
    *,
    repo_id: str = "owner/model-gguf",
    filename: str = "model-q4.gguf",
    revision: str = REV_A,
    quant_label: str = "Q4_K_M",
    sha256: str = SHA_A,
    size_bytes: int = 2048,
    vram_required_gb_8k: float | None = 19.5,
    vram_required_gb_32k: float | None = 22.0,
) -> OneShotArtifact:
    return OneShotArtifact(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
        quant_label=quant_label,
        sha256=sha256,
        size_bytes=size_bytes,
        vram_required_gb_8k=vram_required_gb_8k,
        vram_required_gb_32k=vram_required_gb_32k,
    )


def catalog_with_artifacts(
    *,
    artifacts: list[dict[str, object]],
    runs: list[dict[str, object]] | None = None,
    tokenizer_repo: str = "Qwen/Qwen3.6-27B",
) -> dict[str, object]:
    return {
        "models": [
            {
                "slug": "qwen3-6-27b",
                "catalog_id": "Qwen/Qwen3.6-27B",
                "display_name": "Qwen3.6 27B",
                "family": "Qwen3.6",
                "tokenizer_repo": tokenizer_repo,
                "artifacts": artifacts,
                "runs": runs or [],
            },
        ],
    }
