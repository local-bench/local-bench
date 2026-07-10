from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WslWorkerConfig:
    repo_root_wsl_path: str
    venv_python: str
    appworld_root: str
    log_dir: Path = Path("runs") / "agentic-wsl"
    open_task_timeout_s: float = 180.0
    op_timeout_s: float = 300.0
    finalize_timeout_s: float = 120.0
    close_timeout_s: float = 5.0
    worker_argv: tuple[str, ...] | None = None
    worker_env: Mapping[str, str] | None = None


def worker_argv(config: WslWorkerConfig) -> tuple[str, ...]:
    if config.worker_argv is not None:
        return config.worker_argv
    command = " && ".join(
        [
            f"export APPWORLD_ROOT={shlex.quote(config.appworld_root)}",
            "export PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8",
            'export PATH="$HOME/.local/bin:$PATH"',
            f"{quote_wsl_executable(config.venv_python)} -m localbench.scoring.agentic_exec.wsl_worker",
        ],
    )
    return ("wsl.exe", "bash", "-lc", command)


def quote_wsl_executable(path: str) -> str:
    if path == "~" or path.startswith("~/"):
        return '"$HOME"' + shlex.quote(path[1:])
    return shlex.quote(path)


def worker_env(config: WslWorkerConfig) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "APPWORLD_ROOT": config.appworld_root,
            "PYTHONHASHSEED": "0",
            "TZ": "UTC",
            "LC_ALL": "C.UTF-8",
        },
    )
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
