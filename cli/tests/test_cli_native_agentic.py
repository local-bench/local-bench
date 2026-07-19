from __future__ import annotations

from pathlib import Path
import json

import pytest

from localbench import cli as cli_module
from localbench._types import JsonObject
from localbench.cli import main


def test_doctor_reports_active_native_agentic_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_path = tmp_path / "active.json"
    active_path.write_text(
        json.dumps(
            {
                "schema": "localbench.appliance_active.v1",
                "runtime_id": "native-fixture",
            }
        ),
        encoding="utf-8",
    )

    class Provisioner:
        root = tmp_path

        @staticmethod
        def _read_json(path: Path) -> JsonObject | None:
            return json.loads(path.read_text(encoding="utf-8"))

        def list_runtimes(self) -> list[JsonObject]:
            return [
                {
                    "schema": "localbench.appliance_state.v1",
                    "runtime_id": "stale-active-fixture",
                    "state": "active",
                    "distro_name": "LocalBench-Agentic-stale-active-fixture",
                },
                {
                    "schema": "localbench.appliance_state.v1",
                    "runtime_id": "native-fixture",
                    "state": "active",
                },
            ]

    monkeypatch.setattr(cli_module, "ApplianceProvisioner", Provisioner)

    code = main(["doctor", "--cache-dir", str(tmp_path / "cache")])

    output = capsys.readouterr().out
    assert code == 0
    assert "agentic  native-fixture active (native Linux)" in output
