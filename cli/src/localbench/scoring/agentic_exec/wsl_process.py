from __future__ import annotations

import os
import secrets
import sys
from pathlib import PurePosixPath

from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.native_worker import NativeWorkerSpec, native_worker_argv
from localbench.appliance.provisioner import ProvisioningError
from localbench.scoring.agentic_exec.worker_config import WslWorkerConfig
from localbench.scoring.agentic_exec.worker_process_control import (
    creation_flags,
    terminate_worker_process_tree,
    verify_reported_worker_process,
    verify_worker_process_tree_terminated,
)
from localbench.scoring.agentic_exec.worker_resolution import resolve_worker_config
from localbench.scoring.agentic_exec.wsl_teardown import WORKER_TOKEN_ENV

__all__ = (
    "WslWorkerConfig",
    "creation_flags",
    "resolve_worker_config",
    "terminate_worker_process_tree",
    "verify_reported_worker_process",
    "verify_worker_process_tree_terminated",
)

_WORKER_MODULE = "localbench.scoring.agentic_exec.wsl_worker"
_TEST_WORKER_PLATFORM = "localbench-test-worker"


def worker_argv(
    config: WslWorkerConfig,
    *,
    worker_token: str | None = None,
    platform_name: str | None = None,
) -> tuple[str, ...]:
    resolved_platform = sys.platform if platform_name is None else platform_name
    if config.worker_argv is not None:
        if (
            not config.allow_test_worker_override
            or resolved_platform != _TEST_WORKER_PLATFORM
        ):
            raise ProvisioningError(
                "test_worker_override_required",
                "worker_argv overrides are disabled for managed execution",
                "Use the resolved managed worker configuration",
            )
        return config.worker_argv
    if config.native_rootfs is not None:
        environment = {
            "HOME": "/home/lbworker",
            "APPWORLD_ROOT": "/home/lbworker/appworld",
            "LOCALBENCH_RUNTIME_TOPOLOGY": "native-linux-bubblewrap",
            "PATH": "/opt/localbench/venv/bin:/usr/bin:/bin",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TZ": "UTC",
            "LC_ALL": "C.UTF-8",
        }
        token_argument: tuple[str, ...] = ()
        if worker_token is not None:
            environment[WORKER_TOKEN_ENV] = worker_token
            token_argument = (f"--localbench-worker-token={worker_token}",)
        return native_worker_argv(
            NativeWorkerSpec(
                rootfs=config.native_rootfs,
                command=(
                    "/opt/localbench/venv/bin/python",
                    "-m",
                    _WORKER_MODULE,
                    *token_argument,
                ),
                environment=environment,
                writable=False,
                network=False,
            )
        )
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


def validate_worker_argv(
    config: WslWorkerConfig,
    argv: tuple[str, ...],
    *,
    platform_name: str,
) -> None:
    from localbench.appliance.provisioner import FINAL_DISTRO_PREFIX, ProvisioningError
    from localbench.appliance.worker import APPWORLD_ROOT as managed_appworld_root
    from localbench.appliance.worker import VENV as managed_venv

    if platform_name.startswith("linux") and config.native_rootfs is not None:
        rootfs = config.native_rootfs
        root_binding = ("--ro-bind", str(rootfs), "/")
        binding_present = any(
            argv[index : index + 3] == root_binding for index in range(len(argv) - 2)
        )
        if (
            config.distro_name is not None
            or config.venv_python != str(rootfs / "opt/localbench/venv/bin/python")
            or config.appworld_root != str(rootfs / "home/lbworker/appworld")
            or not argv
            or argv[0] != str(rootfs / "lib64/ld-linux-x86-64.so.2")
            or str(rootfs / "usr/bin/bwrap") not in argv
            or "--unshare-all" not in argv
            or not binding_present
        ):
            raise ProvisioningError(
                "managed_boundary_required",
                "Linux worker argv is not pinned to the managed native rootfs",
                "Run 'localbench setup-agentic' and retry",
            )
        return
    if platform_name != "win32":
        return
    # The spawn boundary must reject ANY unpinned invocation regardless of how the config was
    # produced (test-override flag, or a caller-supplied preflight that skipped
    # resolve_worker_config). Validate the full pinned form: the wsl -d <managed> --exec prefix
    # AND the interpreter + AppWorld root, which are the caller-controlled config fields that
    # worker_argv() interpolates into the executable and environment.
    managed_distro = f"{FINAL_DISTRO_PREFIX}{PINNED_RUNTIME_ID}"
    managed_python = (managed_venv / "bin/python").as_posix()
    managed_appworld = managed_appworld_root.as_posix()
    if (
        config.distro_name != managed_distro
        or config.venv_python != managed_python
        or config.appworld_root != managed_appworld
        or argv[:4] != ("wsl.exe", "-d", managed_distro, "--exec")
    ):
        raise ProvisioningError(
            "managed_boundary_required",
            "Windows worker argv is not pinned to the managed distro, interpreter, and AppWorld root",
            "Run 'localbench setup-agentic' and retry",
        )


def worker_env(
    config: WslWorkerConfig,
    *,
    worker_token: str | None = None,
) -> dict[str, str]:
    if config.native_rootfs is not None:
        env = {
            "HOME": os.environ.get("HOME", "/home/lbworker"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
    elif config.distro_name is None and sys.platform.startswith("linux"):
        env = {
            "HOME": os.environ.get("HOME", "/home/lbworker"),
            "PATH": f"{PurePosixPath(config.venv_python).parent}:/usr/bin:/bin",
        }
    else:
        env = {
            key: os.environ[key]
            for key in (
                "SYSTEMROOT",
                "WINDIR",
                "PATH",
                "PATHEXT",
                "COMSPEC",
                "TEMP",
                "TMP",
            )
            if key in os.environ
        }
    if config.native_rootfs is None:
        env.update(
            {
                "APPWORLD_ROOT": config.appworld_root,
                "PYTHONHASHSEED": "0",
                "TZ": "UTC",
                "LC_ALL": "C.UTF-8",
            }
        )
    if worker_token is not None:
        env[WORKER_TOKEN_ENV] = worker_token
    if config.worker_env is not None:
        env.update(dict(config.worker_env))
    return env


def new_worker_token() -> str:
    return secrets.token_hex(16)


def safe_label(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
