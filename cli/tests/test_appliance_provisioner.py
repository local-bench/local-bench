from __future__ import annotations

import hashlib
import base64
import json
import lzma
from pathlib import Path
import threading

import pytest

import localbench.appliance.provisioner as provisioner_module
from localbench.appliance.manifest import PINNED_RUNTIME_ID, REQUIRED_CRITICAL_HASHES
from localbench.appliance.provisioner import (
    ApplianceProvisioner,
    CommandResult,
    ProvisioningError,
    STATE_ORDER,
    WSL_CONF,
    _decode,
    _parse_wsl_version,
    _parse_wsl_verbose,
    validate_storage_root,
)

SHA = "ab" * 32


def manifest(archive: bytes) -> dict[str, object]:
    return {
        "runtime_id": PINNED_RUNTIME_ID,
        "execution_contract_sha256": SHA,
        "rootfs": {
            "url": "https://local-bench.ai/rootfs.tar.xz",
            "sha256": hashlib.sha256(archive).hexdigest(),
            "size_bytes": len(archive),
            "uncompressed_size_bytes": len(lzma.decompress(archive)),
        },
        "disk_requirements": {"peak_free_bytes": 3, "steady_free_bytes": 1, "download_bytes": 1, "import_bytes": 1, "provision_growth_bytes": 1},
        "appworld": {},
        "worker": {"protocol_version": "localbench.agentic-worker.v1"},
        "task_identity": {
            "ordered_task_ids_sha256": SHA,
            "selection_recipe_sha256": SHA,
            "semantic_task_sha256": SHA,
        },
        "critical_hashes": {name: SHA for name in REQUIRED_CRITICAL_HASHES},
    }


class BytesDownloader:
    def __init__(self, body: bytes | Exception) -> None:
        self.body = body

    def get(self, url: str, *, maximum_bytes: int) -> bytes:
        if isinstance(self.body, Exception):
            raise self.body
        assert len(self.body) <= maximum_bytes
        return self.body


def test_state_machine_order_is_normative() -> None:
    assert STATE_ORDER == (
        "absent",
        "downloading",
        "verified",
        "imported",
        "provisioned",
        "canary-green",
        "active",
    )


def test_wsl_version_parser_uses_probed_verbatim_label_and_utf16() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "wsl-2.6.3.0-win26200-raw.json").read_text(encoding="utf-8"))
    by_args = {tuple(item["arguments"]): item for item in fixture["commands"]}
    version_raw = base64.b64decode(by_args[("--version",)]["stdout_base64"])
    text = _decode(version_raw)
    assert _parse_wsl_version(text) == (2, 6, 3, 0)
    assert _decode(version_raw).startswith("WSL version:")
    verbose = _decode(base64.b64decode(by_args[("--list", "--verbose")]["stdout_base64"]))
    assert _parse_wsl_verbose(verbose) == {"Ubuntu": 2}
    quiet = _decode(base64.b64decode(by_args[("--list", "--quiet")]["stdout_base64"]))
    assert quiet.splitlines() == ["Ubuntu"]
    with pytest.raises(ProvisioningError, match="wsl_version_unparseable"):
        _parse_wsl_version("invented localized fixture")


def test_wsl_conf_contains_every_hardening_setting() -> None:
    assert "enabled=false" in WSL_CONF
    assert "mountFsTab=false" in WSL_CONF
    assert "appendWindowsPath=false" in WSL_CONF
    assert "default=lbworker" in WSL_CONF


def test_download_interruption_leaves_resumable_downloading_state(
    tmp_path: Path,
) -> None:
    error = ProvisioningError("download_failed", "fault", "retry")
    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=lambda argv, timeout=None: CommandResult(0),
        downloader=BytesDownloader(error),
        environ={},
    )
    runtime_dir = tmp_path / "WSL" / PINNED_RUNTIME_ID
    runtime_dir.mkdir(parents=True)
    with pytest.raises(ProvisioningError, match="download_failed"):
        provisioner._resume(
            runtime_dir, {"state": "absent"}, manifest(lzma.compress(b"tar"))
        )
    state = json.loads((runtime_dir / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "downloading"
    assert not (tmp_path / "active.json").exists()


@pytest.mark.parametrize(
    "fault_state", ["verified", "imported", "provisioned", "canary-green"]
)
def test_fault_injection_never_creates_active_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault_state: str
) -> None:
    archive = lzma.compress(b"tar")
    value = manifest(archive)
    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=lambda argv, timeout=None: CommandResult(0),
        downloader=BytesDownloader(archive),
        environ={},
    )
    runtime_dir = tmp_path / "WSL" / PINNED_RUNTIME_ID
    runtime_dir.mkdir(parents=True)
    if fault_state == "verified":
        (
            runtime_dir / f"localbench-agentic-runtime-{PINNED_RUNTIME_ID}.tar.xz"
        ).write_bytes(archive)
    initial = {"state": fault_state, "distro_name": "LocalBench-Agentic-test"}
    provisioner._write_state(
        runtime_dir, PINNED_RUNTIME_ID, fault_state, distro_name=initial["distro_name"]
    )
    monkeypatch.setattr(provisioner, "_distro_names", lambda: {initial["distro_name"]})
    monkeypatch.setattr(
        provisioner,
        "_import_hardened",
        lambda *args: (_ for _ in ()).throw(
            ProvisioningError("fault", fault_state, "retry")
        ),
    )
    monkeypatch.setattr(
        provisioner,
        "_provision_appworld",
        lambda *args: (_ for _ in ()).throw(
            ProvisioningError("fault", fault_state, "retry")
        ),
    )
    monkeypatch.setattr(
        provisioner,
        "_run_canaries",
        lambda *args: (_ for _ in ()).throw(
            ProvisioningError("fault", fault_state, "retry")
        ),
    )
    monkeypatch.setattr(
        provisioner,
        "_prove_hardening",
        lambda *args: (_ for _ in ()).throw(
            ProvisioningError("fault", fault_state, "retry")
        ),
    )
    with pytest.raises(ProvisioningError, match="fault"):
        provisioner._resume(runtime_dir, initial, value)
    assert not (tmp_path / "active.json").exists()


def test_active_remove_requires_explicit_confirmation_before_wsl_call(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return CommandResult(0, b"")

    provisioner = ApplianceProvisioner(
        root=tmp_path, runner=runner, downloader=BytesDownloader(b""), environ={}
    )
    runtime_dir = tmp_path / "WSL" / PINNED_RUNTIME_ID
    runtime_dir.mkdir(parents=True)
    provisioner._write_state(
        runtime_dir, PINNED_RUNTIME_ID, "canary-green", distro_name="LocalBench-Agentic-test"
    )
    (tmp_path / "active.json").write_text(json.dumps({"runtime_id": PINNED_RUNTIME_ID}), encoding="utf-8")
    with pytest.raises(ProvisioningError) as caught:
        provisioner.remove(PINNED_RUNTIME_ID)
    assert caught.value.code == "active_runtime_confirmation_required"
    assert calls == []


def test_remove_refuses_unregister_when_ownership_marker_does_not_match(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        if argv[1:] == ["--list", "--quiet"]:
            return CommandResult(0, b"LocalBench-Agentic-test\n")
        if "/bin/cat" in argv:
            return CommandResult(0, b'{"owner":"someone-else"}')
        return CommandResult(0)

    provisioner = ApplianceProvisioner(
        root=tmp_path, runner=runner, downloader=BytesDownloader(b""), environ={}
    )
    runtime_dir = tmp_path / "WSL" / PINNED_RUNTIME_ID
    runtime_dir.mkdir(parents=True)
    provisioner._write_state(
        runtime_dir,
        PINNED_RUNTIME_ID,
        "imported",
        distro_name="LocalBench-Agentic-test",
    )
    with pytest.raises(ProvisioningError) as caught:
        provisioner.remove(PINNED_RUNTIME_ID)
    assert caught.value.code == "ownership_marker_mismatch"
    assert not any("--unregister" in call for call in calls)


def test_confirmed_active_remove_checks_marker_unregisters_and_deletes(
    tmp_path: Path,
) -> None:
    distro = "LocalBench-Agentic-test"
    marker = {
        "owner": "localbench",
        "runtime_id": PINNED_RUNTIME_ID,
        "schema": "localbench.appliance_owner.v1",
    }
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        if argv[1:] == ["--list", "--quiet"]:
            return CommandResult(0, (distro + "\n").encode())
        if "/bin/cat" in argv:
            return CommandResult(0, json.dumps(marker).encode())
        return CommandResult(0)

    provisioner = ApplianceProvisioner(
        root=tmp_path, runner=runner, downloader=BytesDownloader(b""), environ={}
    )
    runtime_dir = tmp_path / "WSL" / PINNED_RUNTIME_ID
    runtime_dir.mkdir(parents=True)
    provisioner._write_state(
        runtime_dir, PINNED_RUNTIME_ID, "active", distro_name=distro
    )
    (tmp_path / "active.json").write_text(
        json.dumps({"runtime_id": PINNED_RUNTIME_ID}), encoding="utf-8"
    )

    provisioner.remove(PINNED_RUNTIME_ID, confirm_active=True)

    assert any(call[1:] == ["--unregister", distro] for call in calls)
    assert not runtime_dir.exists()
    assert not (tmp_path / "active.json").exists()


def test_prune_preserves_active_pinned_and_newest_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=lambda argv, timeout=None: CommandResult(0),
        downloader=BytesDownloader(b""),
        environ={},
    )
    records = {
        "old-a": "2026-01-01T00:00:00Z",
        "old-b": "2026-02-01T00:00:00Z",
        "rollback": "2026-03-01T00:00:00Z",
        PINNED_RUNTIME_ID: "2026-04-01T00:00:00Z",
    }
    for runtime_id, updated_at in records.items():
        directory = tmp_path / "WSL" / runtime_id
        directory.mkdir(parents=True)
        (directory / "state.json").write_text(
            json.dumps(
                {
                    "schema": "localbench.appliance_state.v1",
                    "runtime_id": runtime_id,
                    "state": "imported"
                    if runtime_id != PINNED_RUNTIME_ID
                    else "active",
                    "updated_at": updated_at,
                }
            ),
            encoding="utf-8",
        )
    removed: list[str] = []
    monkeypatch.setattr(
        provisioner, "remove", lambda runtime_id: removed.append(runtime_id)
    )

    assert provisioner.prune() == ["old-b", "old-a"]
    assert removed == ["old-b", "old-a"]
    assert "rollback" not in removed


def test_cloud_synced_storage_is_rejected(tmp_path: Path) -> None:
    cloud = tmp_path / "OneDrive"
    target = cloud / "LocalBench"
    target.mkdir(parents=True)
    with pytest.raises(ProvisioningError) as caught:
        validate_storage_root(target, {"OneDrive": str(cloud)})
    assert caught.value.code == "cloud_storage_disallowed"


def test_runtime_id_cannot_be_retargeted_after_first_seen_manifest(
    tmp_path: Path,
) -> None:
    first = {"runtime_id": PINNED_RUNTIME_ID, "rootfs": {"sha256": "11" * 32}}
    second = {"runtime_id": PINNED_RUNTIME_ID, "rootfs": {"sha256": "22" * 32}}
    ApplianceProvisioner._bind_manifest(tmp_path, first)
    ApplianceProvisioner._bind_manifest(tmp_path, first)
    with pytest.raises(ProvisioningError) as caught:
        ApplianceProvisioner._bind_manifest(tmp_path, second)
    assert caught.value.code == "runtime_id_retargeted"


def test_import_flow_uses_only_probed_wsl_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return CommandResult(0)

    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=runner,
        downloader=BytesDownloader(b""),
        environ={},
    )
    monkeypatch.setattr(provisioner, "_distro_names", lambda: set())
    monkeypatch.setattr(provisioner, "_assert_owned", lambda *args: None)
    monkeypatch.setattr(provisioner, "_prove_wsl2", lambda *args: None)
    monkeypatch.setattr(provisioner, "_install_wsl_conf", lambda *args: None)
    monkeypatch.setattr(provisioner, "_prove_hardening", lambda *args: None)
    tar_path = tmp_path / "rootfs.tar"
    tar_path.write_bytes(b"tar")

    final = provisioner._import_hardened(tmp_path, PINNED_RUNTIME_ID, tar_path)

    staging = f"LocalBench-Staging-{PINNED_RUNTIME_ID}"
    expected_final = f"LocalBench-Agentic-{PINNED_RUNTIME_ID}"
    assert final == expected_final
    assert [
        "wsl.exe",
        "--import",
        staging,
        str(tmp_path / "staging-import"),
        str(tar_path),
        "--version",
        "2",
    ] in calls
    assert ["wsl.exe", "--terminate", staging] in calls
    assert ["wsl.exe", "--unregister", staging] in calls
    assert [
        "wsl.exe",
        "--import",
        expected_final,
        str(tmp_path / "vhd"),
        str(tar_path),
        "--version",
        "2",
    ] in calls


def test_partial_registration_without_marker_is_journaled_and_never_unregistered(
    tmp_path: Path,
) -> None:
    staging = f"LocalBench-Staging-{PINNED_RUNTIME_ID}"
    calls: list[list[str]] = []
    listed = 0

    def runner(argv, timeout=None):
        nonlocal listed
        calls.append(list(argv))
        if argv[1:] == ["--list", "--quiet"]:
            listed += 1
            return CommandResult(0, (staging + "\n").encode() if listed > 1 else b"")
        if "--import" in argv:
            return CommandResult(1, b"", b"interrupted import")
        if "/bin/cat" in argv:
            return CommandResult(1, b"", b"marker unavailable")
        return CommandResult(0)

    provisioner = ApplianceProvisioner(
        root=tmp_path, runner=runner, downloader=BytesDownloader(b""), environ={}
    )
    tar_path = tmp_path / "rootfs.tar"
    tar_path.write_bytes(b"tar")
    with pytest.raises(ProvisioningError) as caught:
        provisioner._import_hardened(tmp_path, PINNED_RUNTIME_ID, tar_path)
    assert caught.value.code == "partial_registration_unowned"
    journal = json.loads(
        (tmp_path / "partial-registration.json").read_text(encoding="utf-8")
    )
    assert journal["distro_name"] == staging
    assert not any("--unregister" in call for call in calls)


def test_wsl_disk_full_is_a_typed_disk_error(tmp_path: Path) -> None:
    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=lambda argv, timeout=None: CommandResult(
            1, b"", b"write failed: No space left on device"
        ),
        downloader=BytesDownloader(b""),
        environ={},
    )
    with pytest.raises(ProvisioningError) as caught:
        provisioner._wsl(["--list", "--quiet"], timeout=1)
    assert caught.value.code == "disk_space_exhausted"


def test_disk_math_checks_peak_and_steady_before_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=lambda argv, timeout=None: CommandResult(0),
        downloader=BytesDownloader(b""),
        environ={},
    )
    monkeypatch.setattr(
        provisioner_module.shutil,
        "disk_usage",
        lambda path: provisioner_module.shutil._ntuple_diskusage(100, 98, 2),
    )
    with pytest.raises(ProvisioningError) as caught:
        provisioner._require_disk(
            tmp_path,
            {
                "peak_free_bytes": 3,
                "steady_free_bytes": 4,
                "download_bytes": 1,
                "import_bytes": 1,
                "provision_growth_bytes": 1,
            },
        )
    assert caught.value.code == "disk_space_insufficient"


def test_ca_bundle_is_copied_and_only_linux_path_reaches_worker(tmp_path: Path) -> None:
    ca = tmp_path / "corporate-ca.pem"
    ca.write_bytes(b"test corporate CA bytes")
    digest = hashlib.sha256(ca.read_bytes()).hexdigest()
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        if "/usr/bin/sha256sum" in argv:
            return CommandResult(0, f"{digest}  /opt/localbench/ca/corporate-ca.pem\n".encode())
        return CommandResult(0)

    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=runner,
        downloader=BytesDownloader(b""),
        environ={"LOCALBENCH_CA_BUNDLE": str(ca)},
    )
    provisioner._provision_appworld("LocalBench-Agentic-test", {"appworld": {}})
    worker_call = next(call for call in calls if "/opt/localbench/bin/provision-appworld" in call)
    assert "-i" in worker_call
    assert "SSL_CERT_FILE=/opt/localbench/ca/corporate-ca.pem" in worker_call
    assert all(str(ca) not in item for item in worker_call)


def test_global_inventory_lock_serializes_different_runtime_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = 0
    entered_first = threading.Event()
    release_first = threading.Event()
    guard = threading.Lock()

    def preflight(self) -> None:
        nonlocal entered
        with guard:
            entered += 1
            position = entered
        if position == 1:
            entered_first.set()
            assert release_first.wait(5)

    monkeypatch.setattr(ApplianceProvisioner, "_feature_preflight", preflight)
    monkeypatch.setattr(
        ApplianceProvisioner,
        "_fetch_manifest",
        lambda self: {"runtime_id": "test", "rootfs": {"sha256": SHA}},
    )
    monkeypatch.setattr(ApplianceProvisioner, "_resume", lambda self, *args: {"ok": True})
    provisioners = [
        ApplianceProvisioner(
            root=tmp_path,
            runner=lambda argv, timeout=None: CommandResult(0),
            downloader=BytesDownloader(b""),
            environ={},
        )
        for _ in range(2)
    ]
    errors: list[BaseException] = []

    def invoke(index: int, runtime_id: str) -> None:
        try:
            provisioners[index].ensure_active(runtime_id)
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    first = threading.Thread(target=invoke, args=(0, "runtime-a"))
    second = threading.Thread(target=invoke, args=(1, "runtime-b"))
    first.start()
    assert entered_first.wait(5)
    second.start()
    second.join(0.1)
    assert second.is_alive()
    assert entered == 1
    release_first.set()
    first.join(5)
    second.join(5)
    assert not errors
    assert entered == 2


def test_active_state_recovers_pointer_flip_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner = ApplianceProvisioner(
        root=tmp_path,
        runner=lambda argv, timeout=None: CommandResult(0),
        downloader=BytesDownloader(b""),
        environ={},
    )
    runtime_dir = tmp_path / "WSL" / PINNED_RUNTIME_ID
    runtime_dir.mkdir(parents=True)
    provisioner._write_state(
        runtime_dir,
        PINNED_RUNTIME_ID,
        "active",
        distro_name="LocalBench-Agentic-recovered",
    )
    (tmp_path / "active.json").write_text(
        json.dumps({"runtime_id": "previous-runtime"}), encoding="utf-8"
    )
    monkeypatch.setattr(provisioner, "_feature_preflight", lambda: None)
    monkeypatch.setattr(
        provisioner,
        "_fetch_manifest",
        lambda: {"runtime_id": PINNED_RUNTIME_ID, "rootfs": {"sha256": SHA}},
    )
    monkeypatch.setattr(provisioner, "_handshake", lambda *args: {"healthy": True})
    assert provisioner.ensure_active() == {"healthy": True}
    pointer = json.loads((tmp_path / "active.json").read_text(encoding="utf-8"))
    assert pointer["runtime_id"] == PINNED_RUNTIME_ID
    assert pointer["distro_name"] == "LocalBench-Agentic-recovered"
