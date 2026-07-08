from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

import localbench.cli as cli_mod
from localbench.exit_codes import EXIT_COMPLETE, EXIT_USER_INTERRUPTED
from localbench.one_shot.runner import (
    OneShotRunnerDeps,
    SleepGapMonitor,
    SleepWakeClockGap,
    run_one_shot_bench,
)
from localbench.one_shot.types import FULL_EXEC_SUITE_MANIFEST_SHA256, FULL_EXEC_SUITE_RELEASE_ID
from localbench.submissions.submit_run import SubmitRunOptions, SubmitRunResult


_REV = "a" * 40
_MODEL_BYTES = b"GGUF one-shot fixture"
_MODEL_SHA = hashlib.sha256(_MODEL_BYTES).hexdigest()


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
    assert options.gguf_repo_only is False
    lock = json.loads((tmp_path / "plan.lock.json").read_text(encoding="utf-8"))
    assert lock["artifact_revision"] == _REV
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


class _CatalogLoader:
    def load(self, *, requested_model: str, site: str) -> dict[str, object]:
        assert requested_model == "qwen3-6-27b"
        assert site == "https://local-bench.ai"
        return {
            "models": [
                {
                    "slug": "qwen3-6-27b",
                    "catalog_id": "Qwen/Qwen3.6-27B",
                    "display_name": "Qwen3.6 27B",
                    "family": "Qwen3.6",
                    "tokenizer_repo": "owner/base-model",
                    "artifacts": [
                        {
                            "quant_label": "Q4_K_M",
                            "repo_id": "owner/model-gguf",
                            "filename": "model-q4.gguf",
                            "revision": _REV,
                            "sha256": _MODEL_SHA,
                            "size_bytes": len(_MODEL_BYTES),
                            "vram_required_gb_32k": 22.0,
                        },
                    ],
                },
            ],
        }


class _PreflightHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append((url, payload))
        return {"publishable": True, "reasons": []}


class _HfClient:
    def download_file(self, *, repo_id: str, filename: str, revision: str, destination: Path) -> None:
        assert repo_id in {"owner/model-gguf", "owner/raw-gguf"}
        assert filename == "model-q4.gguf"
        assert revision == _REV
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_MODEL_BYTES)

    def snapshot_download(self, *, repo_id: str, revision: str, destination: Path) -> Path:
        assert repo_id in {"owner/base-model", "owner/raw-gguf"}
        assert revision == _REV
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "tokenizer.json").write_text("{}", encoding="utf-8")
        (destination / "tokenizer_config.json").write_text(
            json.dumps({"chat_template": "{{ messages }}"}),
            encoding="utf-8",
        )
        return destination


class _BenchRunner:
    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self.options = None
        self.raise_keyboard_interrupt = False

    def __call__(self, options) -> dict[str, object]:
        if self.raise_keyboard_interrupt:
            raise KeyboardInterrupt
        self.options = options
        run_path = self._run_dir / "localbench-run.json"
        run_path.write_text(json.dumps({"scores": {"headline_score": 0.73}}), encoding="utf-8")
        return {"scores": {"headline_score": 0.73}, "warnings": []}


class _Submitter:
    def __init__(self) -> None:
        self.calls: list[SubmitRunOptions] = []

    def __call__(self, options: SubmitRunOptions) -> SubmitRunResult:
        self.calls.append(options)
        return SubmitRunResult(exit_code=0, lines=("submission sub_fake",))


class _RawArtifactResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def resolve_raw_artifact(self, *, repo_id: str, quant: str | None):
        self.calls.append((repo_id, quant))
        from localbench.one_shot.types import OneShotArtifact

        return OneShotArtifact(
            repo_id=repo_id,
            filename="model-q4.gguf",
            revision=_REV,
            quant_label=quant or "Q4_K_M",
            sha256=_MODEL_SHA,
            size_bytes=len(_MODEL_BYTES),
            vram_required_gb_8k=None,
            vram_required_gb_32k=None,
        )


def _deps(tmp_path: Path) -> OneShotRunnerDeps:
    return OneShotRunnerDeps(
        catalog_loader=_CatalogLoader(),
        preflight_http=_PreflightHttp(),
        hf_client=_HfClient(),
        bench_runner=_BenchRunner(tmp_path),
        submitter=_Submitter(),
        raw_artifact_resolver=_RawArtifactResolver(),
    )


def _args(
    tmp_path: Path,
    *,
    one_shot_submit: bool | None = False,
    offline: bool = False,
    resume: Path | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        one_shot_model="qwen3-6-27b",
        yes=True,
        one_shot_submit=one_shot_submit,
        accept_suite_terms=True,
        quant="Q4_K_M",
        vram_gb=24.0,
        offline=offline,
        allow_sleep_risk=False,
        purge_model=False,
        llama_server_path=Path("llama-server.exe"),
        server_bin=None,
        out=None if resume is not None else tmp_path,
        resume=resume,
        cache_dir=None,
        suite_dir=None,
        suite_source=None,
        max_items=None,
        threads=8,
        threads_batch=8,
        wsl_venv_python="~/appworld-harness/venv/bin/python3",
        appworld_root="/home/michael/appworld-data",
        site="https://local-bench.ai",
        signing_key=None,
        display_name=None,
        bypass_token=None,
        bypass_token_file=None,
    )
