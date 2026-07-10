from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from localbench.scoring.agentic_exec import task_pool

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_subset_from_task_ids_returns_stable_synthetic_subset() -> None:
    # Given injected task ids for a GPU-free campaign path.
    task_ids = ["fac291d_1", "50e1ac9_1"]

    # When building the synthetic subset twice.
    canonical = [*task_ids, "other_1"]
    first = task_pool.subset_from_task_ids(task_ids, canonical_task_ids=canonical)
    second = task_pool.subset_from_task_ids(list(task_ids), canonical_task_ids=canonical)

    # Then the ids, size, and manifest hash are stable without AppWorld.
    assert first.name == "injected"
    assert first.split == "injected"
    assert first.size == 2
    assert first.seed == 0
    assert first.task_ids == tuple(task_ids)
    assert first.manifest_hash == second.manifest_hash


def test_subset_from_task_ids_rejects_duplicates_and_noncanonical_ids() -> None:
    canonical = ["fac291d_1", "50e1ac9_1"]

    with pytest.raises(ValueError, match="must be unique"):
        task_pool.subset_from_task_ids(
            ["fac291d_1", "fac291d_1"],
            canonical_task_ids=canonical,
        )
    with pytest.raises(ValueError, match="outside the canonical scored set"):
        task_pool.subset_from_task_ids(["unknown_1"], canonical_task_ids=canonical)


def test_load_metadata_reads_fake_appworld_root_without_importing_appworld(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given a fake APPWORLD_ROOT with one valid metadata file, one garbage file, and one missing file.
    root = tmp_path / "appworld"
    valid_dir = root / "data" / "tasks" / "fac291d_1" / "ground_truth"
    valid_dir.mkdir(parents=True)
    (valid_dir / "metadata.json").write_text(
        json.dumps(
            {
                "difficulty": 3,
                "apps": ["spotify", "calendar"],
                "num_api_calls": 4.0,
            },
        ),
        encoding="utf-8",
    )
    garbage_dir = root / "data" / "tasks" / "bad_1" / "ground_truth"
    garbage_dir.mkdir(parents=True)
    (garbage_dir / "metadata.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("APPWORLD_ROOT", str(root))
    sys.modules.pop("appworld", None)

    # When loading metadata for all three ids.
    metadata = task_pool.load_metadata(["fac291d_1", "bad_1", "missing_1"])

    # Then valid fields are parsed and bad/missing rows fall back to bare TaskMeta.
    assert metadata["fac291d_1"].difficulty == 3
    assert metadata["fac291d_1"].primary_app == "calendar"
    assert metadata["fac291d_1"].num_api_calls == 4
    assert metadata["bad_1"].difficulty is None
    assert metadata["bad_1"].primary_app is None
    assert metadata["missing_1"].difficulty is None
    assert metadata["missing_1"].primary_app is None
    assert "appworld" not in sys.modules


def test_agentic_imports_are_appworld_optional() -> None:
    # Given no AppWorld module has been imported in this process.
    sys.modules.pop("appworld", None)

    # When importing the task-pool and orchestrator modules.
    task_pool_module = importlib.import_module("localbench.scoring.agentic_exec.task_pool")
    orchestrate_module = importlib.import_module("localbench.orchestrate")

    # Then imports succeed without loading the real AppWorld backend.
    assert task_pool_module.__name__.endswith("task_pool")
    assert orchestrate_module.OrchestrateConfig.__name__ == "OrchestrateConfig"
    assert "appworld" not in sys.modules


def test_appworld_c_funnel_help_is_appworld_optional() -> None:
    # Given the funnel CLI is invoked only for help text.
    command = [sys.executable, str(_REPO_ROOT / "cli" / "tools" / "appworld_c_funnel.py"), "--help"]

    # When running it off the real AppWorld host.
    result = subprocess.run(command, cwd=_REPO_ROOT, capture_output=True, text=True, check=False)

    # Then argparse help is available without importing AppWorld.
    assert result.returncode == 0
    assert "AppWorld-C staged funnel runner" in result.stdout
