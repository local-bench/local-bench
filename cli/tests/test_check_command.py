from __future__ import annotations

import struct
from pathlib import Path

import localbench.cli as cli_module
import localbench.check.run as check_run
import pytest

from localbench._types import JsonObject
from localbench.check.live_runner import LiveExecutionResult, LiveItem
from localbench.checkset.input_runs import read_json
from localbench.cli import main


def _fixture_gguf(path: Path) -> Path:
    key = b"general.architecture"
    value = b"qwen3"
    _ = path.write_bytes(
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", 8)
        + struct.pack("<Q", len(value))
        + value
    )
    return path


def test_check_dry_run_executes_every_manifest_item_and_writes_plan_lock(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    artifact = _fixture_gguf(tmp_path / "fixture-Q5_K_M.gguf")
    run_dir = tmp_path / "run"

    exit_code = main(
        (
            "check",
            str(artifact),
            "--parent",
            "dry-run-reference-v1",
            "--dry-run",
            "--manifest",
            str(repo_root / "checkset" / "check-set-v1.manifest.json"),
            "--out",
            str(run_dir),
        )
    )

    record = read_json(run_dir / "check-record.json")
    lifecycle = record["lifecycle"]
    items = record["items"]
    comparison = record["comparison"]
    execution = record["execution"]
    assert isinstance(lifecycle, dict)
    assert isinstance(items, list)
    assert isinstance(comparison, dict)
    assert isinstance(execution, dict)
    assert exit_code == 0
    assert record["schema_version"] == "localbench-check-run-v1"
    assert lifecycle["status"] == "dry-run-executed"
    assert len(items) == 594
    assert comparison["pairing_status"] == "paired"
    assert execution["runner"] == "mock"
    assert (run_dir / "plan.lock.json").is_file()


def test_check_requires_explicit_resume_and_preserves_prior_items(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    artifact = _fixture_gguf(tmp_path / "fixture-Q5_K_M.gguf")
    run_dir = tmp_path / "run"
    args = (
        "check",
        str(artifact),
        "--dry-run",
        "--manifest",
        str(repo_root / "checkset" / "check-set-v1.manifest.json"),
        "--out",
        str(run_dir),
    )
    assert main(args) == 0
    original = (run_dir / "items.jsonl").read_bytes()

    assert main(args) == 2
    assert main((*args[:-2], "--resume", str(run_dir))) == 0
    assert (run_dir / "items.jsonl").read_bytes() == original


def test_check_returns_unpaired_when_reference_comparison_edition_mismatches(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    artifact = _fixture_gguf(tmp_path / "fixture.gguf")
    run_dir = tmp_path / "run"

    exit_code = main(
        (
            "check",
            str(artifact),
            "--dry-run",
            "--reference-checkset-edition",
            "check-set-v0",
            "--manifest",
            str(repo_root / "checkset" / "check-set-v1.manifest.json"),
            "--out",
            str(run_dir),
        )
    )

    record = read_json(run_dir / "check-record.json")
    comparison = record["comparison"]
    assert isinstance(comparison, dict)
    assert exit_code == 0
    assert comparison["pairing_status"] == "unpaired"
    assert comparison["verdict"] == "unpaired"


def test_check_cli_threads_smoke_mode_to_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_check_command(_artifact: Path, **kwargs: object) -> tuple[int, str]:
        captured.update(kwargs)
        return 0, "smoke accepted"

    monkeypatch.setattr(cli_module, "check_command", fake_check_command)

    assert main(("check", "candidate.gguf", "--smoke")) == 0
    assert captured["smoke"] is True


def test_check_cli_threads_reference_run_and_coding_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_check_command(_artifact: Path, **kwargs: object) -> tuple[int, str]:
        captured.update(kwargs)
        return 0, "live accepted"

    monkeypatch.setattr(cli_module, "check_command", fake_check_command)

    assert main(
        (
            "check",
            "candidate.gguf",
            "--reference-run",
            "reference-run",
            "--allow-untrusted-code",
        )
    ) == 0
    assert captured["reference_run"] == Path("reference-run")
    assert captured["allow_untrusted_code"] is True


def test_check_smoke_writes_candidate_only_non_scoring_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    artifact = _fixture_gguf(tmp_path / "fixture-Q5_K_M.gguf")
    run_dir = tmp_path / "smoke"
    rows: list[JsonObject] = [
        {
            "candidate": {
                "finish_reason": "stop",
                "parsed_tool_calls": [],
                "protocol_flag": None,
                "server_start_id": "start-a",
                "text": "ALPHA<END>",
                "token_ids": [1, 2],
                "usage": {"completion_tokens": 2, "prompt_tokens": 4, "total_tokens": 6},
            },
            "generation_parameters": {
                "answer_budget_tokens": 512,
                "headroom_tokens": 256,
                "max_tokens": 4864,
                "seed": 1234,
                "temperature": 0,
                "think_budget_tokens": 4096,
            },
            "item_id": "gate-stop-token-01",
            "module": "sanity-gates",
            "source_item": {
                "category": "stop-token",
                "expected": {"required": "ALPHA", "stop_marker": "<END>"},
                "gate_kind": "validity",
            },
        }
    ]
    def fake_load_smoke_items(*_args: object) -> tuple[LiveItem, ...]:
        return ()

    def fake_run_live_items(*_args: object, **_kwargs: object) -> LiveExecutionResult:
        return LiveExecutionResult(
            rows,
            {"edition": "LCE-1", "runner": "llama-server-live"},
        )

    monkeypatch.setattr(check_run, "load_smoke_items", fake_load_smoke_items)
    monkeypatch.setattr(check_run, "run_live_items", fake_run_live_items)

    exit_code = main(
        (
            "check",
            str(artifact),
            "--smoke",
            "--manifest",
            str(repo_root / "checkset" / "check-set-v1.manifest.json"),
            "--out",
            str(run_dir),
        )
    )

    record = read_json(run_dir / "check-record.json")
    lifecycle = record["lifecycle"]
    comparison = record["comparison"]
    grading = record["grading"]
    assert exit_code == 0
    assert isinstance(lifecycle, dict) and lifecycle["status"] == "smoke-executed"
    assert isinstance(comparison, dict) and comparison["pairing_status"] == "non-scoring"
    assert isinstance(grading, dict) and grading == {
        "n_items": 1,
        "schema_version": "localbench-check-smoke-grading-v1",
        "status": "non-scoring",
    }
    assert record["scoring"] == {"label": "non-scoring", "reason": "pinned-smoke-validation"}
    assert (run_dir / "receipt.json").is_file()
