from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WslWorkerConfig:
    venv_python: str
    appworld_root: str
    distro_name: str | None = None
    native_rootfs: Path | None = None
    repo_root_wsl_path: str = ""
    log_dir: Path = Path("runs") / "agentic-wsl"
    open_task_timeout_s: float = 180.0
    op_timeout_s: float = 300.0
    finalize_timeout_s: float = 120.0
    close_timeout_s: float = 5.0
    worker_argv: tuple[str, ...] | None = None
    allow_test_worker_override: bool = False
    worker_env: Mapping[str, str] | None = None
