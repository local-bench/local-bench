from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from localbench.bounded_final_profiles import BoundedFinalProfileChoice
from localbench.orchestrate import LaneChoice, ReasoningActivationChoice, TierChoice
from localbench.suite_resolver import DEFAULT_SUITE_ID


@dataclass(frozen=True, slots=True)
class ServeBenchOptions:
    runtime: str
    model_file: Path | None
    model_ref: str | None
    model_id: str
    server_bin: Path | None
    ctx: int
    determinism: str
    tier: TierChoice
    bench: str
    lane: LaneChoice
    seed: int
    profile: BoundedFinalProfileChoice = "auto"
    max_items: int | None = None
    suite: str = DEFAULT_SUITE_ID
    suite_source: Path | None = None
    suite_dir: Path | None = None
    out: Path | None = None
    resume: Path | None = None
    retry_errored: bool = False
    cache_dir: Path | None = None
    threads: int = 8
    threads_batch: int = 8
    reasoning_activation: ReasoningActivationChoice | None = None
    hf_model_id: str | None = None
    gguf_repo_only: bool = False
    wsl_venv_python: str = "~/appworld-harness/venv/bin/python3"
    appworld_root: str = "/home/michael/appworld-data"
