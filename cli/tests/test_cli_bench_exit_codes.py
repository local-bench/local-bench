from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import localbench.cli as cli_mod
from localbench.campaign_checkpoints import CheckpointCorruptionError
from localbench.exit_codes import (
    EXIT_AGENTIC_SETUP_REQUIRED,
    EXIT_CHECKPOINT_CORRUPTION,
    EXIT_UNSAFE_RESUME,
)
from localbench.orchestrate import UnsafeResumeError
from localbench.serving.agentic_support import AgenticSetupError


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
    assert "--static-only" in error
    assert "No model download or benchmark work has started" in error


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
        suite_dir=None,
        out=Path("runs/bench/gemma"),
        resume=None,
        retry_errored=retry_errored,
        cache_dir=None,
        threads=8,
        threads_batch=8,
        hf_model_id=hf_model_id,
        reasoning_activation=reasoning_activation,
        gguf_repo_only=gguf_repo_only,
    )


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
