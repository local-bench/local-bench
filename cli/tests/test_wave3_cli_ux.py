from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from localbench.cli import main


def test_root_version_and_help_include_public_quickstart(capsys: pytest.CaptureFixture[str]) -> None:
    # Given / When: users ask for root version and help.
    version_code = main(["--version"])
    version_output = capsys.readouterr().out
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    help_output = capsys.readouterr().out

    # Then: version prints and help shows the four-line public quickstart.
    assert version_code == 0
    assert version_output.strip()
    assert exit_info.value.code == 0
    assert "localbench fetch-suite --site https://local-bench.ai --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms" in help_output
    assert "localbench bench --runtime llama.cpp --model-file <gguf> --model-id <slug>" in help_output
    assert "localbench run --endpoint <OpenAI-compatible url> --model <name>" in help_output
    assert "localbench submit run --run <run-or-campaign> --suite-dir <suite-dir>" in help_output
    assert "https://local-bench.ai/submit" in help_output


def test_verify_submission_origin_threads_to_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: local verify-submission is called with community origin.
    import localbench.cli as cli_mod

    captured: dict[str, object] = {}

    def fake_verify(*args: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"schema_version": "localbench.submission_status_update.v1", "status": "accepted"}

    monkeypatch.setattr(cli_mod, "verify_submission", fake_verify)

    # When: the command runs.
    code = main(
        [
            "verify-submission",
            str(tmp_path / "bundle.json"),
            "--suite-dir",
            str(tmp_path),
            "--projection-out",
            str(tmp_path / "projection.json"),
            "--origin",
            "community",
        ],
    )

    # Then: the origin reaches the verification boundary.
    assert code == 0
    assert captured["origin"] == "community"


def test_doctor_prints_next_steps_for_missing_suite_key_and_attester(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: an empty cache, no submitter key, and no attester key env var.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("LOCALBENCH_ATTESTER_KEY_FILE", raising=False)

    # When: doctor runs against the default suite.
    code = main(["doctor", "--cache-dir", str(tmp_path / "cache")])

    # Then: it reports next steps instead of a traceback.
    output = capsys.readouterr().out
    assert code == 0
    assert "next      localbench fetch-suite --site https://local-bench.ai --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms" in output
    assert "next      submit run will create ~/.localbench/submitter_ed25519.pem if needed" in output
    assert "next      LOCALBENCH_ATTESTER_KEY_FILE unset; attestations are project-anchor-only" in output


def test_run_suite_resolution_error_lists_known_suites_and_fetch_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given / When: an unknown suite is requested without a cached suite.
    code = main(
        [
            "run",
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "model",
            "--suite",
            "unknown-suite",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--dry-run",
        ],
    )

    # Then: the error is actionable.
    output = capsys.readouterr().out
    assert code == 2
    assert "known suite ids:" in output
    assert "suite-v1-full-exec-6axis-v1" in output
    assert "fetch-suite --site https://local-bench.ai --suite unknown-suite --accept-suite-terms" in output
    assert "Traceback" not in output


def test_print_summary_reports_full_static_and_per_axis_placement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: representative run records with 5, 4, and 2 measured headline axes.
    import localbench.cli as cli_mod

    for measured_axes, expected in (
        (
                ("knowledge", "instruction_following", "math", "tool_use", "coding"),
                "placement  all 5 headline axes measured; this run is eligible for the full composite.",
            ),
            (
                ("knowledge", "instruction_following", "math", "coding"),
                "placement  4 static headline axes measured; this run is eligible for the static composite (static-suite-v3), not the full composite.",
            ),
            (
                ("knowledge", "instruction_following"),
                "placement  fewer than 4 static headline axes measured; this run is reported per-axis only.",
        ),
    ):
        # When: the run summary is printed.
        cli_mod._print_summary(_record(measured_axes))
        output = capsys.readouterr().out

        # Then: it states how the measured coverage affects placement.
        assert expected in output


def test_run_prints_publishability_warning_at_start(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a dry-run invocation missing publishable sampler pinning.
    suite = _write_suite(tmp_path / "suite")

    # When: run starts.
    code = main(
        [
            "run",
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "model",
            "--suite-dir",
            str(suite),
            "--dry-run",
        ],
    )

    # Then: the warning is prominent before the dry-run details.
    output = capsys.readouterr().out.splitlines()
    assert code == 0
    assert output[0] == (
        "warning    this run will not be submittable as publishable — "
        "add --publishable --sampler-seed <n>"
    )


def test_run_parser_rejects_hf_model_id_with_gguf_repo_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given / When: both bounded-final identity modes are requested.
    with pytest.raises(SystemExit) as exit_info:
        main(
            [
                "run",
                "--endpoint",
                "http://127.0.0.1:9/v1",
                "--model",
                "model",
                "--lane",
                "bounded-final-v2",
                "--hf-model-id",
                "unsloth/gemma-4-12b-it",
                "--gguf-repo-only",
            ],
        )

    # Then: argparse rejects the mutually exclusive flags before execution.
    stderr = capsys.readouterr().err
    assert exit_info.value.code == 2
    assert "--gguf-repo-only" in stderr
    assert "--hf-model-id" in stderr


def test_publishable_bounded_final_requires_explicit_identity_choice(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given / When: a publishable bounded-final run omits both identity choices.
    code = main(
        [
            "run",
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "model",
            "--lane",
            "bounded-final-v2",
            "--publishable",
            "--sampler-seed",
            "1234",
            "--dry-run",
        ],
    )

    # Then: it fails fast with both remediation options.
    stderr = capsys.readouterr().err
    assert code == 2
    assert "--hf-model-id <repo>" in stderr
    assert "--gguf-repo-only" in stderr
    assert "basic GGUF repo-only identity" in stderr


def test_non_publishable_bounded_final_warns_when_identity_is_omitted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a diagnostic bounded-final dry-run with no explicit identity mode.
    suite = _write_suite(tmp_path / "suite")

    # When: the run is accepted as non-publishable.
    code = main(
        [
            "run",
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "model",
            "--lane",
            "bounded-final-v2",
            "--suite-dir",
            str(suite),
            "--dry-run",
        ],
    )

    # Then: omission remains allowed but visible.
    output = capsys.readouterr().out
    assert code == 0
    assert output.count("warning    bounded-final model identity was not declared") == 1
    assert "--hf-model-id <repo>" in output
    assert "--gguf-repo-only" in output


def test_gguf_repo_only_notice_prints_before_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a basic-identity bounded-final diagnostic dry-run.
    suite = _write_suite(tmp_path / "suite")

    # When: the run starts.
    code = main(
        [
            "run",
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "model",
            "--lane",
            "bounded-final-v2",
            "--gguf-repo-only",
            "--suite-dir",
            str(suite),
            "--dry-run",
        ],
    )

    # Then: the basic identity notice explains the null-digest tradeoff.
    output = capsys.readouterr().out.splitlines()
    assert code == 0
    assert (
        "notice     identity basic-gguf-repo-only-v1: tokenizer/chat-template "
        "digests will be null; add --hf-model-id <exact HF repo> for full provenance"
    ) in output


def _record(measured_axes: tuple[str, ...]) -> dict[str, object]:
    axes = {
        key: {"axis": key, "status": "measured" if key in measured_axes else "not_measured", "reason": "ok"}
        for key in ("knowledge", "instruction_following", "math", "tool_use", "coding")
    }
    return {
        "benches": {},
        "scores": {"headline_score": None, "partial_composite": 0.5},
        "totals": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "wall_time_seconds": 0.0,
            "completion_tokens_per_second": 0.0,
        },
        "axis_status": {"axes": axes},
        "warnings": [],
    }


def _write_suite(path: Path) -> Path:
    path.mkdir()
    item_path = path / "mmlu_pro.jsonl"
    item_path.write_text(
        '{"id":"1","question":"Pick A","options":["A","B"],"answer":"A"}\n',
        encoding="utf-8",
    )
    digest = hashlib.sha256(item_path.read_bytes()).hexdigest()
    (path / "suite.json").write_text(
        json.dumps(
            {
                "id": "fixture-suite",
                "version": "fixture-suite",
                "benches": {
                    "mmlu_pro": {
                        "chance_correction_baseline": 0.5,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {"standard": {"file": "mmlu_pro.jsonl", "item_count": 1, "sha256": digest}},
                        "template_text": "{question}\n{options}",
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    (path / "itemsets.lock.json").write_text(
        json.dumps({"files": {"mmlu_pro.jsonl": {"item_count": 1, "sha256": digest}}}),
        encoding="utf-8",
    )
    return path
