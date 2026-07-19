from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

import localbench.appliance.provisioner as provisioner_module
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.native_materialization import (
    _rootfs_filter,
    _validated_rootfs_members,
    materialize_rootfs,
)
from localbench.appliance.provisioner import (
    ApplianceProvisioner,
    CommandResult,
    ProvisioningError,
    VerifiedManifest,
    WSL_CONF,
    appliance_root,
)
from localbench.submissions.canon import canonical_json_hash
from test_appliance_provisioner import BytesDownloader, manifest


def _tar_entry(
    archive: tarfile.TarFile, name: str, data: bytes, mode: int = 0o644
) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(data)
    member.mode = mode
    archive.addfile(member, io.BytesIO(data))


def _native_release() -> tuple[bytes, dict[str, object], dict[str, object]]:
    package = b"native-worker\n"
    package_digest = hashlib.sha256(package).digest()
    encoded = base64.urlsafe_b64encode(package_digest).rstrip(b"=").decode("ascii")
    script = b"#!/opt/localbench/venv/bin/python\n"
    script_digest = hashlib.sha256(script).digest()
    script_encoded = base64.urlsafe_b64encode(script_digest).rstrip(b"=").decode("ascii")
    record = (
        f"localbench/__init__.py,sha256={encoded},{len(package)}\n"
        f"../../../bin/localbench,sha256={script_encoded},{len(script)}\n"
        "local_bench_ai-0.4.3.dist-info/RECORD,,\n"
    ).encode()
    record_digest = hashlib.sha256(record).hexdigest()
    wheel_entries = sorted(
        [
            ["local_bench_ai-0.4.3.dist-info/RECORD", record_digest, len(record)],
            ["localbench/__init__.py", package_digest.hex(), len(package)],
            ["../../../bin/localbench", script_digest.hex(), len(script)],
        ]
    )
    entrypoint = b"#!/bin/sh\n"
    bubblewrap = b"signed-bwrap\n"
    wsl_conf = WSL_CONF.encode()
    owner = json.dumps(
        {
            "owner": "localbench",
            "runtime_id": PINNED_RUNTIME_ID,
            "schema": "localbench.appliance_owner.v1",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:xz") as archive:
        for name, data, mode in (
            ("./etc/localbench-appliance-owner.json", owner, 0o644),
            ("./etc/wsl.conf", wsl_conf, 0o644),
            ("./opt/localbench/bin/localbench-worker", entrypoint, 0o755),
            ("./opt/localbench/venv/bin/python", b"python\n", 0o755),
            ("./opt/localbench/venv/bin/localbench", script, 0o755),
            (
                "./opt/localbench/venv/lib/python3.12/site-packages/localbench/__init__.py",
                package,
                0o644,
            ),
            (
                "./opt/localbench/venv/lib/python3.12/site-packages/local_bench_ai-0.4.3.dist-info/RECORD",
                record,
                0o644,
            ),
            ("./usr/bin/bwrap", bubblewrap, 0o755),
            ("./lib64/ld-linux-x86-64.so.2", b"loader\n", 0o755),
        ):
            _tar_entry(archive, name, data, mode)
        appworld = tarfile.TarInfo("./home/lbworker/appworld")
        appworld.type = tarfile.DIRTYPE
        appworld.mode = 0o755
        archive.addfile(appworld)
        device = tarfile.TarInfo("./dev/null")
        device.type = tarfile.CHRTYPE
        device.devmajor = 1
        device.devminor = 3
        archive.addfile(device)
        mtab = tarfile.TarInfo("./etc/mtab")
        mtab.type = tarfile.SYMTYPE
        mtab.linkname = "/proc/mounts"
        archive.addfile(mtab)
    payload = manifest(stream.getvalue())
    critical = payload["critical_hashes"]
    assert isinstance(critical, dict)
    critical.update(
        {
            "worker_entrypoint_sha256": hashlib.sha256(entrypoint).hexdigest(),
            "worker_wheel_tree_sha256": canonical_json_hash(wheel_entries),
            "bubblewrap_sha256": hashlib.sha256(bubblewrap).hexdigest(),
            "wsl_conf_sha256": hashlib.sha256(wsl_conf).hexdigest(),
        }
    )
    identity = {
        "runtime_id": PINNED_RUNTIME_ID,
        "protocol_version": payload["worker"]["protocol_version"],
        "python_version": payload["python"]["version"],
        "bubblewrap_version": "bubblewrap 0.9.0",
        "appworld_package_sha256": critical["appworld_installed_tree_sha256"],
        "appworld_data_sha256": critical["appworld_data_tree_sha256"],
        "critical_hashes": critical,
        "execution_contract_sha256": payload["execution_contract_sha256"],
        **payload["task_identity"],
        "uid": "lbworker",
        "gid": "lbworker",
        "mnt_c_absent": True,
        "interop_blocked": True,
        "windows_path_absent": True,
    }
    return stream.getvalue(), payload, identity


class NativeBoundary:
    def __init__(self, identity: dict[str, object]) -> None:
        self.identity = identity
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout=None):
        call = list(argv)
        self.calls.append(call)
        if "handshake" in call:
            return CommandResult(0, json.dumps(self.identity).encode())
        return CommandResult(0)


class ResumableBytesDownloader(BytesDownloader):
    def download_to(self, url: str, path: Path, *, exact_bytes: int) -> None:
        assert isinstance(self.body, bytes)
        assert len(self.body) == exact_bytes
        path.write_bytes(self.body)


def _native_provisioner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ApplianceProvisioner, NativeBoundary, Path]:
    archive, payload, identity = _native_release()
    boundary = NativeBoundary(identity)
    value = ApplianceProvisioner(
        root=tmp_path,
        runner=boundary,
        downloader=ResumableBytesDownloader(archive),
        environ={},
    )
    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        value,
        "_resolve_manifest",
        lambda *_args: VerifiedManifest(payload, b"signed-manifest"),
    )
    return value, boundary, tmp_path / "native" / PINNED_RUNTIME_ID


def test_appliance_root_uses_xdg_data_home_on_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")

    assert appliance_root({"XDG_DATA_HOME": "/srv/data"}) == Path(
        "/srv/data/LocalBench"
    )
    assert appliance_root({"HOME": "/home/alice"}) == Path(
        "/home/alice/.local/share/LocalBench"
    )


def test_appliance_root_names_xdg_when_linux_home_is_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_home() -> Path:
        raise RuntimeError("home unavailable")

    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(provisioner_module.Path, "home", unavailable_home)

    with pytest.raises(ProvisioningError) as caught:
        appliance_root({})

    assert caught.value.code == "xdg_data_home_missing"
    assert "XDG_DATA_HOME" in str(caught.value)


def test_native_setup_materializes_and_activates_signed_rootfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner, boundary, runtime_dir = _native_provisioner(tmp_path, monkeypatch)

    result = provisioner.ensure_active()

    state = json.loads((runtime_dir / "state.json").read_text(encoding="utf-8"))
    active = json.loads((tmp_path / "active.json").read_text(encoding="utf-8"))
    assert result["runtime_id"] == PINNED_RUNTIME_ID
    assert state["state"] == "active"
    assert "distro_name" not in state
    assert "distro_name" not in active
    assert (runtime_dir / "rootfs/usr/bin/bwrap").read_bytes() == b"signed-bwrap\n"
    assert not (runtime_dir / "rootfs/dev/null").exists()
    if os.name != "nt":
        assert (runtime_dir / "rootfs/etc/mtab").readlink() == Path("/proc/mounts")
    isolated = [call for call in boundary.calls if "--unshare-all" in call]
    assert isolated
    assert all("--cap-drop" in call and "ALL" in call for call in isolated)
    assert all("wsl.exe" not in call for call in boundary.calls)


def test_native_materialization_enforces_signed_uncompressed_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, payload, identity = _native_release()
    rootfs = payload["rootfs"]
    assert isinstance(rootfs, dict)
    rootfs["uncompressed_size_bytes"] = int(rootfs["uncompressed_size_bytes"]) + 1
    value = ApplianceProvisioner(
        root=tmp_path,
        runner=NativeBoundary(identity),
        downloader=ResumableBytesDownloader(archive),
        environ={},
    )
    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        value,
        "_resolve_manifest",
        lambda *_args: VerifiedManifest(payload, b"signed-manifest"),
    )

    with pytest.raises(ProvisioningError) as caught:
        value.ensure_active()

    assert caught.value.code == "archive_size_invalid"


def test_native_materialization_rejects_archive_path_traversal(tmp_path: Path) -> None:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        _tar_entry(archive, "../outside", b"escape\n")
    tar_path = tmp_path / "rootfs.tar"
    tar_path.write_bytes(stream.getvalue())

    with pytest.raises(ProvisioningError) as caught:
        materialize_rootfs(tar_path, tmp_path / "rootfs", {})

    assert caught.value.code == "rootfs_materialization_failed"
    assert not (tmp_path / "outside").exists()


def test_native_materialization_extracts_relative_links_to_absolute_symlinks(
    tmp_path: Path,
) -> None:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        _tar_entry(
            archive, "./usr/share/ca-certificates/mozilla/GTS_Root_R4.crt", b"cert\n"
        )
        pem = tarfile.TarInfo("./etc/ssl/certs/GTS_Root_R4.pem")
        pem.type = tarfile.SYMTYPE
        pem.linkname = "/usr/share/ca-certificates/mozilla/GTS_Root_R4.crt"
        archive.addfile(pem)
        hashed = tarfile.TarInfo("./etc/ssl/certs/a3418fda.0")
        hashed.type = tarfile.SYMTYPE
        hashed.linkname = "GTS_Root_R4.pem"
        archive.addfile(hashed)
    tar_path = tmp_path / "rootfs.tar"
    tar_path.write_bytes(stream.getvalue())
    destination = tmp_path / "rootfs"
    destination.mkdir()

    with tarfile.open(tar_path, mode="r:") as source:
        source.extractall(
            destination,
            members=_validated_rootfs_members(source),
            filter=_rootfs_filter,
        )

    if os.name != "nt":
        assert (destination / "etc/ssl/certs/GTS_Root_R4.pem").readlink() == Path(
            "/usr/share/ca-certificates/mozilla/GTS_Root_R4.crt"
        )
        assert (destination / "etc/ssl/certs/a3418fda.0").readlink() == Path(
            "GTS_Root_R4.pem"
        )


def test_native_materialization_rejects_relative_symlink_escape(
    tmp_path: Path,
) -> None:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        evil = tarfile.TarInfo("./etc/evil")
        evil.type = tarfile.SYMTYPE
        evil.linkname = "../../outside"
        archive.addfile(evil)
    tar_path = tmp_path / "rootfs.tar"
    tar_path.write_bytes(stream.getvalue())

    with pytest.raises(ProvisioningError) as caught:
        materialize_rootfs(tar_path, tmp_path / "rootfs", {})

    assert caught.value.code == "rootfs_materialization_failed"
    assert "escapes rootfs" in caught.value.detail


def test_native_active_runtime_rechecks_materialized_critical_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner, _boundary, runtime_dir = _native_provisioner(tmp_path, monkeypatch)
    provisioner.ensure_active()
    (runtime_dir / "rootfs/usr/bin/bwrap").write_bytes(b"mutated\n")

    with pytest.raises(ProvisioningError) as caught:
        provisioner.ensure_active()

    assert caught.value.code == "runtime_mutated"


def test_native_list_and_remove_use_state_and_ownership_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner, _boundary, runtime_dir = _native_provisioner(tmp_path, monkeypatch)
    provisioner.ensure_active()

    assert provisioner.list_runtimes()[0]["runtime_id"] == PINNED_RUNTIME_ID
    with pytest.raises(ProvisioningError, match="--confirm-active"):
        provisioner.remove(PINNED_RUNTIME_ID)
    provisioner.remove(PINNED_RUNTIME_ID, confirm_active=True)

    assert not runtime_dir.exists()
    assert not (tmp_path / "active.json").exists()
