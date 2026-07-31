from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import httpx
import pytest

from localbench._types import JsonObject
from localbench.runtime_capacity_probe import (
    CAPACITY_PROBE_FILENAME,
    CapacityProbeMismatchError,
    verify_llama_cpp_capacity,
)

_REQUIRED_CONTEXT: Final = 65_536


def _props() -> JsonObject:
    return {
        "default_generation_settings": {"n_ctx": _REQUIRED_CONTEXT},
        "total_slots": 1,
        "cache_type_k": "f16",
        "cache_type_v": "f16",
        "fit": "off",
        "flash_attn": "on",
    }


def _models() -> JsonObject:
    return {
        "data": [
            {
                "id": "qwen35",
                "meta": {
                    "n_ctx": _REQUIRED_CONTEXT,
                    "n_ctx_train": 262_144,
                },
            }
        ]
    }


def _slots() -> list[JsonObject]:
    return [{"id": 0, "n_ctx": _REQUIRED_CONTEXT}]


async def _run_probe(
    tmp_path: Path,
    *,
    props: JsonObject | list[JsonObject] | None = None,
    models: JsonObject | list[JsonObject] | None = None,
    slots: JsonObject | list[JsonObject] | None = None,
) -> JsonObject:
    responses = {
        "/props": _props() if props is None else props,
        "/v1/models": _models() if models is None else models,
        "/slots": _slots() if slots is None else slots,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses[request.url.path])

    return await verify_llama_cpp_capacity(
        base_url="http://llama.test",
        api_key="secret",
        required_context_tokens=_REQUIRED_CONTEXT,
        run_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.anyio
async def test_capacity_probe_accepts_and_persists_live_b10076_evidence(
    tmp_path: Path,
) -> None:
    # Given: live b10076 endpoint evidence for the exact deep-budget allocation.
    # When: the independently named capacity probe validates the runtime.
    evidence = await _run_probe(tmp_path)

    # Then: the accepted runtime facts are returned and persisted for release evidence.
    assert evidence["passed"] is True
    assert evidence["effective"] == {
        "context_tokens": 65_536,
        "model_context_tokens": 65_536,
        "native_context_tokens": 262_144,
        "cache_type_k": "f16",
        "cache_type_v": "f16",
        "fit": "off",
        "flash_attn": "on",
        "total_slots": 1,
        "slot_context_tokens": [65_536],
    }
    persisted = json.loads((tmp_path / CAPACITY_PROBE_FILENAME).read_text())
    assert persisted == evidence


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case", "props", "models", "slots", "failure"),
    [
        (
            "effective context below the contract",
            {**_props(), "default_generation_settings": {"n_ctx": 32_768}},
            _models(),
            _slots(),
            "effective context",
        ),
        (
            "model effective context silently scaled",
            _props(),
            {"data": [{"id": "qwen35", "meta": {"n_ctx": 32_768, "n_ctx_train": 262_144}}]},
            _slots(),
            "model effective context",
        ),
        (
            "native context missing",
            _props(),
            {"data": [{"id": "qwen35", "meta": {"n_ctx": 65_536}}]},
            _slots(),
            "n_ctx_train",
        ),
        (
            "native context too small",
            _props(),
            {"data": [{"id": "qwen35", "meta": {"n_ctx": 65_536, "n_ctx_train": 32_768}}]},
            _slots(),
            "n_ctx_train",
        ),
        (
            "K cache changed",
            {**_props(), "cache_type_k": "q8_0"},
            _models(),
            _slots(),
            "cache_type_k",
        ),
        (
            "V cache missing",
            {key: value for key, value in _props().items() if key != "cache_type_v"},
            _models(),
            _slots(),
            "cache_type_v",
        ),
        (
            "fit enabled",
            {**_props(), "fit": "on"},
            _models(),
            _slots(),
            "fit",
        ),
        (
            "fit auto",
            {**_props(), "fit": "auto"},
            _models(),
            _slots(),
            "fit",
        ),
        (
            "fit unreported",
            {key: value for key, value in _props().items() if key != "fit"},
            _models(),
            _slots(),
            "fit",
        ),
        (
            "slot allocation missing",
            _props(),
            _models(),
            [],
            "slot allocation",
        ),
        (
            "multiple slots",
            {**_props(), "total_slots": 2},
            _models(),
            [{"id": 0, "n_ctx": 65_536}, {"id": 1, "n_ctx": 65_536}],
            "single slot",
        ),
        (
            "slot allocation undersized",
            _props(),
            _models(),
            [{"id": 0, "n_ctx": 32_768}],
            "slot context",
        ),
        (
            "malformed props",
            [],
            _models(),
            _slots(),
            "/props response is not an object",
        ),
        (
            "flash attention unreported",
            {key: value for key, value in _props().items() if key != "flash_attn"},
            _models(),
            _slots(),
            "flash_attn",
        ),
    ],
)
async def test_capacity_probe_fails_closed_on_missing_or_mismatched_runtime_fact(
    tmp_path: Path,
    case: str,
    props: JsonObject | list[JsonObject],
    models: JsonObject | list[JsonObject],
    slots: JsonObject | list[JsonObject],
    failure: str,
) -> None:
    # Given: one malformed or contradictory live runtime fact.
    # When/Then: validation aborts and retains a failed capacity artifact.
    with pytest.raises(CapacityProbeMismatchError, match=failure):
        await _run_probe(tmp_path, props=props, models=models, slots=slots)
    evidence = json.loads((tmp_path / CAPACITY_PROBE_FILENAME).read_text())
    assert evidence["passed"] is False, case
    assert any(failure in reason for reason in evidence["failure_reasons"]), case
