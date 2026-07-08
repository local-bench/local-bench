from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import localbench.cli as cli_mod
from localbench.exit_codes import EXIT_COMPLETE, EXIT_USER_INTERRUPTED
from localbench.one_shot.runner import (
    SleepGapMonitor,
    SleepWakeClockGap,
    run_one_shot_bench,
)
from localbench.one_shot.types import FULL_EXEC_SUITE_MANIFEST_SHA256, FULL_EXEC_SUITE_RELEASE_ID
from localbench.submissions.submit_run import SubmitRunOptions
from one_shot_fixtures import REV_A, TOKENIZER_REV_A
from one_shot_runner_fakes import _args, _deps


def test_cli_bench_positional_model_dispatches_one_shot(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: argparse.Namespace | None = None

    def fake_run(args: argparse.Namespace, *, cli_version: str) -> int:
        nonlocal captured
        captured = args
        assert cli_version != "0.3.0"
        return EXIT_COMPLETE

    monkeypatch.setattr(cli_mod, "run_one_shot_bench", fake_run)

    code = cli_mod.main(
        [
            "bench",
            "qwen3-6-27b",
            "--yes",
            "--no-submit",
            "--accept-suite-terms",
            "--vram-gb",
            "24",
            "--llama-server-path",
            "llama-server.exe",
        ],
    )

    assert code == EXIT_COMPLETE
    assert captured is not None
    assert captured.one_shot_model == "qwen3-6-27b"
    assert captured.one_shot_submit is False
    assert captured.llama_server_path == Path("llama-server.exe")


def test_advanced_bench_still_requires_manual_model_inputs(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_mod.main(["bench", "--runtime", "llama.cpp"])

    assert code == 2
    assert "--model-file or --model-ref" in capsys.readouterr().err


def test_one_shot_runner_prompts_submit_default_no_and_builds_bounded_final_options(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)
    args = _args(tmp_path, one_shot_submit=None)

    code = run_one_shot_bench(args, cli_version="0.2.5", deps=deps, is_tty=True, input_fn=lambda: "")

    assert code == EXIT_COMPLETE
    assert deps.submitter.calls == []
    assert deps.bench_runner.options is not None
    options = deps.bench_runner.options
    assert options.lane == "bounded-final-v2"
    assert options.ctx == 32768
    assert options.seed == 1234
    assert options.model_file == tmp_path / "models" / "model-q4.gguf"
    assert options.model_ref is None
    assert options.hf_model_id == "owner/base-model"
    assert options.hf_revision == TOKENIZER_REV_A
    assert options.gguf_repo_only is False
    lock = json.loads((tmp_path / "plan.lock.json").read_text(encoding="utf-8"))
    assert lock["artifact_revision"] == REV_A
    assert lock["suite_manifest_sha256"] == FULL_EXEC_SUITE_MANIFEST_SHA256
    output = capsys.readouterr().out
    assert "submit? [y/N]" in output
    assert "submit    skipped" in output


def test_one_shot_submit_true_uses_existing_submit_finished_run_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)

    code = run_one_shot_bench(
        _args(tmp_path, one_shot_submit=True),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == EXIT_COMPLETE
    assert deps.submitter.calls == [
        SubmitRunOptions(
            site="https://local-bench.ai",
            run=tmp_path / "localbench-run.json",
            bundle=None,
            suite_dir=None,
            signing_key=None,
            display_name=None,
            bypass_token=None,
            bypass_token_file=None,
            dry_run=False,
        ),
    ]
    assert "submission sub_fake" in capsys.readouterr().out


def test_one_shot_offline_forces_local_only_and_skips_publishability_preflight(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)

    code = run_one_shot_bench(
        _args(tmp_path, offline=True, one_shot_submit=False),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == EXIT_COMPLETE
    assert deps.preflight_http.calls == []
    assert deps.submitter.calls == []
    assert "offline local-only" in capsys.readouterr().out


def test_one_shot_raw_hf_repo_runs_local_only_and_skips_preflight_submit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)
    args = _args(tmp_path, one_shot_submit=False)
    args.one_shot_model = "owner/raw-gguf"

    code = run_one_shot_bench(args, cli_version="0.2.5", deps=deps, is_tty=False, input_fn=lambda: "")

    assert code == EXIT_COMPLETE
    assert deps.raw_artifact_resolver.calls == [("owner/raw-gguf", "Q4_K_M")]
    assert deps.preflight_http.calls == []
    assert deps.submitter.calls == []
    assert "raw HF repos are LOCAL-ONLY" in capsys.readouterr().out


def test_one_shot_resume_refuses_plan_lock_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "plan.lock.json").write_text(
        json.dumps(
            {
                "schema_version": "localbench.one_shot_plan.v1",
                "requested_model": "qwen3-6-27b",
                "quant_label": "Q4_K_M",
                "artifact_revision": "b" * 40,
                "artifact_filename": "model-q4.gguf",
                "suite_release_id": FULL_EXEC_SUITE_RELEASE_ID,
                "suite_manifest_sha256": FULL_EXEC_SUITE_MANIFEST_SHA256,
                "cli_version": "0.2.5",
            },
        ),
        encoding="utf-8",
    )
    deps = _deps(tmp_path)

    code = run_one_shot_bench(
        _args(tmp_path, resume=tmp_path),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == 2
    assert deps.bench_runner.options is None
    assert "artifact_revision" in capsys.readouterr().err


def test_one_shot_ctrl_c_returns_user_interrupted_and_never_submits(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)
    deps.bench_runner.raise_keyboard_interrupt = True

    code = run_one_shot_bench(
        _args(tmp_path, one_shot_submit=True),
        cli_version="0.2.5",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == EXIT_USER_INTERRUPTED
    assert deps.submitter.calls == []
    assert "interrupted" in capsys.readouterr().err


def test_sleep_gap_monitor_aborts_without_allow_sleep_risk() -> None:
    monitor = SleepGapMonitor(threshold_seconds=60.0, allow_sleep_risk=False)
    monitor.checkpoint(wall_seconds=1000.0, monotonic_seconds=100.0)

    with pytest.raises(SleepWakeClockGap, match="sleep/wake clock gap"):
        monitor.checkpoint(wall_seconds=1400.0, monotonic_seconds=110.0)

    allowed = SleepGapMonitor(threshold_seconds=60.0, allow_sleep_risk=True)
    allowed.checkpoint(wall_seconds=1000.0, monotonic_seconds=100.0)
    allowed.checkpoint(wall_seconds=1400.0, monotonic_seconds=110.0)
