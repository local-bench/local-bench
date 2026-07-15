from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from localbench._types import JsonObject
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.provisioner import FINAL_DISTRO_PREFIX, ProvisioningError, appliance_root
from localbench.scoring.agentic_exec.wsl_teardown import LinuxProcfs, ProcessPin, TeardownError
from localbench.scoring.agentic_exec.wsl_teardown import WORKER_TOKEN_ENV, terminate_linux_worker
from localbench.scoring.agentic_exec.wsl_teardown import verify_linux_worker_terminated

_DEFAULT_OPEN_TASK_TIMEOUT_S = 180.0
_DEFAULT_OPERATION_TIMEOUT_S = 300.0
_DEFAULT_FINALIZE_TIMEOUT_S = 120.0
_DEFAULT_CLOSE_TIMEOUT_S = 5.0
_WORKER_MODULE = "localbench.scoring.agentic_exec.wsl_worker"
_TEARDOWN_MODULE = "localbench.scoring.agentic_exec.wsl_teardown"


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
    allow_test_worker_override: bool = False
    worker_env: Mapping[str, str] | None = None


def worker_argv(
    config: WslWorkerConfig,
    *,
    worker_token: str | None = None,
) -> tuple[str, ...]:
    if config.worker_argv is not None:
        if not config.allow_test_worker_override:
            raise ProvisioningError(
                "test_worker_override_required",
                "worker_argv overrides are disabled for managed execution",
                "Use the resolved managed worker configuration",
            )
        return config.worker_argv
    if config.distro_name is None:
        command = (config.venv_python, "-m", _WORKER_MODULE)
        if worker_token is not None:
            return (*command, f"--localbench-worker-token={worker_token}")
        return command
    token_environment = (
        (f"{WORKER_TOKEN_ENV}={worker_token}",) if worker_token is not None else ()
    )
    session_launcher = ("/usr/bin/setsid", "--wait") if worker_token is not None else ()
    token_argument = (
        (f"--localbench-worker-token={worker_token}",)
        if worker_token is not None
        else ()
    )
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
        *token_environment,
        *session_launcher,
        config.venv_python,
        "-m",
        _WORKER_MODULE,
        *token_argument,
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
        if _running_inside_wsl(environment):
            raise ProvisioningError(
                "managed_boundary_required",
                "direct Linux execution is disabled when the CLI is running inside WSL",
                "Run LocalBench from Windows so it can select the managed distro",
            )
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


def validate_worker_argv(
    config: WslWorkerConfig,
    argv: tuple[str, ...],
    *,
    platform_name: str,
) -> None:
    if platform_name != "win32" or config.allow_test_worker_override:
        return
    managed_distro = f"{FINAL_DISTRO_PREFIX}{PINNED_RUNTIME_ID}"
    if config.distro_name != managed_distro or argv[:4] != (
        "wsl.exe",
        "-d",
        managed_distro,
        "--exec",
    ):
        raise ProvisioningError(
            "managed_boundary_required",
            "Windows worker argv is not pinned to the managed distro",
            "Run 'localbench setup-agentic' and retry",
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


def worker_env(
    config: WslWorkerConfig,
    *,
    worker_token: str | None = None,
) -> dict[str, str]:
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
    if worker_token is not None:
        env[WORKER_TOKEN_ENV] = worker_token
    if config.worker_env is not None:
        env.update(dict(config.worker_env))
    return env


def new_worker_token() -> str:
    return secrets.token_hex(16)


def verify_reported_worker_process(
    config: WslWorkerConfig,
    *,
    token: str,
    reported: object,
) -> ProcessPin:
    pin = ProcessPin.from_json(reported)
    if pin.pid != pin.process_group_id or pin.process_group_id != pin.session_id:
        raise TeardownError("worker is not the leader of its pinned process group and session")
    if config.distro_name is not None:
        verified = _run_managed_control(config, "verify", token=token, pin=pin)
        if ProcessPin.from_json(verified) != pin:
            raise TeardownError("managed worker identity changed during verification")
        return pin
    live = LinuxProcfs().capture(pin.pid, token=token)
    if live != pin:
        raise TeardownError("native Linux worker identity differs from its process record")
    return pin


def terminate_worker_process_tree(
    config: WslWorkerConfig,
    proc: subprocess.Popen[bytes],
    *,
    token: str | None,
    pin: ProcessPin | None,
) -> None:
    if token is not None:
        resolved_pin = pin or _discover_worker_process(config, token=token)
        if config.distro_name is not None:
            _run_managed_control(config, "terminate", token=token, pin=resolved_pin)
        else:
            terminate_linux_worker(resolved_pin, token=token)
    _terminate_retained_process_handle(proc)


def verify_worker_process_tree_terminated(
    config: WslWorkerConfig,
    *,
    token: str,
    pin: ProcessPin,
) -> None:
    if config.distro_name is not None:
        _run_managed_control(config, "verify-terminated", token=token, pin=pin)
    else:
        verify_linux_worker_terminated(pin, token=token)


def _discover_worker_process(config: WslWorkerConfig, *, token: str) -> ProcessPin:
    if config.distro_name is not None:
        return ProcessPin.from_json(_run_managed_control(config, "discover", token=token))
    return LinuxProcfs().find_worker(token=token)


def _run_managed_control(
    config: WslWorkerConfig,
    operation: str,
    *,
    token: str,
    pin: ProcessPin | None = None,
) -> JsonObject:
    if config.distro_name is None:
        raise TeardownError("managed worker control requires a distro")
    arguments = [operation, token]
    if pin is not None:
        arguments.extend(
            [
                str(pin.pid),
                str(pin.process_group_id),
                str(pin.session_id),
                str(pin.start_time_ticks),
                pin.executable,
            ],
        )
    command = [
        "wsl.exe",
        "-d",
        config.distro_name,
        "--exec",
        "/usr/bin/env",
        "-i",
        "HOME=/home/lbworker",
        f"PATH={PurePosixPath(config.venv_python).parent}:/usr/bin:/bin",
        config.venv_python,
        "-m",
        _TEARDOWN_MODULE,
        *arguments,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=15.0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TeardownError(f"managed worker {operation} command failed: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
        raise TeardownError(
            f"managed worker {operation} failed with exit {completed.returncode}: {detail}",
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise TeardownError(f"managed worker {operation} returned invalid JSON") from error
    if not isinstance(result, dict):
        raise TeardownError(f"managed worker {operation} returned a non-object result")
    return result


def _terminate_retained_process_handle(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError as error:
            if proc.poll() is None:
                raise TeardownError(f"host worker termination failed: {error}") from error
    try:
        returncode = proc.wait(timeout=5.0)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TeardownError(f"host worker did not terminate: {error}") from error
    if returncode is None:
        raise TeardownError("host worker termination returned no exit status")


def creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def safe_label(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
