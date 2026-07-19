from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

import localbench.cli as cli_mod
import localbench.exit_codes as exit_codes
import localbench.one_shot.runner as one_shot_runner
from localbench.appliance.worker import APPWORLD_ROOT, VENV
from localbench.coding_exec.sandbox import DockerEnv
from localbench.exit_codes import EXIT_COMPLETE, EXIT_USER_INTERRUPTED
from localbench.one_shot.runner import (
    SleepGapMonitor,
    SleepWakeClockGap,
    run_one_shot_bench,
)
from localbench.one_shot.types import FULL_EXEC_SUITE_MANIFEST_SHA256, FULL_EXEC_SUITE_RELEASE_ID
from localbench.scoring.agentic_exec.wsl_process import WslWorkerConfig
from localbench.submissions.submit_run import SubmitRunOptions
from one_shot_fixtures import REV_A, TOKENIZER_REV_A
from one_shot_runner_fakes import _args, _deps


def test_cli_bench_positional_model_dispatches_one_shot(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: argparse.Namespace | None = None

    def fake_run(args: argparse.Namespace, *, cli_version: str) -> int:
        nonlocal captured
        captured = args
        # The dispatched version must be the real installed package version, not a literal.
        assert cli_version == cli_mod._package_version()
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


def test_cli_bench_no_longer_accepts_static_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli_mod.main(["bench", "qwen3-6-27b", "--static-only"])

    assert raised.value.code == 2
    assert "unrecognized arguments: --static-only" in capsys.readouterr().err


def test_advanced_bench_still_requires_manual_model_inputs(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_mod.main(["bench", "--runtime", "llama.cpp"])

    assert code == 2
    assert "--model-file or --model-ref" in capsys.readouterr().err


def test_one_shot_missing_agentic_harness_fails_before_model_download(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a full six-axis one-shot run whose agentic harness preflight fails.
    deps = _deps(tmp_path)

    def fail_agentic_preflight(*_args, **_kwargs):
        raise one_shot_runner.AgenticSetupError(detail="configured harness is unavailable")

    deps.agentic_preflight = fail_agentic_preflight

    # When the one-shot path starts.
    code = run_one_shot_bench(
        _args(tmp_path),
        cli_version="0.3.1",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    # Then setup gets its dedicated exit before tokenizer/GGUF network work.
    assert code == exit_codes.EXIT_AGENTIC_SETUP_REQUIRED
    assert deps.hf_client.revision_calls == []
    assert deps.hf_client.snapshot_calls == []
    assert not (tmp_path / "models").exists()
    assert deps.bench_runner.options is None
    error = capsys.readouterr().err
    assert "AppWorld harness" in error
    assert "localbench setup-agentic" in error
    assert "No model download or benchmark work has started" in error


def test_one_shot_missing_docker_fails_before_model_download(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = replace(
        _deps(tmp_path),
        coding_docker_env=DockerEnv(
            platform="windows",
            desktop=False,
            rootless=False,
            runsc_available=False,
            runc_version=None,
            available=False,
        ),
    )

    code = run_one_shot_bench(
        _args(tmp_path),
        cli_version="0.4.3.dev0",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == exit_codes.EXIT_PREFLIGHT_FAILED
    assert deps.hf_client.revision_calls == []
    assert deps.hf_client.snapshot_calls == []
    assert deps.bench_runner.options is None
    assert "Docker is unavailable" in capsys.readouterr().err


def test_one_shot_resolves_selected_suite_before_any_model_asset_download(
    tmp_path: Path,
) -> None:
    deps = _deps(tmp_path)
    args = _args(tmp_path)
    args.suite_dir = tmp_path / "missing-suite"

    code = run_one_shot_bench(
        args,
        cli_version="0.3.1",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == 2
    assert deps.hf_client.revision_calls == []
    assert deps.hf_client.snapshot_calls == []
    assert deps.bench_runner.options is None


def test_one_shot_rejects_release_manifest_file_drift_before_download(tmp_path: Path) -> None:
    deps = _deps(tmp_path)
    args = _args(tmp_path)
    canonical = args.suite_dir
    tampered = tmp_path / "tampered-suite"
    shutil.copytree(canonical, tampered)
    # Template content is not covered by itemsets.lock.json, so the suite remains internally
    # consistent while diverging from the canonical release manifest's files[] identity.
    (tampered / "templates" / "math.txt").write_text("tampered\n", encoding="utf-8")
    args.suite_dir = tampered

    code = run_one_shot_bench(
        args,
        cli_version="0.3.1",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == 2
    assert deps.hf_client.revision_calls == []
    assert deps.hf_client.snapshot_calls == []
    assert deps.bench_runner.options is None


def test_one_shot_revalidates_agentic_setup_after_download_before_serving(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)
    calls = 0

    def changing_preflight(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise one_shot_runner.AgenticSetupError(detail="managed harness changed")
        return one_shot_runner.WslPreflightResult(
            identity={},
            task_ids=("task",),
            worker_config=WslWorkerConfig(
                venv_python=(VENV / "bin/python").as_posix(),
                appworld_root=APPWORLD_ROOT.as_posix(),
            ),
        )

    deps.agentic_preflight = changing_preflight

    code = run_one_shot_bench(
        _args(tmp_path),
        cli_version="0.3.1",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == exit_codes.EXIT_AGENTIC_SETUP_REQUIRED
    assert calls == 2
    assert deps.hf_client.snapshot_calls
    assert (tmp_path / "models" / "model-q4.gguf").is_file()
    error = capsys.readouterr().err
    assert "may already have been downloaded" in error
    assert "No model download or benchmark work has started" not in error


def test_one_shot_always_uses_full_identity_and_agentic_preflight(
    tmp_path: Path,
) -> None:
    deps = _deps(tmp_path)
    original_preflight = deps.agentic_preflight
    calls = 0

    def recording_agentic_preflight(*args, **kwargs):
        nonlocal calls
        calls += 1
        assert original_preflight is not None
        return original_preflight(*args, **kwargs)

    deps.agentic_preflight = recording_agentic_preflight

    code = run_one_shot_bench(
        _args(tmp_path),
        cli_version="0.3.1",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == EXIT_COMPLETE
    assert calls == 2
    assert deps.bench_runner.options is not None
    assert deps.bench_runner.options.suite == FULL_EXEC_SUITE_RELEASE_ID
    lock = json.loads((tmp_path / "plan.lock.json").read_text(encoding="utf-8"))
    assert lock["suite_release_id"] == FULL_EXEC_SUITE_RELEASE_ID
    assert lock["suite_manifest_sha256"] == FULL_EXEC_SUITE_MANIFEST_SHA256


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
            suite_dir=(
                Path(__file__).resolve().parents[2]
                / "web"
                / "public"
                / "suites"
                / "suite-v1-full-exec-6axis-v1"
            ),
            signing_key=None,
            display_name=None,
            bypass_token=None,
            bypass_token_file=None,
            dry_run=False,
        ),
    ]
    assert "submission sub_fake" in capsys.readouterr().out


def test_one_shot_submission_rejects_incomplete_post_grading_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deps = _deps(tmp_path)

    def incomplete_grader(run_path, suite_dir, *, image, docker_env):
        record = json.loads(run_path.read_text(encoding="utf-8"))
        record["headline_complete"] = False
        run_path.write_text(json.dumps(record), encoding="utf-8")
        return record

    deps.coding_grader = incomplete_grader

    code = run_one_shot_bench(
        _args(tmp_path, one_shot_submit=True),
        cli_version="0.3.1",
        deps=deps,
        is_tty=False,
        input_fn=lambda: "",
    )

    assert code == 2
    assert deps.submitter.calls == []
    error = capsys.readouterr().err
    assert "incomplete_run" in error


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
