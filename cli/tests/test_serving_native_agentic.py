from __future__ import annotations

from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.wsl_bridge import WslPreflightResult
from localbench.scoring.agentic_exec.wsl_process import WslWorkerConfig
from localbench.serving import runner as serving_runner
from localbench.serving.options import ServeBenchOptions


def test_linux_agentic_preflight_provisions_managed_native_runtime_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=tmp_path / "model.gguf",
        model_ref=None,
        model_id="fixture",
        server_bin=tmp_path / "llama-server",
        ctx=32768,
        determinism="strict",
        tier="standard",
        bench="appworld_c",
        lane="bounded-final-v2",
        seed=1234,
    )
    runtime_identity: JsonObject = {"schema": "localbench.agentic_runtime_identity.v1"}
    runtime_digest = "a" * 64
    events: list[str] = []
    config = WslWorkerConfig(
        venv_python="/managed/rootfs/opt/localbench/venv/bin/python",
        appworld_root="/managed/rootfs/home/lbworker/appworld",
        native_rootfs=Path("/managed/rootfs"),
    )

    class Provisioner:
        def ensure_active(self) -> JsonObject:
            events.append("provision")
            return {
                "agentic_runtime_identity": runtime_identity,
                "agentic_runtime_identity_sha256": runtime_digest,
            }

    def resolve(**_kwargs: object) -> WslWorkerConfig:
        events.append("resolve")
        return config

    def preflight(
        *, config: WslWorkerConfig, max_items: int | None
    ) -> WslPreflightResult:
        events.append("preflight")
        assert max_items is None
        return WslPreflightResult(
            identity={}, task_ids=("fixture-task",), worker_config=config
        )

    monkeypatch.setattr(serving_runner.sys, "platform", "linux")
    monkeypatch.setattr(serving_runner, "ApplianceProvisioner", Provisioner)
    monkeypatch.setattr(serving_runner, "resolve_worker_config", resolve)
    monkeypatch.setattr(serving_runner, "preflight_wsl_agentic", preflight)

    result = serving_runner.preflight_agentic_if_needed(options, tmp_path / "run")

    assert events == ["provision", "resolve", "preflight"]
    assert result is not None
    assert result.agentic_runtime_identity == runtime_identity
    assert result.agentic_runtime_identity_sha256 == runtime_digest
