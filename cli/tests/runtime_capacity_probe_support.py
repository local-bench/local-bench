from __future__ import annotations

from pathlib import Path
from typing import Final

import httpx

from localbench._types import JsonObject
from localbench.runtime_capacity_probe import verify_llama_cpp_capacity

REQUIRED_CONTEXT: Final = 65_536
STARTUP_LOG: Final = """llama_context: n_seq_max     = 1
llama_context: n_ctx         = 65536
llama_context: n_ctx_seq     = 65536
llama_context: flash_attn    = enabled
llama_kv_cache: size = 12288.00 MiB ( 65536 cells, 47 layers, 1/1 seqs), K (f16): 6144.00 MiB, V (f16): 6144.00 MiB"""
LAUNCH_ARGV: Final = (
    "llama-server.exe",
    "--ctx-size",
    "65536",
    "--parallel",
    "1",
    "--fit",
    "off",
    "--flash-attn",
    "on",
    "--cache-type-k",
    "f16",
    "--cache-type-v",
    "f16",
)


def props_payload() -> JsonObject:
    return {
        "default_generation_settings": {"n_ctx": REQUIRED_CONTEXT},
        "total_slots": 1,
    }


def models_payload() -> JsonObject:
    return {
        "data": [
            {
                "id": "qwen35",
                "meta": {
                    "n_ctx": REQUIRED_CONTEXT,
                    "n_ctx_train": 262_144,
                },
            }
        ]
    }


def slots_payload() -> list[JsonObject]:
    return [{"id": 0, "n_ctx": REQUIRED_CONTEXT}]


def startup_log() -> str:
    return STARTUP_LOG


def launch_argv() -> list[str]:
    return list(LAUNCH_ARGV)


async def run_probe(
    tmp_path: Path,
    *,
    props: JsonObject | list[JsonObject] | None = None,
    models: JsonObject | list[JsonObject] | None = None,
    slots: JsonObject | list[JsonObject] | None = None,
    startup_log: str | None = None,
    stale_startup_log: str = "",
    launch_argv: list[str] | None = None,
    serve_log_start_byte: int | None = None,
    server_pid: int = 4242,
) -> JsonObject:
    responses = {
        "/props": props_payload() if props is None else props,
        "/v1/models": models_payload() if models is None else models,
        "/slots": slots_payload() if slots is None else slots,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses[request.url.path])

    serve_log_path = tmp_path / "serve.log"
    stale_bytes = stale_startup_log.encode("utf-8")
    current_bytes = (STARTUP_LOG if startup_log is None else startup_log).encode("utf-8")
    serve_log_path.write_bytes(stale_bytes + current_bytes)

    return await verify_llama_cpp_capacity(
        base_url="http://llama.test",
        api_key="secret",
        required_context_tokens=REQUIRED_CONTEXT,
        run_dir=tmp_path,
        serve_log_path=serve_log_path,
        serve_log_start_byte=(
            len(stale_bytes) if serve_log_start_byte is None else serve_log_start_byte
        ),
        server_pid=server_pid,
        launch_argv=list(LAUNCH_ARGV) if launch_argv is None else launch_argv,
        transport=httpx.MockTransport(handler),
    )
