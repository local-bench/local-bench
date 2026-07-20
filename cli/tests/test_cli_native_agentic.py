from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from localbench import cli as cli_module
from localbench._types import JsonObject
from localbench.appliance.manifest import PINNED_RUNTIME_ID
import localbench.appliance.native_apparmor as native_apparmor_module
from localbench.appliance.provisioner import ProvisioningError
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


def test_setup_agentic_renders_apparmor_userns_guidance_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    rootfs = tmp_path / "rootfs"
    bwrap = rootfs / "usr/bin/bwrap"
    bwrap.parent.mkdir(parents=True)
    bwrap.write_bytes(b"signed-bwrap\n")
    bwrap_sha256 = hashlib.sha256(b"signed-bwrap\n").hexdigest()
    enabled = tmp_path / "apparmor-enabled"
    restriction = tmp_path / "apparmor-restrict-unprivileged-userns"
    enabled.write_bytes(b"Y\n")
    restriction.write_bytes(b"1\n")
    monkeypatch.setattr(
        native_apparmor_module, "_APPARMOR_ENABLED_PATH", enabled
    )
    monkeypatch.setattr(
        native_apparmor_module,
        "_APPARMOR_USERNS_RESTRICTION_PATH",
        restriction,
    )
    error = native_apparmor_module.classify_userns_denial(
        rootfs,
        bwrap_sha256,
        "bwrap: setting up uid map: Permission denied",
    )
    assert isinstance(error, ProvisioningError)

    class Provisioner:
        def __init__(self, *, environ: Mapping[str, str]) -> None:
            del environ

        @staticmethod
        def ensure_active(runtime_id: str = PINNED_RUNTIME_ID) -> JsonObject:
            del runtime_id
            raise error

    monkeypatch.setattr(cli_module, "ApplianceProvisioner", Provisioner)
    stderr = io.StringIO()

    # When
    with redirect_stderr(stderr):
        code = main(["setup-agentic"])

    # Then
    rendered = stderr.getvalue()
    print(rendered, end="")
    assert code != 0
    assert rendered == (
        "error      host_userns_blocked_by_apparmor: Ubuntu AppArmor blocked "
        "LocalBench's bundled bubblewrap from creating an unprivileged user "
        "namespace. \n"
        "Observed:\n"
        "- AppArmor enabled\n"
        "- kernel.apparmor_restrict_unprivileged_userns=1\n"
        f"- bundled bwrap: {bwrap.resolve()}\n"
        f"- bundled bwrap SHA-256: {bwrap_sha256}\n"
        "- failure: setting up uid map: Permission denied\n"
        "LocalBench made no system changes.\n"
        "Setting the following sysctl to 0 permits unprivileged user namespaces "
        "system-wide\n"
        "while it remains disabled. This affects processes other than LocalBench "
        "and weakens a\n"
        "host security restriction. Prefer running LocalBench in a disposable or "
        "dedicated VM,\n"
        "or consult the machine administrator.\n"
        "Keep the setting at 0 during both setup and benchmark execution, then "
        "restore it:\n"
        "    sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0\n"
        "    # run localbench setup-agentic and the benchmark\n"
        "    sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=1\n"
        "Do not run LocalBench as root, disable AppArmor, or persist this setting "
        "unless you\n"
        "understand and accept the system-wide effect.\n"
        "This release does not install an AppArmor exception automatically because "
        "the bundled\n"
        "executable is materialized under a user-owned path; granting that path "
        "additional\n"
        "permission would not safely pin the permission to the signed executable.\n"
    )
