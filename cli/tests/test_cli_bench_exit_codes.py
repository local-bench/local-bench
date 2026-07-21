from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import localbench.cli as cli_mod
from localbench._types import JsonObject
from localbench.campaign_checkpoints import CheckpointCorruptionError
from localbench.exit_codes import (
    EXIT_AGENTIC_SETUP_REQUIRED,
    EXIT_CHECKPOINT_CORRUPTION,
    EXIT_UNSAFE_RESUME,
)
from localbench.orchestrate import UnsafeResumeError
from localbench.prompt_rendering import TokenizerCacheMissError
from localbench.serving.agentic_support import AgenticSetupError
from localbench.scoring.agentic_exec.wsl_proxy import WslTransportError


_TOKENIZER_REVISION = "d" * 40


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


def test_bench_returns_dedicated_exit_for_missing_agentic_setup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_anyio_run(function, options) -> None:
        raise AgenticSetupError(detail="managed harness paths are unset")

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)

    code = cli_mod._bench(_bench_args())

    assert code == EXIT_AGENTIC_SETUP_REQUIRED
    error = capsys.readouterr().err
    assert "AppWorld harness" in error
    assert "localbench setup-agentic" in error
    assert "No model download or benchmark work has started" in error


def test_bench_finishes_when_only_post_score_wsl_teardown_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: every scored item and the final run document are durable before WSL cleanup fails.
    run_dir = tmp_path / "completed-run"
    run_dir.mkdir()
    run_path = run_dir / "localbench-run.json"
    run_path.write_text(
        json.dumps({"benches": {}, "totals": {}, "warnings": []}) + "\n",
        encoding="utf-8",
    )
    status_path = run_dir / "run.status.json"
    status_path.write_text(
        json.dumps(
            {
                "state": "running",
                "completed_items": 1311,
                "total_items": 1311,
                "exit_code": None,
                "failure_reason": None,
            },
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_after_scoring(function, options):
        raise WslTransportError(
            operation="teardown",
            detail="managed worker discover failed with exit 3221225794",
        )

    monkeypatch.setattr(cli_mod.anyio, "run", fail_after_scoring)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: None)

    # When: bench handles the teardown-only transport failure.
    code = cli_mod._bench(_bench_args(out=run_dir))

    # Then: cleanup is recorded as a warning and cannot turn the completed run nonzero.
    warning = (
        "wsl transport teardown failed after scoring completed; cleanup remains best-effort: "
        "managed worker discover failed with exit 3221225794"
    )
    assert code == 0
    assert f"warning    {warning}" in capsys.readouterr().err
    assert json.loads(run_path.read_text(encoding="utf-8"))["warnings"] == [warning]
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["state"] == "complete"
    assert status["exit_code"] == 0
    assert status["failure_reason"] is None


def test_bench_capped_thinking_requires_reasoning_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: capped-thinking is requested without the family activation flags.
    launched = False

    def fake_anyio_run(function, options) -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)

    # When: the bench command is validated.
    code = cli_mod._bench(_bench_args(lane="capped-thinking"))

    # Then: it fails as a usage error before launch and names both missing flags.
    stderr = capsys.readouterr().err
    assert code == 2
    assert launched is False
    assert "--reasoning-activation" in stderr
    assert "--hf-model-id" in stderr


def test_bench_publishable_bounded_final_requires_identity_choice(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: bench-managed bounded-final is publishable but lacks HF or basic GGUF identity.
    launched = False

    def fake_anyio_run(function, options) -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)

    # When: the bench command is validated.
    code = cli_mod._bench(_bench_args(lane="bounded-final-v2"))

    # Then: it fails as a usage error before launch and names both identity choices.
    stderr = capsys.readouterr().err
    assert code == 2
    assert launched is False
    assert "--hf-model-id <repo>" in stderr
    assert "--gguf-repo-only" in stderr


def test_bench_gguf_repo_only_satisfies_bounded_final_identity_choice(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: bench-managed bounded-final explicitly chooses basic GGUF repo identity.
    captured_options = None

    def fake_anyio_run(function, options):
        nonlocal captured_options
        captured_options = options
        return {"benches": {}, "totals": {}, "warnings": []}

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: None)

    # When: the bench command is validated and launched.
    code = cli_mod._bench(_bench_args(lane="bounded-final-v2", gguf_repo_only=True))

    # Then: the launch receives the basic identity choice and prints the null-digest notice.
    output = capsys.readouterr().out
    assert code == 0
    assert captured_options is not None
    assert captured_options.gguf_repo_only is True
    assert (
        "notice     identity basic-gguf-repo-only-v1: tokenizer/chat-template "
        "digests will be null; add --hf-model-id <exact HF repo> for full provenance"
    ) in output


def test_bench_online_precaches_missing_tokenizer_and_threads_resolved_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: bounded-final introspection misses the local cache, while online acquisition is allowed.
    load_calls: list[tuple[str, str | None]] = []
    download_calls: list[tuple[str, tuple[str, ...], str | None]] = []
    captured_options = None

    def fake_load(repo_id: str, revision: str | None = None):
        load_calls.append((repo_id, revision))
        if len(load_calls) == 1:
            raise TokenizerCacheMissError("offline cache miss")
        return object()

    def fake_snapshot_download(
        repo_id: str,
        allow_patterns: list[str],
        *,
        revision: str | None = None,
    ) -> str:
        download_calls.append((repo_id, tuple(allow_patterns), revision))
        return str(tmp_path / "models--owner--model" / "snapshots" / _TOKENIZER_REVISION)

    def fake_anyio_run(function, options):
        nonlocal captured_options
        captured_options = options
        return {"benches": {}, "totals": {}, "warnings": []}

    monkeypatch.setattr(cli_mod, "load_hf_chat_template_tokenizer", fake_load)
    monkeypatch.setattr(cli_mod, "_hf_snapshot_download", fake_snapshot_download)
    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: None)

    # When: the advanced bench path prepares its tokenizer.
    code = cli_mod._bench(_bench_args(lane="bounded-final-v2", hf_model_id="owner/model"))

    # Then: acquisition is a pre-step, introspection retries offline, and provenance receives the revision.
    assert code == 0
    assert download_calls == [
        ("owner/model", ("*.json", "*.model", "*.jinja"), None),
    ]
    assert load_calls == [("owner/model", None), ("owner/model", _TOKENIZER_REVISION)]
    assert captured_options is not None
    assert captured_options.hf_revision == _TOKENIZER_REVISION


def test_bench_offline_keeps_tokenizer_cache_miss_as_hard_refusal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: the requested tokenizer is absent and --offline forbids acquisition.
    message = (
        "could not load tokenizer for 'owner/model' from the offline HF cache. "
        "Template introspection is offline-only; pre-cache the tokenizer once with:\n"
        '  hf download owner/model --include "*.json" --include "*.model" --include "*.jinja"\n'
        "(gated repos need `hf auth login` after accepting the license on huggingface.co)"
    )

    def fail_load(repo_id: str, revision: str | None = None):
        raise TokenizerCacheMissError(message)

    def forbid_download(*_args, **_kwargs):
        raise AssertionError("offline mode must not download")

    monkeypatch.setattr(cli_mod, "load_hf_chat_template_tokenizer", fail_load)
    monkeypatch.setattr(cli_mod, "_hf_snapshot_download", forbid_download)

    # When: the advanced bench path prepares its tokenizer.
    code = cli_mod._bench(
        _bench_args(lane="bounded-final-v2", hf_model_id="owner/model", offline=True),
    )

    # Then: it preserves the existing cache-miss remediation verbatim and never launches.
    assert code == 2
    assert message in capsys.readouterr().err


def test_bench_auto_chains_pending_coding_verifier_when_consent_is_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: bench finishes with generated coding artifacts and untrusted-code consent.
    run_dir = tmp_path / "run"
    suite_dir = _write_minimal_suite(tmp_path / "suite")
    pending = _generated_unverified_record()
    verified = {
        **pending,
        "axis_status": {
            "axes": {"coding": {"status": "measured"}},
        },
        "headline_complete": True,
    }
    captured: dict[str, object] = {}
    summaries: list[JsonObject] = []

    monkeypatch.setattr(cli_mod.anyio, "run", lambda function, options: pending)

    def fake_verify(run_path: Path, config: cli_mod.CodingExecConfig) -> JsonObject:
        captured["run_path"] = run_path
        captured["config"] = config
        return verified

    monkeypatch.setattr(cli_mod, "execute_pending_artifacts", fake_verify)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: summaries.append(record))

    # When: the advanced bench path completes.
    code = cli_mod._bench(
        _bench_args(
            allow_untrusted_code=True,
            out=run_dir,
            suite_dir=suite_dir,
        ),
    )

    # Then: the in-process verifier updates the same run before the submit-ready summary.
    assert code == 0
    assert captured["run_path"] == run_dir / "localbench-run.json"
    config = captured["config"]
    assert isinstance(config, cli_mod.CodingExecConfig)
    assert config.suite_dir == suite_dir
    assert config.out == run_dir / "localbench-run.json"
    assert config.allow_untrusted_code is True
    assert summaries == [verified]


def test_bench_verifier_failure_keeps_current_exit_and_prints_manual_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: bench generated coding artifacts but the automatic verifier cannot start.
    run_dir = tmp_path / "run"
    suite_dir = _write_minimal_suite(tmp_path / "suite")
    pending = _generated_unverified_record()
    summaries: list[JsonObject] = []
    monkeypatch.setattr(cli_mod.anyio, "run", lambda function, options: pending)

    def fail_verify(run_path: Path, config: cli_mod.CodingExecConfig) -> JsonObject:
        raise cli_mod.CodingExecError("sandbox preflight failed")

    monkeypatch.setattr(cli_mod, "execute_pending_artifacts", fail_verify)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: summaries.append(record))

    # When: the automatic verifier fails.
    code = cli_mod._bench(
        _bench_args(
            allow_untrusted_code=True,
            out=run_dir,
            suite_dir=suite_dir,
        ),
    )

    # Then: bench keeps its completed-run exit semantics and prints a ready-to-paste fallback.
    output = capsys.readouterr()
    assert code == 0
    assert "warning    automatic coding verifier failed: sandbox preflight failed" in output.err
    assert (
        "verify     localbench code "
        f"--pending-run {run_dir / 'localbench-run.json'} "
        f"--suite-dir {suite_dir} --allow-untrusted-code"
    ) in output.err
    assert summaries == [pending]


@pytest.mark.parametrize(
    ("hf_model_id", "reasoning_activation", "expected_flag"),
    (
        ("unsloth/gemma-4-12b-it", None, "--hf-model-id"),
        (None, "gemma4", "--reasoning-activation"),
    ),
)
def test_bench_answer_only_rejects_reasoning_flags(
    hf_model_id: str | None,
    reasoning_activation: str | None,
    expected_flag: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: answer-only is requested with a capped-thinking-only flag.
    launched = False

    def fake_anyio_run(function, options) -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)

    # When: the bench command is validated.
    code = cli_mod._bench(
        _bench_args(
            hf_model_id=hf_model_id,
            reasoning_activation=reasoning_activation,
        ),
    )

    # Then: it fails as a usage error before launch and names the rejected flag.
    stderr = capsys.readouterr().err
    assert code == 2
    assert launched is False
    assert expected_flag in stderr
    assert "capped-thinking" in stderr


def test_bench_retry_errored_requires_resume(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: retry-errored is requested without a resume directory.
    launched = False

    def fake_anyio_run(function, options) -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)

    # When: the bench command is validated.
    code = cli_mod._bench(_bench_args(retry_errored=True))

    # Then: it fails as a usage error before launch.
    stderr = capsys.readouterr().err
    assert code == 2
    assert launched is False
    assert "--retry-errored requires --resume" in stderr


def test_run_normalizes_extensionless_out_path_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = _write_minimal_suite(tmp_path / "suite")
    out_root = tmp_path / "run-output"
    captured_options = None

    def fake_anyio_run(function, options):
        nonlocal captured_options
        captured_options = options
        return {"benches": {}, "totals": {}, "warnings": []}

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: None)

    code = cli_mod.main(
        [
            "run",
            "--suite-dir",
            str(suite),
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "smoke-model",
            "--skip-preflight",
            "--no-supervisor",
            "--out",
            str(out_root),
        ],
    )

    assert code == 0
    assert captured_options is not None
    assert captured_options.out == out_root / "localbench-run.json"


def test_run_with_endpoint_identity_files_passes_digest_inputs_to_orchestrator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = _write_minimal_suite(tmp_path / "suite")
    tokenizer = tmp_path / "tokenizer.json"
    chat_template = tmp_path / "chat_template.jinja"
    tokenizer.write_text('{"model":"fixture"}\n', encoding="utf-8")
    chat_template.write_text("{{ messages }}\n", encoding="utf-8")
    captured_options = None

    def fake_anyio_run(function, options):
        nonlocal captured_options
        captured_options = options
        return {"benches": {}, "totals": {}, "warnings": []}

    monkeypatch.setattr(cli_mod.anyio, "run", fake_anyio_run)
    monkeypatch.setattr(cli_mod, "_print_summary", lambda record, out=None: None)

    code = cli_mod.main(
        [
            "run",
            "--suite-dir",
            str(suite),
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "smoke-model",
            "--skip-preflight",
            "--no-supervisor",
            "--tokenizer-file",
            str(tokenizer),
            "--chat-template-file",
            str(chat_template),
        ],
    )

    assert code == 0
    assert captured_options is not None
    assert captured_options.tokenizer_file == tokenizer
    assert captured_options.chat_template_file == chat_template
    assert captured_options.tokenizer_digest is None
    assert captured_options.chat_template_digest is None


def _bench_args(
    *,
    lane: str = "answer-only",
    hf_model_id: str | None = None,
    reasoning_activation: str | None = None,
    gguf_repo_only: bool = False,
    retry_errored: bool = False,
    offline: bool = False,
    allow_untrusted_code: bool = False,
    out: Path = Path("runs/bench/gemma"),
    suite_dir: Path | None = None,
) -> argparse.Namespace:
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
        lane=lane,
        seed=1234,
        max_items=None,
        suite="core-text-v1",
        suite_source=None,
        suite_dir=suite_dir,
        out=out,
        resume=None,
        retry_errored=retry_errored,
        cache_dir=None,
        threads=8,
        threads_batch=8,
        hf_model_id=hf_model_id,
        reasoning_activation=reasoning_activation,
        gguf_repo_only=gguf_repo_only,
        offline=offline,
        allow_untrusted_code=allow_untrusted_code,
    )


def _generated_unverified_record() -> JsonObject:
    return {
        "benches": {},
        "totals": {},
        "warnings": [],
        "headline_complete": False,
        "axis_status": {
            "axes": {
                "coding": {
                    "axis": "coding",
                    "status": "generated_unverified",
                    "reason": "verdict_pending",
                },
            },
        },
    }


def _write_minimal_suite(path: Path) -> Path:
    path.mkdir(parents=True)
    item_path = path / "mmlu_pro.jsonl"
    item_path.write_text(
        '{"id":"1","question":"Pick A","options":["A","B"],"answer":"A"}\n',
        encoding="utf-8",
    )
    item_hash = __import__("hashlib").sha256(item_path.read_bytes()).hexdigest()
    (path / "suite.json").write_text(
        json.dumps(
            {
                "id": "core-text-v1",
                "version": "core-text-v1",
                "benches": {
                    "mmlu_pro": {
                        "chance_correction_baseline": 0.5,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {"standard": {"file": "mmlu_pro.jsonl", "item_count": 1, "sha256": item_hash}},
                        "template_text": "{question}\n{options}",
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (path / "itemsets.lock.json").write_text(
        json.dumps(
            {"files": {"mmlu_pro.jsonl": {"item_count": 1, "sha256": item_hash}}},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path
