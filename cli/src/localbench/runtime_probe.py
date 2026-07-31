"""Authoritative llama.cpp reasoning-profile probe.

Empirically verified on the pinned Windows b10076-305ba519a llama-server:
GET /props, POST /apply-template, and POST /v1/chat/completions all return the
evidence used here. The binary's --help does not advertise /apply-template.
With the Qwopus GGUF and enable_thinking=true, /apply-template ends in an active
``<think>`` opener and a tiny completion returns non-empty reasoning_content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import httpx

from localbench._types import ChatMessage, JsonObject, JsonValue
from localbench.bounded_final_profiles import BoundedFinalProfileRuntime
from localbench.persistence import atomic_write_json
from localbench.prompt_rendering import PromptRenderingError
from localbench.runtime_probe_evidence import (
    apply_template_request,
    build_probe_evidence,
    contract_probe_evidence,
    first_mismatch_offset,
    sha256_json,
    sha256_text,
)

RUNTIME_PROBE_MISMATCH: Final = "runtime_probe_mismatch"
RENDERER_BYTE_MISMATCH: Final = "renderer_byte_mismatch"
RUNTIME_PROBE_FILENAME: Final = "runtime-probe.json"
_THINK_OPEN = re.compile(r"<(?:think|thinking)>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</(?:think|thinking)>", re.IGNORECASE)
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
BEHAVIORAL_PROBE_MAX_TOKENS: Final = 16
_LIMITS = httpx.Limits(
    max_connections=8,
    max_keepalive_connections=4,
    keepalive_expiry=30.0,
)
_MESSAGES: Final[list[ChatMessage]] = [
    {"role": "user", "content": "Reply with one short word."},
]
_TOOLS: Final[list[JsonValue]] = [
    {
        "type": "function",
        "function": {
            "name": "probe_tool",
            "description": "Runtime probe tool.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }
]


@dataclass(frozen=True, slots=True)
class RuntimeProbeMismatchError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return f"{RUNTIME_PROBE_MISMATCH}: {self.detail}"


@dataclass(frozen=True, slots=True)
class RuntimeProbePayloadError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


async def verify_llama_cpp_runtime_profile(
    *,
    base_url: str,
    model_id: str,
    api_key: str,
    runtime: BoundedFinalProfileRuntime,
    llama_build: JsonObject,
    run_dir: Path,
) -> BoundedFinalProfileRuntime:
    """Probe the launched server and bind successful behavior to the contract."""
    kwargs = dict(runtime.contract.chat_template_kwargs)
    request_record: JsonObject = {
        "model_id": model_id,
        "messages": _MESSAGES,
        "tools": _TOOLS,
        "chat_template_kwargs": kwargs,
        "completion_max_tokens": BEHAVIORAL_PROBE_MAX_TOKENS,
    }
    try:
        transport = httpx.AsyncHTTPTransport(retries=3, limits=_LIMITS)
        async with httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_TIMEOUT,
            transport=transport,
            follow_redirects=True,
        ) as client:
            props = await client.get("/props")
            props.raise_for_status()
            no_tools = await _apply_template(client, kwargs, include_tools=False)
            with_tools = await _apply_template(client, kwargs, include_tools=True)
            completion = await _completion(client, model_id, kwargs)
        no_tools_prompt = _required_prompt(no_tools)
        tools_prompt = _required_prompt(with_tools)
        reasoning_content = _reasoning_content(completion)
        no_tools_active = _has_active_think_opener(no_tools_prompt)
        tools_active = _has_active_think_opener(tools_prompt)
        reasoning_present = reasoning_content not in (None, "")
        failures = _probe_failures(
            reasoning_mode=runtime.contract.reasoning_mode,
            no_tools_active=no_tools_active,
            tools_active=tools_active,
            reasoning_present=reasoning_present,
        )
        client_prompt = (
            None
            if runtime.prompt_renderer is None
            else runtime.prompt_renderer.render(_MESSAGES)
        )
        mismatch_offset = first_mismatch_offset(client_prompt, no_tools_prompt)
        diagnostic_subcode = (
            RENDERER_BYTE_MISMATCH if mismatch_offset is not None else None
        )
        if diagnostic_subcode is not None:
            failures.append(
                f"{diagnostic_subcode}: client/server prompt bytes first differ at "
                f"offset {mismatch_offset}",
            )
        evidence = build_probe_evidence(
            passed=not failures,
            requests=request_record,
            llama_build=llama_build,
            props=props,
            no_tools=no_tools,
            with_tools=with_tools,
            completion=completion,
            no_tools_prompt=no_tools_prompt,
            tools_prompt=tools_prompt,
            client_prompt=client_prompt,
            raw_template_sha256=runtime.contract.raw_template_sha256,
            prompt_renderer_context_sha256=(
                runtime.contract.prompt_renderer_context_sha256
            ),
            request_shape_sha256=sha256_json(
                apply_template_request(_MESSAGES, kwargs),
            ),
            first_mismatch_offset=mismatch_offset,
            diagnostic_subcode=diagnostic_subcode,
            no_tools_active=no_tools_active,
            tools_active=tools_active,
            reasoning_present=reasoning_present,
            failures=failures,
        )
    except (
        httpx.HTTPError,
        PromptRenderingError,
        RuntimeProbePayloadError,
        KeyError,
        IndexError,
        TypeError,
    ) as error:
        evidence = {
            "schema": "localbench.runtime_probe.v1",
            "passed": False,
            "requests": request_record,
            "llama_build": llama_build,
            "failure_reasons": [f"probe endpoint evidence unavailable: {error}"],
        }
        atomic_write_json(evidence, run_dir / RUNTIME_PROBE_FILENAME)
        raise RuntimeProbeMismatchError(str(evidence["failure_reasons"][0])) from error
    atomic_write_json(evidence, run_dir / RUNTIME_PROBE_FILENAME)
    if failures:
        raise RuntimeProbeMismatchError("; ".join(failures))
    effective_sha = sha256_text(no_tools_prompt)
    contract = replace(
        runtime.contract,
        effective_template_sha256=effective_sha,
        runtime_probe=contract_probe_evidence(evidence),
    )
    return replace(runtime, contract=contract)


async def _apply_template(
    client: httpx.AsyncClient,
    kwargs: dict[str, bool],
    *,
    include_tools: bool,
) -> httpx.Response:
    payload = apply_template_request(
        _MESSAGES,
        kwargs,
        tools=_TOOLS if include_tools else None,
    )
    response = await client.post("/apply-template", json=payload)
    response.raise_for_status()
    return response


async def _completion(
    client: httpx.AsyncClient,
    model_id: str,
    kwargs: dict[str, bool],
) -> httpx.Response:
    payload: JsonObject = {
        "model": model_id,
        "messages": _MESSAGES,
        "max_tokens": BEHAVIORAL_PROBE_MAX_TOKENS,
        "temperature": 0,
        "seed": 0,
        "chat_template_kwargs": kwargs,
    }
    response = await client.post("/v1/chat/completions", json=payload)
    response.raise_for_status()
    return response


def _required_prompt(response: httpx.Response) -> str:
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeProbePayloadError("/apply-template response is not an object")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        raise RuntimeProbePayloadError("/apply-template response omitted prompt")
    return prompt


def _reasoning_content(response: httpx.Response) -> str | None:
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeProbePayloadError("completion response is not an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeProbePayloadError("completion response omitted choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeProbePayloadError("completion choice is not an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeProbePayloadError("completion choice omitted message")
    value = message.get("reasoning_content")
    if value is not None and not isinstance(value, str):
        raise RuntimeProbePayloadError("completion reasoning_content is not text")
    return value


def _has_active_think_opener(prompt: str) -> bool:
    openers = tuple(_THINK_OPEN.finditer(prompt))
    if not openers:
        return False
    closers = tuple(_THINK_CLOSE.finditer(prompt))
    return not closers or openers[-1].start() > closers[-1].start()


def _probe_failures(
    *,
    reasoning_mode: str,
    no_tools_active: bool,
    tools_active: bool,
    reasoning_present: bool,
) -> list[str]:
    failures: list[str] = []
    expected_active = reasoning_mode == "generic_think"
    if no_tools_active != expected_active:
        failures.append("no-tools applied template contradicted the resolved reasoning mode")
    if tools_active != no_tools_active:
        failures.append("tools template variant changed reasoning semantics")
    if reasoning_present != expected_active:
        failures.append("completion reasoning_content contradicted the resolved reasoning mode")
    return failures
