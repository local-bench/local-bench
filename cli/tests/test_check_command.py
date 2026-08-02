from __future__ import annotations

import struct
from pathlib import Path

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
