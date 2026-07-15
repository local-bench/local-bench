from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from localbench._types import JsonObject
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.provisioner import (
    FINAL_DISTRO_PREFIX,
    ProvisioningError,
    appliance_root,
)
_DEFAULT_OPEN_TASK_TIMEOUT_S = 180.0
_DEFAULT_OPERATION_TIMEOUT_S = 300.0
_DEFAULT_FINALIZE_TIMEOUT_S = 120.0
_DEFAULT_CLOSE_TIMEOUT_S = 5.0
_WORKER_MODULE = "localbench.scoring.agentic_exec.wsl_worker"


@dataclass(frozen=True, slots=True)
class WslWorkerConfig:
    venv_python: str
    appworld_root: str
    distro_name: str | None = None
    repo_root_wsl_path: str = ""
    log_dir: Path = Path("runs") / "agentic-wsl"
    open_task_timeout_s: float = _DEFAULT_OPEN_TASK_TIMEOUT_S
    op_timeout_s: float = _DEFAULT_OPERATION_TIMEOUT_S
    finalize_timeout_s: float = _DEFAULT_FINALIZE_TIMEOUT_S
    close_timeout_s: float = _DEFAULT_CLOSE_TIMEOUT_S
    worker_argv: tuple[str, ...] | None = None
    worker_env: Mapping[str, str] | None = None


def worker_argv(config: WslWorkerConfig) -> tuple[str, ...]:
    if config.worker_argv is not None:
        return config.worker_argv
    if config.distro_name is None:
        return (config.venv_python, "-m", _WORKER_MODULE)
    return (
        "wsl.exe",
        "-d",
        config.distro_name,
        "--exec",
        "/usr/bin/env",
        "-i",
        "HOME=/home/lbworker",
        f"APPWORLD_ROOT={config.appworld_root}",
        "PYTHONHASHSEED=0",
        "TZ=UTC",
        "LC_ALL=C.UTF-8",
        f"PATH={PurePosixPath(config.venv_python).parent}:/usr/bin:/bin",
        config.venv_python,
        "-m",
        _WORKER_MODULE,
    )


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
    if platform_name.startswith("linux"):
        resolved_root = appworld_root or environment.get("APPWORLD_ROOT")
        if not resolved_root:
            raise ProvisioningError(
                "appworld_root_missing",
                "APPWORLD_ROOT is unset for native Linux execution",
                "Set APPWORLD_ROOT and retry",
            )
        return WslWorkerConfig(
            venv_python=direct_python or sys.executable,
            appworld_root=resolved_root,
            log_dir=log_dir or Path("runs") / "agentic-wsl",
        )
    raise ProvisioningError(
        "unsupported_platform",
        platform_name,
        "Use x64 Windows 11 or native Linux",
    )


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


def worker_env(config: WslWorkerConfig) -> dict[str, str]:
    if config.distro_name is None and sys.platform.startswith("linux"):
        env = {
            "HOME": os.environ.get("HOME", "/home/lbworker"),
            "PATH": f"{PurePosixPath(config.venv_python).parent}:/usr/bin:/bin",
        }
    else:
        env = {
            key: os.environ[key]
            for key in ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP")
            if key in os.environ
        }
    env.update({"APPWORLD_ROOT": config.appworld_root, "PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C.UTF-8"})
    if config.worker_env is not None:
        env.update(dict(config.worker_env))
    return env


def kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        return
    except (subprocess.TimeoutExpired, OSError):
        pass
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def safe_label(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
