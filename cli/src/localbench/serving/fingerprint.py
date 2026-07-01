from __future__ import annotations

import hashlib
import json


def canonical_sha256(value: str | int | float | bool | None | list | dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def server_fingerprint(
    *,
    model_file_sha256: str,
    executable_sha256: str,
    argv: list[str],
    env_allowlist: dict[str, str],
    ctx: int,
    kv_cache_quant: str,
    parallel_slots: int,
    flash_attention: str,
    chat_template_digest: str,
) -> str:
    return canonical_sha256(
        {
            "argv": argv,
            "chat_template_digest": chat_template_digest,
            "ctx": ctx,
            "env_allowlist": env_allowlist,
            "executable_sha256": executable_sha256,
            "flash_attention": flash_attention,
            "kv_cache_quant": kv_cache_quant,
            "model_file_sha256": model_file_sha256,
            "parallel_slots": parallel_slots,
        },
    )
