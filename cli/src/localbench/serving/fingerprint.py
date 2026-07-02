from __future__ import annotations

import hashlib
import json


EPHEMERAL_TOKEN = "<EPHEMERAL>"


def canonical_sha256(value: str | int | float | bool | None | list | dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_ephemeral_argv(argv: list[str]) -> list[str]:
    normalized = list(argv)
    for index, token in enumerate(normalized[:-1]):
        if token == "--port":
            normalized[index + 1] = EPHEMERAL_TOKEN
    return normalized


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


def resume_identity(
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
    return server_fingerprint(
        model_file_sha256=model_file_sha256,
        executable_sha256=executable_sha256,
        argv=normalize_ephemeral_argv(argv),
        env_allowlist=env_allowlist,
        ctx=ctx,
        kv_cache_quant=kv_cache_quant,
        parallel_slots=parallel_slots,
        flash_attention=flash_attention,
        chat_template_digest=chat_template_digest,
    )
