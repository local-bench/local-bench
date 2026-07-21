from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import PurePosixPath

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.worker_config import WslWorkerConfig
from localbench.scoring.agentic_exec.wsl_teardown import (
    LinuxProcfs,
    ProcessPin,
    TeardownError,
    terminate_linux_worker,
    verify_linux_worker_terminated,
)

_TEARDOWN_MODULE = "localbench.scoring.agentic_exec.wsl_teardown"


def verify_reported_worker_process(
    config: WslWorkerConfig,
    *,
    token: str,
    reported: object,
) -> ProcessPin:
    pin = ProcessPin.from_json(reported)
    if config.native_rootfs is not None:
        if not isinstance(reported, dict):
            raise TeardownError("native managed worker process identity is invalid")
        host_pid = reported.get("host_pid")
        if not isinstance(host_pid, int) or isinstance(host_pid, bool):
            raise TeardownError("native managed worker host pid is unavailable")
        live = LinuxProcfs().capture(host_pid, token=token)
        if (
            live.pid != live.process_group_id
            or live.process_group_id != live.session_id
        ):
            raise TeardownError(
                "native rootfs launcher is not its process group leader"
            )
        return live
    if pin.pid != pin.process_group_id or pin.process_group_id != pin.session_id:
        raise TeardownError(
            "worker is not the leader of its pinned process group and session"
        )
    if config.distro_name is not None:
        verified = _run_managed_control(config, "verify", token=token, pin=pin)
        if ProcessPin.from_json(verified) != pin:
            raise TeardownError("managed worker identity changed during verification")
        return pin
    live = LinuxProcfs().capture(pin.pid, token=token)
    if live != pin:
        raise TeardownError(
            "native Linux worker identity differs from its process record"
        )
    return pin


def terminate_worker_process_tree(
    config: WslWorkerConfig,
    proc: subprocess.Popen[bytes],
    *,
    token: str | None,
    pin: ProcessPin | None,
) -> None:
    if token is not None:
        if pin is not None:
            resolved_pin = pin
        elif config.native_rootfs is not None:
            resolved_pin = LinuxProcfs().capture(proc.pid, token=token)
        else:
            resolved_pin = _discover_worker_process(config, token=token)
        if config.distro_name is not None:
            try:
                _run_managed_control(
                    config,
                    "terminate",
                    token=token,
                    pin=resolved_pin,
                )
            except TeardownError:
                time.sleep(0.25)
                _run_managed_control(
                    config,
                    "terminate",
                    token=token,
                    pin=resolved_pin,
                )
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
        try:
            _run_managed_control(
                config,
                "verify-terminated",
                token=token,
                pin=pin,
            )
        except TeardownError:
            time.sleep(0.25)
            _run_managed_control(
                config,
                "verify-terminated",
                token=token,
                pin=pin,
            )
    else:
        verify_linux_worker_terminated(pin, token=token)


def creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def _discover_worker_process(config: WslWorkerConfig, *, token: str) -> ProcessPin:
    if config.distro_name is not None:
        try:
            reported = _run_managed_control(config, "discover", token=token)
        except TeardownError:
            time.sleep(0.25)
            reported = _run_managed_control(config, "discover", token=token)
        return ProcessPin.from_json(reported)
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
        raise TeardownError(
            f"managed worker {operation} command failed: {error}"
        ) from error
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "no diagnostic output"
        )
        raise TeardownError(
            f"managed worker {operation} failed with exit {completed.returncode}: {detail}",
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise TeardownError(
            f"managed worker {operation} returned invalid JSON"
        ) from error
    if not isinstance(result, dict):
        raise TeardownError(f"managed worker {operation} returned a non-object result")
    return result


def _terminate_retained_process_handle(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError as error:
            if proc.poll() is None:
                raise TeardownError(
                    f"host worker termination failed: {error}"
                ) from error
    try:
        returncode = proc.wait(timeout=5.0)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TeardownError(f"host worker did not terminate: {error}") from error
    if returncode is None:
        raise TeardownError("host worker termination returned no exit status")
