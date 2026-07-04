from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import anyio
import httpx

from localbench._requests import utc_now
from localbench._types import JsonObject, JsonValue
from localbench.serving.fingerprint import canonical_sha256


@dataclass(frozen=True, slots=True)
class ReadinessError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ReadinessEvidence:
    health_200_at: str
    models_response_sha256: str
    props_response_sha256: str
    reported_model: str
    smoke_chat_sha256: str
    tokenize_sha256: str
    apply_template_sha256: str
    total_slots: int
    model_path: str
    chat_template: str | None
    build_info: str | None


async def verify_llama_cpp_readiness(
    *,
    base_url: str,
    model_id: str,
    model_file: Path,
    api_key: str,
    seed: int,
    transport: httpx.AsyncBaseTransport | None = None,
    startup_timeout_seconds: float = 180.0,
    poll_interval_seconds: float = 0.25,
) -> ReadinessEvidence:
    root = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=10.0, transport=transport, headers=headers) as client:
        health_200_at = await _wait_for_health(
            client,
            root,
            startup_timeout_seconds=startup_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        models = await _get_json(client, f"{root}/v1/models")
        reported_model = _reported_model(models, model_id)
        if reported_model != model_id:
            raise ReadinessError(f"/v1/models did not report requested model {model_id}")
        props = await _get_json(client, f"{root}/props")
        total_slots = _int_field(props, "total_slots")
        if total_slots != 1:
            raise ReadinessError(f"llama.cpp total_slots must be 1, got {total_slots}")
        model_path = _text_field(props, "model_path")
        if Path(model_path).resolve() != model_file.resolve():
            raise ReadinessError(f"llama.cpp model_path mismatch: {model_path}")
        smoke = await _post_json(
            client,
            f"{root}/v1/chat/completions",
            {
                "model": model_id,
                "messages": [{"role": "user", "content": "localbench readiness"}],
                "max_tokens": 1,
                "temperature": 0,
                "top_k": 1,
                "seed": seed,
            },
        )
        tokenized = await _post_json(client, f"{root}/tokenize", {"content": "localbench readiness"})
        templated = await _post_json(
            client,
            f"{root}/apply-template",
            {"messages": [{"role": "user", "content": "localbench readiness"}]},
        )
        return ReadinessEvidence(
            health_200_at=health_200_at,
            models_response_sha256=canonical_sha256(models),
            props_response_sha256=canonical_sha256(props),
            reported_model=reported_model,
            smoke_chat_sha256=canonical_sha256(smoke),
            tokenize_sha256=canonical_sha256(tokenized),
            apply_template_sha256=canonical_sha256(templated),
            total_slots=total_slots,
            model_path=model_path,
            chat_template=_optional_text(props.get("chat_template")),
            build_info=_optional_text(props.get("build_info")),
        )


async def _wait_for_health(
    client: httpx.AsyncClient,
    root: str,
    *,
    startup_timeout_seconds: float,
    poll_interval_seconds: float,
) -> str:
    deadline = time.monotonic() + startup_timeout_seconds
    while time.monotonic() <= deadline:
        response = await client.get(f"{root}/health")
        if response.status_code == 200:
            return utc_now()
        if response.status_code != 503:
            raise ReadinessError(f"/health returned {response.status_code}")
        await anyio.sleep(poll_interval_seconds)
    raise ReadinessError("llama.cpp readiness timed out")


async def _get_json(client: httpx.AsyncClient, url: str) -> JsonObject:
    response = await client.get(url)
    if response.status_code >= 400:
        raise ReadinessError(f"{url} returned {response.status_code}")
    return _response_object(response)


async def _post_json(client: httpx.AsyncClient, url: str, payload: JsonObject) -> JsonObject:
    response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise ReadinessError(f"{url} returned {response.status_code}")
    return _response_object(response)


def _response_object(response: httpx.Response) -> JsonObject:
    try:
        data = response.json()
    except json.JSONDecodeError as error:
        raise ReadinessError("readiness endpoint returned invalid JSON") from error
    if isinstance(data, dict):
        return data
    raise ReadinessError("readiness endpoint returned non-object JSON")


def _reported_model(data: JsonObject, requested: str) -> str:
    models = data.get("data")
    if not isinstance(models, list):
        raise ReadinessError("/v1/models response missing data list")
    first: str | None = None
    for row in models:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id")
        if not isinstance(model_id, str):
            continue
        if model_id == requested:
            return model_id
        if first is None:
            first = model_id
    if first is not None:
        return first
    raise ReadinessError("/v1/models response contained no model ids")


def _int_field(data: JsonObject, key: str) -> int:
    value = data.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ReadinessError(f"/props field {key} is not an integer")


def _text_field(data: JsonObject, key: str) -> str:
    value = data.get(key)
    if isinstance(value, str):
        return value
    raise ReadinessError(f"/props field {key} is not text")


def _optional_text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None
