from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from localbench._types import JsonObject
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.provisioner import (
    FINAL_DISTRO_PREFIX,
    ProvisioningError,
    appliance_root,
)
from localbench.scoring.agentic_exec.worker_config import WslWorkerConfig


def resolve_worker_config(
    *,
    platform_name: str,
    environ: Mapping[str, str] | None = None,
    direct_python: str | None = None,
    appworld_root: str | None = None,
    log_dir: Path | None = None,
) -> WslWorkerConfig:
    environment = dict(os.environ if environ is None else environ)
    if platform_name == "win32":
        return _resolve_windows_worker(
            environment, direct_python, appworld_root, log_dir
        )
    if platform_name.startswith("linux"):
        return _resolve_linux_worker(environment, direct_python, appworld_root, log_dir)
    raise ProvisioningError(
        "unsupported_platform",
        platform_name,
        "Use x64 Windows 11 or native Linux",
    )


def _resolve_windows_worker(
    environment: Mapping[str, str],
    direct_python: str | None,
    appworld_root: str | None,
    log_dir: Path | None,
) -> WslWorkerConfig:
    from localbench.appliance.worker import APPWORLD_ROOT as managed_appworld_root
    from localbench.appliance.worker import VENV as managed_venv

    if direct_python is not None or appworld_root is not None:
        raise ProvisioningError(
            "managed_runtime_required",
            "Windows agentic execution supports the managed runtime only",
            "Run 'localbench setup-agentic'",
        )
    root = appliance_root(environment)
    active = _read_runtime_json(root / "active.json")
    runtime_id = active.get("runtime_id")
    distro_name = active.get("distro_name")
    if (
        active.get("schema") != "localbench.appliance_active.v1"
        or runtime_id != PINNED_RUNTIME_ID
        or not isinstance(distro_name, str)
        or distro_name != FINAL_DISTRO_PREFIX + runtime_id
    ):
        raise _runtime_not_ready(root / "active.json")
    state = _read_runtime_json(root / "WSL" / runtime_id / "state.json")
    if (
        state.get("schema") != "localbench.appliance_state.v1"
        or state.get("runtime_id") != runtime_id
        or state.get("state") != "active"
        or state.get("distro_name") != distro_name
    ):
        raise _runtime_not_ready(root / "WSL" / runtime_id / "state.json")
    return WslWorkerConfig(
        distro_name=distro_name,
        venv_python=(managed_venv / "bin/python").as_posix(),
        appworld_root=managed_appworld_root.as_posix(),
        log_dir=log_dir or Path("runs") / "agentic-wsl",
    )


def _resolve_linux_worker(
    environment: Mapping[str, str],
    direct_python: str | None,
    appworld_root: str | None,
    log_dir: Path | None,
) -> WslWorkerConfig:
    if direct_python is not None or appworld_root is not None:
        if _running_inside_wsl(environment):
            raise ProvisioningError(
                "managed_boundary_required",
                "direct Linux execution is disabled when the CLI is running inside WSL",
                "Use the managed native appliance",
            )
        resolved_root = appworld_root or environment.get("APPWORLD_ROOT")
        if not resolved_root:
            raise ProvisioningError(
                "appworld_root_missing",
                "APPWORLD_ROOT is unset for direct Linux execution",
                "Set APPWORLD_ROOT and retry",
            )
        return WslWorkerConfig(
            venv_python=direct_python or sys.executable,
            appworld_root=resolved_root,
            log_dir=log_dir or Path("runs") / "agentic-wsl",
        )
    root = appliance_root(environment)
    active_path = root / "active.json"
    active = _read_runtime_json(active_path)
    runtime_id = active.get("runtime_id")
    if (
        active.get("schema") != "localbench.appliance_active.v1"
        or runtime_id != PINNED_RUNTIME_ID
        or "distro_name" in active
    ):
        raise _runtime_not_ready(active_path)
    state_path = root / "native" / runtime_id / "state.json"
    state = _read_runtime_json(state_path)
    if (
        state.get("schema") != "localbench.appliance_state.v1"
        or state.get("runtime_id") != runtime_id
        or state.get("state") != "active"
        or "distro_name" in state
    ):
        raise _runtime_not_ready(state_path)
    rootfs = root / "native" / runtime_id / "rootfs"
    managed_python = rootfs / "opt/localbench/venv/bin/python"
    managed_appworld = rootfs / "home/lbworker/appworld"
    if (
        not rootfs.is_dir()
        or not managed_python.is_file()
        or not managed_appworld.is_dir()
    ):
        raise _runtime_not_ready(rootfs)
    return WslWorkerConfig(
        venv_python=str(managed_python),
        appworld_root=str(managed_appworld),
        native_rootfs=rootfs,
        log_dir=log_dir or Path("runs") / "agentic-wsl",
    )


def _running_inside_wsl(environment: Mapping[str, str]) -> bool:
    if environment.get("WSL_DISTRO_NAME") or environment.get("WSL_INTEROP"):
        return True
    for path in (Path("/proc/sys/kernel/osrelease"), Path("/proc/version")):
        try:
            if "microsoft" in path.read_text(encoding="utf-8").casefold():
                return True
        except (FileNotFoundError, OSError, UnicodeError):
            continue
    return False


def _read_runtime_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _runtime_not_ready(path) from error
    if not isinstance(value, dict):
        raise _runtime_not_ready(path)
    return value


def _runtime_not_ready(path: Path) -> ProvisioningError:
    return ProvisioningError(
        "managed_runtime_not_ready",
        str(path),
        "Run 'localbench setup-agentic'",
    )
