from __future__ import annotations

import hashlib
import json
import socket
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx2
import typer
from pydantic import JsonValue, TypeAdapter
from transformers import PreTrainedTokenizerBase

JSON_VALUE = TypeAdapter(JsonValue)
TEMPLATE_KWARGS = TypeAdapter(dict[str, bool])
_LIMITS = httpx2.Limits(
    max_connections=200,
    max_keepalive_connections=40,
    keepalive_expiry=30.0,
)
_TIMEOUT = httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
_SOCKET_OPTIONS: Final[list[tuple[int, int, int]]] = [
    (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
]


@dataclass(frozen=True, slots=True)
class Config:
    suite_cache: Path
    agentic_trace: Path
    hf_tokenizer: str
    revision: str
    llama_url: str
    out: Path
    tier: str
    samples: int
    template_kwargs: dict[str, bool]


@dataclass(frozen=True, slots=True)
class RenderCase:
    name: str
    messages: list[dict[str, JsonValue]]
    tools: list[JsonValue] | None = None
    add_generation_prompt: bool = True
    continue_final_message: bool = False


@dataclass(frozen=True, slots=True)
class Rendered:
    prompt: str
    tokens: list[int]


@dataclass(frozen=True, slots=True)
class CaseResult:
    name: str
    passed: bool
    hf_bytes_sha256: str
    llama_bytes_sha256: str
    hf_token_ids_sha256: str
    llama_token_ids_sha256: str
    byte_mismatch_at: int | None
    token_mismatch_at: int | None


class HarnessError(RuntimeError):
    pass


def _log_request(request: httpx2.Request) -> None:
    request.extensions["request_start"] = time.perf_counter()


def _log_response(response: httpx2.Response) -> None:
    started = response.request.extensions.get("request_start")
    elapsed = time.perf_counter() - started if isinstance(started, float) else 0.0
    typer.echo(
        f"HTTP {response.request.method} {response.request.url.path} "
        f"{response.status_code} {elapsed:.3f}s",
        err=True,
    )


def create_client(config: Config) -> httpx2.Client:
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=_LIMITS,
        socket_options=_SOCKET_OPTIONS,
    )
    return httpx2.Client(
        base_url=config.llama_url,
        transport=transport,
        timeout=_TIMEOUT,
        follow_redirects=True,
        event_hooks={"request": [_log_request], "response": [_log_response]},
    )


def hf_render(
    tokenizer: PreTrainedTokenizerBase,
    case: RenderCase,
    kwargs: dict[str, bool],
) -> Rendered:
    prompt = tokenizer.apply_chat_template(
        case.messages,
        tools=case.tools,
        tokenize=False,
        add_generation_prompt=case.add_generation_prompt,
        continue_final_message=case.continue_final_message,
        **kwargs,
    )
    if not isinstance(prompt, str):
        raise HarnessError(f"{case.name}: HF renderer did not return text")
    return Rendered(prompt, tokenizer.encode(prompt, add_special_tokens=False))


def llama_render(
    client: httpx2.Client,
    case: RenderCase,
    kwargs: dict[str, bool],
) -> Rendered:
    payload: dict[str, JsonValue] = {
        "messages": case.messages,
        "add_generation_prompt": case.add_generation_prompt,
        "continue_final_message": case.continue_final_message,
        "chat_template_kwargs": kwargs,
    }
    if case.tools is not None:
        payload["tools"] = case.tools
    response = client.post("/apply-template", json=payload)
    response.raise_for_status()
    applied = JSON_VALUE.validate_json(response.content)
    if not isinstance(applied, dict) or not isinstance(applied.get("prompt"), str):
        raise HarnessError(f"{case.name}: /apply-template omitted prompt")
    prompt = applied["prompt"]
    response = client.post(
        "/tokenize",
        json={"content": prompt, "add_special": False, "parse_special": True},
    )
    response.raise_for_status()
    token_payload = JSON_VALUE.validate_json(response.content)
    tokens = token_payload.get("tokens") if isinstance(token_payload, dict) else None
    if not isinstance(tokens, list) or not all(
        isinstance(token, int) and not isinstance(token, bool) for token in tokens
    ):
        raise HarnessError(f"{case.name}: /tokenize omitted integer tokens")
    return Rendered(prompt, list(tokens))


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_tokens(tokens: list[int]) -> str:
    return _digest_bytes(json.dumps(tokens, separators=(",", ":")).encode())


def _first_mismatch(left: Sequence[int], right: Sequence[int]) -> int | None:
    for index, pair in enumerate(zip(left, right, strict=False)):
        if pair[0] != pair[1]:
            return index
    return None if len(left) == len(right) else min(len(left), len(right))


def compare(hf: Rendered, llama: Rendered, name: str) -> CaseResult:
    hf_bytes = hf.prompt.encode()
    llama_bytes = llama.prompt.encode()
    return CaseResult(
        name=name,
        passed=hf_bytes == llama_bytes and hf.tokens == llama.tokens,
        hf_bytes_sha256=_digest_bytes(hf_bytes),
        llama_bytes_sha256=_digest_bytes(llama_bytes),
        hf_token_ids_sha256=_digest_tokens(hf.tokens),
        llama_token_ids_sha256=_digest_tokens(llama.tokens),
        byte_mismatch_at=_first_mismatch(hf_bytes, llama_bytes),
        token_mismatch_at=_first_mismatch(hf.tokens, llama.tokens),
    )
