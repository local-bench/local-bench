from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

import httpx

from localbench._types import JsonObject, JsonValue


def build_probe_evidence(
    *,
    passed: bool,
    requests: JsonObject,
    llama_build: JsonObject,
    props: httpx.Response,
    no_tools: httpx.Response,
    with_tools: httpx.Response,
    completion: httpx.Response,
    no_tools_prompt: str,
    tools_prompt: str,
    client_prompt: str | None,
    raw_template_sha256: str | None,
    prompt_renderer_context_sha256: str,
    request_shape_sha256: str,
    first_mismatch_offset: int | None,
    diagnostic_subcode: str | None,
    no_tools_active: bool,
    tools_active: bool,
    reasoning_present: bool,
    failures: list[str],
) -> JsonObject:
    return {
        "schema": "localbench.runtime_probe.v1",
        "passed": passed,
        "requests": requests,
        "llama_build": llama_build,
        "response_sha256": {
            "props": sha256_bytes(props.content),
            "apply_template_no_tools": sha256_bytes(no_tools.content),
            "apply_template_tools": sha256_bytes(with_tools.content),
            "completion": sha256_bytes(completion.content),
        },
        "prompt_sha256": {
            "no_tools": sha256_text(no_tools_prompt),
            "tools": sha256_text(tools_prompt),
        },
        "renderer_comparison": {
            "raw_template_sha256": raw_template_sha256,
            "client_prompt_sha256": (
                None if client_prompt is None else sha256_text(client_prompt)
            ),
            "client_prompt_length": (
                None if client_prompt is None else len(client_prompt.encode("utf-8"))
            ),
            "server_prompt_sha256": sha256_text(no_tools_prompt),
            "server_prompt_length": len(no_tools_prompt.encode("utf-8")),
            "request_shape_sha256": request_shape_sha256,
            "context_sha256": prompt_renderer_context_sha256,
            "first_mismatch_offset": first_mismatch_offset,
            "diagnostic_subcode": diagnostic_subcode,
        },
        "prompts": {
            "client": client_prompt,
            "server": no_tools_prompt,
            "server_tools": tools_prompt,
        },
        "results": {
            "no_tools_active_think_opener": no_tools_active,
            "tools_active_think_opener": tools_active,
            "reasoning_content_present": reasoning_present,
        },
        "failure_reasons": failures,
    }


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: JsonValue) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256_bytes(canonical)


def contract_probe_evidence(evidence: JsonObject) -> JsonObject:
    return {key: value for key, value in evidence.items() if key != "prompts"}


def apply_template_request(
    messages: Sequence[Mapping[str, JsonValue]],
    chat_template_kwargs: Mapping[str, bool],
    *,
    tools: Sequence[JsonValue] | None = None,
) -> JsonObject:
    payload: JsonObject = {
        "messages": [dict(message) for message in messages],
        "chat_template_kwargs": dict(chat_template_kwargs),
        "add_generation_prompt": True,
    }
    if tools is not None:
        payload["tools"] = list(tools)
    return payload


def first_mismatch_offset(client_prompt: str | None, server_prompt: str) -> int | None:
    if client_prompt is None:
        return None
    client_bytes = client_prompt.encode("utf-8")
    server_bytes = server_prompt.encode("utf-8")
    for offset, (client_byte, server_byte) in enumerate(
        zip(client_bytes, server_bytes, strict=False),
    ):
        if client_byte != server_byte:
            return offset
    if len(client_bytes) != len(server_bytes):
        return min(len(client_bytes), len(server_bytes))
    return None
