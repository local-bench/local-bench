from __future__ import annotations

import struct
from pathlib import Path

from localbench.check.regrade import regrade_run
from localbench.check.run import CheckRequest, run_check


def test_offline_regrade_is_byte_stable_and_never_mutates_generation_rows(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tiny_gguf = _fixture_gguf(tmp_path / "fixture.gguf")
    run_dir, record = run_check(
        CheckRequest(
            artifact=tiny_gguf,
            manifest=repo_root / "checkset" / "check-set-v1.manifest.json",
            parent=None,
            dry_run=True,
            out=tmp_path / "run",
            resume=None,
        )
    )
    items_before = (run_dir / "items.jsonl").read_bytes()
    first = regrade_run(run_dir)
    grades_first = (run_dir / "grades.jsonl").read_bytes()
    second = regrade_run(run_dir)

    assert first == second
    assert (run_dir / "grades.jsonl").read_bytes() == grades_first
    assert (run_dir / "items.jsonl").read_bytes() == items_before
    assert first["n_items"] == 594
    assert record["grading"] == first
    statistics = record["statistics"]
    assert isinstance(statistics, dict)
    gates = statistics["gates"]
    assert isinstance(gates, dict)
    assert gates["validity_total"] == 12
    assert gates["behavioral_total"] == 6
    design = statistics["resampling_design"]
    assert isinstance(design, dict)
    instruction = design["instruction"]
    tools = design["tools"]
    assert isinstance(instruction, dict) and instruction["strata"] == {
        "count": 23,
        "custom": 4,
        "format": 35,
        "ratio": 16,
        "repeat": 2,
        "sentence": 10,
        "words": 30,
    }
    assert isinstance(tools, dict) and tools["cluster_count"] == 66
    assert (run_dir / "statistics.json").is_file()
    assert (run_dir / "verdict.json").is_file()
    performance = record["performance"]
    assert isinstance(performance, dict)
    controlled = performance["controlled"]
    task_phase = performance["task_phase"]
    assert isinstance(controlled, dict)
    assert isinstance(task_phase, dict)
    assert controlled["runner"] == "mock"
    task_rows = task_phase["items"]
    assert isinstance(task_rows, list) and len(task_rows) == 594
    assert task_phase["label"] == "naturalistic"
    assert (run_dir / "performance.json").is_file()


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
