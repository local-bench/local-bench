from __future__ import annotations

import hashlib

import httpx

from localbench._types import JsonObject


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
