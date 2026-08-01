from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.runtime_capacity_probe import (
    CAPACITY_PROBE_FILENAME,
    CapacityProbeMismatchError,
)
from runtime_capacity_probe_support import (
    launch_argv as _launch_argv,
    models_payload as _models,
    props_payload as _props,
    run_probe as _run_probe,
    slots_payload as _slots,
    startup_log as _startup_log,
)


@pytest.mark.anyio
async def test_capacity_probe_accepts_stock_b10076_endpoints_and_startup_log(
    tmp_path: Path,
) -> None:
    # Given: stock b10076 endpoints, its managed startup log, and canonical launch argv.
    # When: the independently named capacity probe validates the runtime.
    evidence = await _run_probe(tmp_path)

    # Then: the accepted runtime facts are returned and persisted for release evidence.
    assert evidence["passed"] is True
    assert evidence["effective"] == {
        "context_tokens": 65_536,
        "model_context_tokens": 65_536,
        "native_context_tokens": 262_144,
        "logged_context_tokens": 65_536,
        "logged_slot_context_tokens": 65_536,
        "logged_parallel_slots": 1,
        "cache_type_k": "f16",
        "cache_type_v": "f16",
        "fit": "off",
        "flash_attn": "enabled",
        "total_slots": 1,
        "slot_context_tokens": [65_536],
    }
    assert len(str(evidence["startup_log_sha256"])) == 64
    assert evidence["startup_log_source"] == {
        "process_pid": 4242,
        "process_executable_path": "C:/tools/llama-server.exe",
        "process_commandline_sha256": "a" * 64,
        "process_birth_token": "134300000000000001",
        "identity_verified_before_probe": True,
        "identity_verified_after_probe": True,
        "listener_owner_pid_before_probe": 4242,
        "listener_owner_pid_after_probe": 4242,
        "listener_owner_verified_before_probe": True,
        "listener_owner_verified_after_probe": True,
        "start_byte": 0,
        "end_byte": len(_startup_log().encode("utf-8")),
    }
    persisted = json.loads((tmp_path / CAPACITY_PROBE_FILENAME).read_text())
    assert persisted == evidence


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case", "props", "models", "slots", "startup_log", "launch_argv", "failure"),
    [
        (
            "effective context below the contract",
            {**_props(), "default_generation_settings": {"n_ctx": 32_768}},
            _models(),
            _slots(),
            _startup_log(),
            _launch_argv(),
            "effective context",
        ),
        (
            "model effective context silently scaled",
            _props(),
            {"data": [{"id": "qwen35", "meta": {"n_ctx": 32_768, "n_ctx_train": 262_144}}]},
            _slots(),
            _startup_log(),
            _launch_argv(),
            "model effective context",
        ),
        (
            "native context missing",
            _props(),
            {"data": [{"id": "qwen35", "meta": {"n_ctx": 65_536}}]},
            _slots(),
            _startup_log(),
            _launch_argv(),
            "n_ctx_train",
        ),
        (
            "native context too small",
            _props(),
            {"data": [{"id": "qwen35", "meta": {"n_ctx": 65_536, "n_ctx_train": 32_768}}]},
            _slots(),
            _startup_log(),
            _launch_argv(),
            "n_ctx_train",
        ),
        (
            "startup log missing",
            _props(),
            _models(),
            _slots(),
            "",
            _launch_argv(),
            "startup log",
        ),
        (
            "startup log malformed",
            _props(),
            _models(),
            _slots(),
            _startup_log().replace("n_ctx         = 65536", "n_ctx         = invalid"),
            _launch_argv(),
            "logged context",
        ),
        (
            "startup context reduced",
            _props(),
            _models(),
            _slots(),
            _startup_log().replace("n_ctx         = 65536", "n_ctx         = 32768"),
            _launch_argv(),
            "logged context",
        ),
        (
            "startup slot context reduced",
            _props(),
            _models(),
            _slots(),
            _startup_log().replace("n_ctx_seq     = 65536", "n_ctx_seq     = 32768"),
            _launch_argv(),
            "logged slot context",
        ),
        (
            "startup parallelism changed",
            _props(),
            _models(),
            _slots(),
            _startup_log().replace("n_seq_max     = 1", "n_seq_max     = 2"),
            _launch_argv(),
            "logged parallel slots",
        ),
        (
            "K cache changed",
            _props(),
            _models(),
            _slots(),
            _startup_log().replace("K (f16)", "K (q8_0)"),
            _launch_argv(),
            "cache_type_k",
        ),
        (
            "V cache missing",
            _props(),
            _models(),
            _slots(),
            _startup_log().replace(", V (f16): 6144.00 MiB", ""),
            _launch_argv(),
            "cache_type_v",
        ),
        (
            "flash attention mismatched",
            _props(),
            _models(),
            _slots(),
            _startup_log().replace("flash_attn    = enabled", "flash_attn    = disabled"),
            _launch_argv(),
            "flash_attn",
        ),
        (
            "fit adjustment evidence",
            _props(),
            _models(),
            _slots(),
            _startup_log()
            + "\ncommon_params_fit_impl: context size reduced from 262144 to 65536",
            _launch_argv(),
            "fit adjustment",
        ),
        (
            "argv-only cache and fit claims",
            _props(),
            _models(),
            _slots(),
            "server: listening on 127.0.0.1:8080",
            _launch_argv(),
            "startup log",
        ),
        (
            "fit argv enabled",
            _props(),
            _models(),
            _slots(),
            _startup_log(),
            [*_launch_argv()[:6], "on", *_launch_argv()[7:]],
            "--fit off",
        ),
        (
            "slot allocation missing",
            _props(),
            _models(),
            [],
            _startup_log(),
            _launch_argv(),
            "slot allocation",
        ),
        (
            "multiple slots",
            {**_props(), "total_slots": 2},
            _models(),
            [{"id": 0, "n_ctx": 65_536}, {"id": 1, "n_ctx": 65_536}],
            _startup_log(),
            _launch_argv(),
            "single slot",
        ),
        (
            "slot allocation undersized",
            _props(),
            _models(),
            [{"id": 0, "n_ctx": 32_768}],
            _startup_log(),
            _launch_argv(),
            "slot context",
        ),
        (
            "malformed props",
            [],
            _models(),
            _slots(),
            _startup_log(),
            _launch_argv(),
            "/props response is not an object",
        ),
    ],
)
async def test_capacity_probe_fails_closed_on_missing_or_mismatched_runtime_fact(
    tmp_path: Path,
    case: str,
    props: JsonObject | list[JsonObject],
    models: JsonObject | list[JsonObject],
    slots: JsonObject | list[JsonObject],
    startup_log: str,
    launch_argv: list[str],
    failure: str,
) -> None:
    # Given: one malformed or contradictory live runtime fact.
    # When/Then: validation aborts and retains a failed capacity artifact.
    with pytest.raises(CapacityProbeMismatchError, match=failure):
        await _run_probe(
            tmp_path,
            props=props,
            models=models,
            slots=slots,
            startup_log=startup_log,
            launch_argv=launch_argv,
        )
    evidence = json.loads((tmp_path / CAPACITY_PROBE_FILENAME).read_text())
    assert evidence["passed"] is False, case
    assert any(failure in reason for reason in evidence["failure_reasons"]), case
