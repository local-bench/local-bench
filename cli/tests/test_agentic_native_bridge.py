from __future__ import annotations

import json
from pathlib import Path

import pytest

import localbench.appliance.provisioner as provisioner_module
from localbench.appliance import native_worker
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.provisioner import ProvisioningError
from localbench.scoring.agentic_exec import wsl_process
from localbench.scoring.agentic_exec import worker_process_control
from localbench.scoring.agentic_exec.wsl_process import worker_argv
from localbench.scoring.agentic_exec.wsl_teardown import ProcessPin


def _active_native_runtime(root: Path) -> Path:
    rootfs = root / "native" / PINNED_RUNTIME_ID / "rootfs"
    for relative in (
        "lib64/ld-linux-x86-64.so.2",
        "usr/bin/bwrap",
        "opt/localbench/venv/bin/python",
    ):
        path = rootfs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture\n")
    (rootfs / "home/lbworker/appworld").mkdir(parents=True)
    state = {
        "schema": "localbench.appliance_state.v1",
        "runtime_id": PINNED_RUNTIME_ID,
        "state": "active",
    }
    (root / "native" / PINNED_RUNTIME_ID / "state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    (root / "active.json").write_text(
        json.dumps(
            {
                "schema": "localbench.appliance_active.v1",
                "runtime_id": PINNED_RUNTIME_ID,
            }
        ),
        encoding="utf-8",
    )
    return rootfs


def test_linux_managed_config_resolves_materialized_native_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed_root = tmp_path / "LocalBench"
    rootfs = _active_native_runtime(managed_root)
    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")

    config = wsl_process.resolve_worker_config(
        platform_name="linux",
        environ={
            "XDG_DATA_HOME": str(tmp_path),
            "WSL_DISTRO_NAME": "Ubuntu-stand-in",
        },
    )

    assert config.distro_name is None
    assert config.native_rootfs == rootfs
    assert config.venv_python == str(rootfs / "opt/localbench/venv/bin/python")
    assert config.appworld_root == str(rootfs / "home/lbworker/appworld")


def test_linux_managed_worker_uses_signed_rootfs_bwrap_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed_root = tmp_path / "LocalBench"
    rootfs = _active_native_runtime(managed_root)
    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")
    config = wsl_process.resolve_worker_config(
        platform_name="linux", environ={"XDG_DATA_HOME": str(tmp_path)}
    )

    argv = worker_argv(config, worker_token="fixture-token", platform_name="linux")

    assert argv[0] == str(rootfs / "lib64/ld-linux-x86-64.so.2")
    assert str(rootfs / "usr/bin/bwrap") in argv
    assert "--unshare-all" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert ("--ro-bind", str(rootfs), "/") == tuple(
        argv[argv.index("--ro-bind") : argv.index("--ro-bind") + 3]
    )
    assert "LOCALBENCH_WORKER_TOKEN" in " ".join(argv)
    assert argv[-3:] == (
        "-m",
        "localbench.scoring.agentic_exec.wsl_worker",
        "--localbench-worker-token=fixture-token",
    )


def test_linux_managed_spawn_guard_rejects_rootfs_argv_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed_root = tmp_path / "LocalBench"
    _active_native_runtime(managed_root)
    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")
    config = wsl_process.resolve_worker_config(
        platform_name="linux", environ={"XDG_DATA_HOME": str(tmp_path)}
    )

    with pytest.raises(ProvisioningError) as caught:
        wsl_process.validate_worker_argv(
            config,
            ("/usr/bin/python3", "-m", "localbench.scoring.agentic_exec.wsl_worker"),
            platform_name="linux",
        )

    assert caught.value.code == "managed_boundary_required"


def test_linux_managed_process_identity_anchors_outer_bwrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed_root = tmp_path / "LocalBench"
    _active_native_runtime(managed_root)
    monkeypatch.setattr(provisioner_module.platform, "system", lambda: "Linux")
    config = wsl_process.resolve_worker_config(
        platform_name="linux", environ={"XDG_DATA_HOME": str(tmp_path)}
    )
    outer = ProcessPin(412, 412, 412, 99, "/signed/rootfs/usr/bin/bwrap")

    class ProcessTable:
        def capture(self, pid: int, *, token: str | None = None) -> ProcessPin:
            assert pid == outer.pid
            assert token == "fixture-token"
            return outer

    monkeypatch.setattr(worker_process_control, "LinuxProcfs", ProcessTable)
    reported = {
        "pid": 1,
        "process_group_id": 1,
        "session_id": 1,
        "start_time_ticks": 2,
        "executable": "/opt/localbench/venv/bin/python",
        "host_pid": outer.pid,
    }

    assert (
        wsl_process.verify_reported_worker_process(
            config, token="fixture-token", reported=reported
        )
        == outer
    )


def test_native_provisioning_keeps_network_without_binding_host_paths(
    tmp_path: Path,
) -> None:
    rootfs = _active_native_runtime(tmp_path / "LocalBench")

    argv = native_worker.native_worker_argv(
        native_worker.NativeWorkerSpec(
            rootfs=rootfs,
            command=("/opt/localbench/bin/provision-appworld", "{}"),
            environment={},
            writable=True,
            network=True,
        )
    )

    assert "--unshare-all" not in argv
    assert ("--ro-bind", str(rootfs), "/") == tuple(
        argv[argv.index("--ro-bind") : argv.index("--ro-bind") + 3]
    )
    venv = rootfs / "opt/localbench/venv"
    venv_binding = ("--bind", str(venv), "/opt/localbench/venv")
    assert any(
        tuple(argv[index : index + 3]) == venv_binding for index in range(len(argv) - 2)
    )
    for index, token in enumerate(argv):
        if token in {"--ro-bind", "--bind"}:
            assert argv[index + 1].startswith(str(rootfs))
