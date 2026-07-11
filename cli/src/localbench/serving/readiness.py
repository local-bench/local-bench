from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
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
    total_slots: int | None
    model_path: str | None
    chat_template: str | None
    build_info: str | None
    resolved_runtime: JsonObject | None = None


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
    async with httpx.AsyncClient(
        timeout=10.0, transport=transport, headers=headers
    ) as client:
        health_200_at = await _wait_for_health(
            client,
            root,
            startup_timeout_seconds=startup_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        models = await _get_json(client, f"{root}/v1/models")
        reported_model = _reported_model(models, model_id)
        if reported_model != model_id:
            raise ReadinessError(
                f"/v1/models did not report requested model {model_id}"
            )
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
        tokenized = await _post_json(
            client, f"{root}/tokenize", {"content": "localbench readiness"}
        )
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


async def verify_vllm_readiness(
    *,
    base_url: str,
    model_id: str,
    pinned_chat_template_sha256: str,
    api_key: str,
    seed: int,
    transport: httpx.AsyncBaseTransport | None = None,
    startup_timeout_seconds: float = 180.0,
    poll_interval_seconds: float = 0.25,
) -> ReadinessEvidence:
    root = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(
        timeout=10.0, transport=transport, headers=headers
    ) as client:
        health_200_at = await _wait_for_health(
            client,
            root,
            startup_timeout_seconds=startup_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            runtime="vLLM",
        )
        models = await _get_json(client, f"{root}/v1/models")
        reported_model = _reported_model(models, model_id)
        if reported_model != model_id:
            raise ReadinessError(
                f"/v1/models did not report requested model {model_id}"
            )
        version = await _get_json(client, f"{root}/version")
        engine_version = _optional_text(version.get("version"))
        if engine_version is None or _version_tuple(engine_version) < (0, 24):
            raise ReadinessError(
                f"vLLM server version must be >= 0.24, got {engine_version or 'unreported'}"
            )
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
        probe_messages: list[JsonObject] = [
            {"role": "system", "content": "localbench template identity"},
            {"role": "user", "content": "probe"},
        ]
        tokenized = await _post_json(
            client,
            f"{root}/tokenize",
            {"model": model_id, "messages": probe_messages},
        )
        model_path = _vllm_model_path(models, model_id)
        return ReadinessEvidence(
            health_200_at=health_200_at,
            models_response_sha256=canonical_sha256(models),
            props_response_sha256=canonical_sha256(version),
            reported_model=reported_model,
            smoke_chat_sha256=canonical_sha256(smoke),
            tokenize_sha256=canonical_sha256(tokenized),
            # vLLM 0.24 rejects request-level templates by default. The served template is
            # pinned at launch with --chat-template; this digest is the Merkle-covered file.
            apply_template_sha256=pinned_chat_template_sha256,
            total_slots=None,
            model_path=model_path,
            chat_template=None,
            build_info=engine_version,
        )


async def verify_sglang_readiness(
    *,
    base_url: str,
    model_id: str,
    model_path: str,
    chat_template: str,
    pinned_chat_template_sha256: str,
    api_key: str,
    seed: int,
    ctx: int,
    dtype: str,
    kv_cache_dtype: str,
    mamba_ssm_dtype: str,
    quantization: str,
    mem_fraction_static: str,
    local_snapshot_path: Path,
    local_token_ids_renderer: Callable[[Path, list[JsonObject]], list[int]] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    startup_timeout_seconds: float = 180.0,
    poll_interval_seconds: float = 0.25,
) -> ReadinessEvidence:
    """Verify only facts exposed by stock SGLang v0.5.13 endpoints.

    Endpoint contracts are defined by the pinned source at:
    https://github.com/sgl-project/sglang/blob/v0.5.13/python/sglang/srt/entrypoints/http_server.py
    """
    root = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(
        timeout=10.0, transport=transport, headers=headers
    ) as client:
        health_200_at = await _wait_for_health(
            client,
            root,
            startup_timeout_seconds=startup_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            runtime="SGLang",
        )
        models = await _get_json(client, f"{root}/v1/models")
        reported_model = _reported_model(models, model_id)
        if reported_model != model_id:
            raise ReadinessError(
                f"/v1/models did not report requested model {model_id}"
            )
        model_info = await _get_json(client, f"{root}/model_info")
        server_info = await _get_json(client, f"{root}/server_info")
        reported_path = _optional_text(model_info.get("model_path"))
        if reported_path != model_path:
            raise ReadinessError(
                f"SGLang /model_info model_path mismatch: {reported_path or 'unreported'}"
            )
        expected: JsonObject = {
            "model_path": model_path,
            "tokenizer_path": model_path,
            "served_model_name": model_id,
            "chat_template": chat_template,
            "context_length": ctx,
            "max_running_requests": 1,
            "random_seed": seed,
            "dtype": dtype,
            "kv_cache_dtype": kv_cache_dtype,
            "mamba_ssm_dtype": mamba_ssm_dtype,
            "quantization": quantization,
            "mem_fraction_static": float(mem_fraction_static),
            "load_format": "safetensors",
            "sampling_defaults": "openai",
            "device": "cuda",
            "tp_size": 1,
            "dp_size": 1,
            "chunked_prefill_size": 2048,
            "disable_radix_cache": True,
            "disable_overlap_schedule": True,
            "cuda_graph_max_bs": 1,
            "attention_backend": "triton",
            "enable_deterministic_inference": True,
        }
        mismatches = [
            f"{key}={server_info.get(key)!r} (expected {value!r})"
            for key, value in expected.items()
            if server_info.get(key) != value
        ]
        if mismatches:
            raise ReadinessError(
                "SGLang /server_info resolved-config mismatch: " + "; ".join(mismatches)
            )
        engine_version = _optional_text(server_info.get("version"))
        if engine_version != "0.5.13":
            raise ReadinessError(
                f"SGLang server version must be 0.5.13, got {engine_version or 'unreported'}"
            )
        max_total_num_tokens = server_info.get("max_total_num_tokens")
        if (
            not isinstance(max_total_num_tokens, int)
            or isinstance(max_total_num_tokens, bool)
            or max_total_num_tokens < ctx
        ):
            raise ReadinessError(
                "SGLang /server_info max_total_num_tokens must cover the configured context: "
                f"got {max_total_num_tokens!r}, need at least {ctx}"
            )
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
        probe_messages: list[JsonObject] = [
            {"role": "system", "content": "localbench template identity"},
            {"role": "user", "content": "probe"},
        ]
        tokenized = await _post_json(
            client,
            f"{root}/v1/tokenize",
            {"model": model_id, "messages": probe_messages},
        )
        local_template_path = local_snapshot_path / "chat_template.jinja"
        if _sha256_file(local_template_path) != pinned_chat_template_sha256:
            raise ReadinessError(
                "SGLang local chat template changed after snapshot identity was recorded"
            )
        renderer = local_token_ids_renderer or _render_snapshot_chat_token_ids
        expected_token_ids = renderer(local_snapshot_path, probe_messages)
        reported_token_ids = _token_ids(tokenized)
        if reported_token_ids != expected_token_ids:
            raise ReadinessError(
                "SGLang /v1/tokenize token IDs do not match the pinned snapshot template/tokenizer"
            )
        resolved = {key: server_info[key] for key in expected}
        resolved["version"] = engine_version
        resolved["max_total_num_tokens"] = max_total_num_tokens
        return ReadinessEvidence(
            health_200_at=health_200_at,
            models_response_sha256=canonical_sha256(models),
            props_response_sha256=canonical_sha256(server_info),
            reported_model=reported_model,
            smoke_chat_sha256=canonical_sha256(smoke),
            tokenize_sha256=canonical_sha256(tokenized),
            apply_template_sha256=pinned_chat_template_sha256,
            total_slots=1,
            model_path=reported_path,
            chat_template=chat_template,
            build_info=engine_version,
            resolved_runtime=resolved,
        )


async def _wait_for_health(
    client: httpx.AsyncClient,
    root: str,
    *,
    startup_timeout_seconds: float,
    poll_interval_seconds: float,
    runtime: str = "llama.cpp",
) -> str:
    deadline = time.monotonic() + startup_timeout_seconds
    while time.monotonic() <= deadline:
        try:
            response = await client.get(f"{root}/health")
        except httpx.TransportError:
            # SGLang writes its launcher PID before the engine subprocesses finish
            # loading and Uvicorn begins listening. Connection refusals/timeouts are
            # therefore expected during startup and consume the same readiness window
            # as HTTP 503 responses.
            await anyio.sleep(poll_interval_seconds)
            continue
        if response.status_code == 200:
            return utc_now()
        if response.status_code != 503:
            raise ReadinessError(f"/health returned {response.status_code}")
        await anyio.sleep(poll_interval_seconds)
    raise ReadinessError(f"{runtime} readiness timed out")


async def _get_json(client: httpx.AsyncClient, url: str) -> JsonObject:
    response = await client.get(url)
    if response.status_code >= 400:
        raise ReadinessError(f"{url} returned {response.status_code}")
    return _response_object(response)


async def _post_json(
    client: httpx.AsyncClient, url: str, payload: JsonObject
) -> JsonObject:
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


def _vllm_model_path(data: JsonObject, requested: str) -> str | None:
    models = data.get("data")
    if not isinstance(models, list):
        return None
    for row in models:
        if isinstance(row, dict) and row.get("id") == requested:
            for key in ("root", "model_path"):
                if isinstance(row.get(key), str):
                    return str(row[key])
    return None


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", value)
    if match is None:
        return ()
    return tuple(int(part) for part in match.groups(default="0"))


def _render_snapshot_chat_token_ids(
    snapshot_path: Path, messages: list[JsonObject]
) -> list[int]:
    template_path = snapshot_path / "chat_template.jinja"
    try:
        template = template_path.read_text(encoding="utf-8")
        from transformers import AutoTokenizer  # noqa: PLC0415

        tokenizer = AutoTokenizer.from_pretrained(snapshot_path, local_files_only=True)
        rendered = tokenizer.apply_chat_template(
            messages,
            chat_template=template,
            tokenize=True,
            add_generation_prompt=True,
        )
    except (ImportError, OSError, TypeError, ValueError) as error:
        raise ReadinessError(
            "SGLang pinned snapshot template/tokenizer could not be rendered locally"
        ) from error
    if not isinstance(rendered, list) or any(
        not isinstance(value, int) or isinstance(value, bool) for value in rendered
    ):
        raise ReadinessError(
            "SGLang pinned snapshot template/tokenizer returned invalid token IDs"
        )
    return rendered


def _token_ids(payload: JsonObject) -> list[int]:
    values = payload.get("tokens")
    if not isinstance(values, list) or any(
        not isinstance(value, int) or isinstance(value, bool) for value in values
    ):
        raise ReadinessError("SGLang /v1/tokenize returned invalid token IDs")
    return values


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
