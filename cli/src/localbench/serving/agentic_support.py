from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject

AGENTIC_SETUP_MESSAGE: Final = (
    "The agentic axis needs the managed AppWorld harness. "
    "Run `localbench setup-agentic` before starting the full-suite benchmark. "
)


@dataclass(slots=True)
class AgenticSetupError(Exception):
    detail: str
    model_download_started: bool = False
    benchmark_started: bool = False

    def __str__(self) -> str:
        if self.benchmark_started:
            work_state = "Model assets were downloaded and benchmark work may already have started."
        elif self.model_download_started:
            work_state = "Model assets may already have been downloaded; no benchmark work has started."
        else:
            work_state = "No model download or benchmark work has started."
        return f"{AGENTIC_SETUP_MESSAGE} {work_state} Setup detail: {self.detail}"


def configured_agentic_paths(
    wsl_venv_python: str | None,
    appworld_root: str | None,
) -> tuple[str, str]:
    if wsl_venv_python is None or appworld_root is None:
        raise AgenticSetupError(
            detail="set both --wsl-venv-python and --appworld-root for a managed harness",
        )
    return wsl_venv_python, appworld_root


def agentic_chat_template_kwargs(lane: str, profile: str) -> JsonObject:
    if lane in {"bounded-final-v1", "bounded-final-v2"}:
        return (
            {"enable_thinking": True}
            if profile in {"generic_think_tags_8192_v1", "gemma4_channel_8192_v1"}
            else {"enable_thinking": False}
        )
    if lane == "answer-only":
        return {"enable_thinking": False}
    return {"enable_thinking": True}


def repo_root() -> Path:
    start = Path(__file__).resolve()
    for parent in start.parents:
        if (parent / ".git").exists():
            return parent
    raise AgenticSetupError(
        detail=(
            "the installed worker has no source checkout; install the WSL worker package "
            "in the managed environment"
        ),
    )


def git_head(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()
