from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from localbench.one_shot.types import OneShotSuiteIdentity, ResolvedOneShotModel
from localbench.progress import ProgressReporter
from localbench.serving.options import ServeBenchOptions


@dataclass(frozen=True, slots=True)
class OneShotServeRequest:
    args: argparse.Namespace
    resolved: ResolvedOneShotModel
    root: Path
    suite_identity: OneShotSuiteIdentity


def build_serve_options(request: OneShotServeRequest) -> ServeBenchOptions:
    args = request.args
    resolved = request.resolved
    return ServeBenchOptions(
        runtime="llama.cpp",
        model_file=None,
        model_ref=None,
        model_id=resolved.model_id,
        server_bin=_server_bin(args),
        ctx=32768,
        determinism="strict",
        tier="standard",
        bench="all",
        lane="bounded-final-v2",
        profile="auto",
        seed=1234,
        max_items=getattr(args, "max_items", None),
        suite=request.suite_identity.release_id,
        suite_source=getattr(args, "suite_source", None),
        suite_dir=getattr(args, "suite_dir", None),
        out=request.root,
        resume=getattr(args, "resume", None),
        retry_errored=False,
        cache_dir=getattr(args, "cache_dir", None),
        threads=int(getattr(args, "threads", 8)),
        threads_batch=int(getattr(args, "threads_batch", 8)),
        reasoning_activation=None,
        hf_model_id=resolved.tokenizer_repo,
        hf_revision=resolved.tokenizer_revision,
        gguf_repo_only=resolved.tokenizer_repo is None,
        wsl_venv_python=getattr(args, "wsl_venv_python", None),
        appworld_root=getattr(args, "appworld_root", None),
        progress_reporter=ProgressReporter(),
    )


def _server_bin(args: argparse.Namespace) -> Path | None:
    value = getattr(args, "llama_server_path", None) or getattr(
        args, "server_bin", None
    )
    return value if isinstance(value, Path) else None
