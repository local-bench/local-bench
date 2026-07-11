from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from localbench.bounded_final_profiles import BoundedFinalProfileChoice
from localbench.orchestrate import LaneChoice, ReasoningActivationChoice, TierChoice
from localbench.progress import ProgressReporter
from localbench.scoring.agentic_exec.wsl_bridge import WslPreflightResult
from localbench.suite_resolver import DEFAULT_SUITE_ID


@dataclass(frozen=True, slots=True)
class ServeBenchOptions:
    runtime: str
    model_file: Path | None
    model_ref: str | None
    model_id: str
    server_bin: Path | None
    ctx: int | None
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
    hf_revision: str | None = None
    gguf_repo_only: bool = False
    wsl_venv_python: str | None = None
    appworld_root: str | None = None
    agentic_preflight: WslPreflightResult | None = None
    progress_reporter: ProgressReporter | None = None
    wsl_distro: str | None = None
    vllm_venv: str | None = None
    vllm_bin: str | None = None
    vllm_dtype: str = "bfloat16"
    vllm_max_model_len: int | None = None
    sglang_venv: str | None = None
    sglang_python: str | None = None
    sglang_dtype: str = "bfloat16"
    sglang_max_model_len: int | None = None
    determinism_canary: bool = False
