from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import localbench.cli as cli_mod
from localbench.campaign_checkpoints import CheckpointCorruptionError
from localbench.exit_codes import EXIT_CHECKPOINT_CORRUPTION, EXIT_UNSAFE_RESUME
from localbench.orchestrate import UnsafeResumeError


@pytest.mark.parametrize(
    ("error", "expected_exit"),
    (
        (UnsafeResumeError("unsafe resume refused"), EXIT_UNSAFE_RESUME),
        (CheckpointCorruptionError("corrupt checkpoint"), EXIT_CHECKPOINT_CORRUPTION),
    ),
)
def test_bench_returns_dedicated_exit_code_for_resume_and_checkpoint_errors(
    error: RuntimeError,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the bench-managed runner raises a dedicated resume/checkpoint error.
    def fake_anyio_run(function, options) -> None:
        raise error

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)

    # When / Then: _bench preserves the same exit-code contract as _run.
    assert cli_mod._bench(_bench_args()) == expected_exit


def _bench_args() -> argparse.Namespace:
    return argparse.Namespace(
        runtime="llama.cpp",
        model_file=Path("model.gguf"),
        model_ref=None,
        model_id="gemma",
        server_bin=Path("llama-server.exe"),
        ctx=32768,
        determinism="strict",
        tier="standard",
        bench="all",
        lane="answer-only",
        seed=1234,
        max_items=None,
        suite="core-text-v1",
        suite_source=None,
        suite_dir=None,
        out=Path("runs/bench/gemma"),
        resume=None,
        cache_dir=None,
        threads=8,
        threads_batch=8,
    )
