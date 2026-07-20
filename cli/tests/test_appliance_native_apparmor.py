from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

import localbench.appliance.native_apparmor as native_apparmor_module
from localbench._types import JsonObject
from localbench.appliance.provisioner import (
    ApplianceProvisioner,
    CommandResult,
    ProvisioningError,
)
from test_appliance_native_provisioner import NativeBoundary, _native_provisioner


class AppArmorDenialBoundary(NativeBoundary):
    def __init__(self, identity: JsonObject, denial_stderr: bytes) -> None:
        super().__init__(identity)
        self.denial_stderr = denial_stderr
        self.block_provisioning = True

    def __call__(
        self, argv: Sequence[str], timeout: float | None = None
    ) -> CommandResult:
        del timeout
        call = list(argv)
        self.calls.append(call)
        if any(
            argument.endswith("/provision-appworld") for argument in call
        ) and self.block_provisioning:
            return CommandResult(1, stderr=self.denial_stderr)
        if "handshake" in call:
            return CommandResult(0, json.dumps(self.identity).encode())
        return CommandResult(0)


@pytest.fixture
def apparmor_denial_stderr() -> bytes:
    return (
        Path(__file__).parent / "fixtures" / "apparmor_userns_denied.stderr"
    ).read_bytes()


def _policy_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
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
    return enabled, restriction


def _denied_provisioner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    denial_stderr: bytes,
) -> tuple[ApplianceProvisioner, AppArmorDenialBoundary, Path]:
    provisioner, successful_boundary, runtime_dir = _native_provisioner(
        tmp_path, monkeypatch
    )
    boundary = AppArmorDenialBoundary(successful_boundary.identity, denial_stderr)
    provisioner.runner = boundary
    return provisioner, boundary, runtime_dir


def test_native_provisioning_classifies_real_uid_map_denial_when_all_evidence_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    apparmor_denial_stderr: bytes,
) -> None:
    # Given
    _policy_paths(tmp_path, monkeypatch)
    provisioner, _boundary, runtime_dir = _denied_provisioner(
        tmp_path, monkeypatch, apparmor_denial_stderr
    )

    # When
    with pytest.raises(ProvisioningError) as caught:
        provisioner.ensure_active()

    # Then
    bwrap = (runtime_dir / "rootfs/usr/bin/bwrap").resolve()
    bwrap_sha256 = hashlib.sha256(b"signed-bwrap\n").hexdigest()
    assert caught.value.code == "host_userns_blocked_by_apparmor"
    assert caught.value.detail == (
        "Ubuntu AppArmor blocked LocalBench's bundled bubblewrap from creating an "
        "unprivileged user namespace"
    )
    assert caught.value.remediation == (
        "\nObserved:\n"
        "- AppArmor enabled\n"
        "- kernel.apparmor_restrict_unprivileged_userns=1\n"
        f"- bundled bwrap: {bwrap}\n"
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
        "permission would not safely pin the permission to the signed executable."
    )


def test_native_provisioning_keeps_generic_error_when_apparmor_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    apparmor_denial_stderr: bytes,
) -> None:
    # Given
    enabled, _restriction = _policy_paths(tmp_path, monkeypatch)
    enabled.write_bytes(b"N\n")
    provisioner, _boundary, _runtime_dir = _denied_provisioner(
        tmp_path, monkeypatch, apparmor_denial_stderr
    )

    # When
    with pytest.raises(ProvisioningError) as caught:
        provisioner.ensure_active()

    # Then
    assert caught.value.code == "appworld_provision_failed"
    assert caught.value.detail == apparmor_denial_stderr.decode()
    assert "sudo sysctl" not in str(caught.value)


def test_native_provisioning_keeps_generic_error_when_userns_restriction_is_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    apparmor_denial_stderr: bytes,
) -> None:
    # Given
    _enabled, restriction = _policy_paths(tmp_path, monkeypatch)
    restriction.write_bytes(b"0\n")
    provisioner, _boundary, _runtime_dir = _denied_provisioner(
        tmp_path, monkeypatch, apparmor_denial_stderr
    )

    # When
    with pytest.raises(ProvisioningError) as caught:
        provisioner.ensure_active()

    # Then
    assert caught.value.code == "appworld_provision_failed"
    assert caught.value.detail == apparmor_denial_stderr.decode()
    assert "sudo sysctl" not in str(caught.value)


def test_native_provisioning_keeps_generic_error_for_other_permission_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    _policy_paths(tmp_path, monkeypatch)
    other_denial = b"bwrap: mounting proc: Permission denied\n"
    provisioner, _boundary, _runtime_dir = _denied_provisioner(
        tmp_path, monkeypatch, other_denial
    )

    # When
    with pytest.raises(ProvisioningError) as caught:
        provisioner.ensure_active()

    # Then
    assert caught.value.code == "appworld_provision_failed"
    assert caught.value.detail == other_denial.decode()
    assert "sudo sysctl" not in str(caught.value)


def test_apparmor_denial_detection_executes_only_the_bundled_launcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    apparmor_denial_stderr: bytes,
) -> None:
    # Given
    _policy_paths(tmp_path, monkeypatch)
    provisioner, boundary, runtime_dir = _denied_provisioner(
        tmp_path, monkeypatch, apparmor_denial_stderr
    )

    # When
    with pytest.raises(ProvisioningError) as caught:
        provisioner.ensure_active()

    # Then
    assert caught.value.code == "host_userns_blocked_by_apparmor"
    assert len(boundary.calls) == 1
    launch = boundary.calls[0]
    rootfs = runtime_dir / "rootfs"
    assert launch[0] == str(rootfs / "lib64/ld-linux-x86-64.so.2")
    assert launch[3] == str(rootfs / "usr/bin/bwrap")
    assert launch[3] != "/usr/bin/bwrap"
    forbidden = {"sudo", "sysctl", "apparmor_parser", "apt", "apt-get", "dpkg"}
    assert forbidden.isdisjoint(Path(argument).name for argument in launch)


def test_native_setup_resumes_from_imported_after_apparmor_policy_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    apparmor_denial_stderr: bytes,
) -> None:
    # Given
    _enabled, restriction = _policy_paths(tmp_path, monkeypatch)
    provisioner, boundary, runtime_dir = _denied_provisioner(
        tmp_path, monkeypatch, apparmor_denial_stderr
    )
    with pytest.raises(ProvisioningError) as caught:
        provisioner.ensure_active()
    assert caught.value.code == "host_userns_blocked_by_apparmor"
    state_after_denial = json.loads(
        (runtime_dir / "state.json").read_text(encoding="utf-8")
    )
    assert state_after_denial["state"] == "imported"
    assert not (tmp_path / "active.json").exists()
    archive = runtime_dir / f"localbench-agentic-runtime-{state_after_denial['runtime_id']}.tar.xz"
    archive.unlink()
    restriction.write_bytes(b"0\n")
    boundary.block_provisioning = False

    # When
    result = provisioner.ensure_active()

    # Then
    final_state = json.loads(
        (runtime_dir / "state.json").read_text(encoding="utf-8")
    )
    assert (tmp_path / "active.json").is_file()
    assert final_state["state"] == "active"
    assert result["runtime_id"] == state_after_denial["runtime_id"]
