from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import pytest

from localbench.checkset.input_runs import (
    _verify_run_files,
    verify_suite_itemset_hashes,
)
from localbench.checkset.sources import build_local_modules


def test_suite_itemset_hashes_must_match_each_run_manifest(tmp_path: Path) -> None:
    # Given a suite directory and a run manifest whose IFBench item-set hash is stale.
    benches = ("bigcodebench_hard", "ifbench", "olymmath_hard", "amo", "tc_json_v1")
    for bench in benches:
        (tmp_path / f"{bench}.jsonl").write_text(f'{{"id":"{bench}"}}\n', encoding="utf-8")
    hashes = {
        f"{bench}.jsonl": hashlib.sha256((tmp_path / f"{bench}.jsonl").read_bytes()).hexdigest()
        for bench in benches
    }
    hashes["ifbench.jsonl"] = "0" * 64
    run = {"manifest": {"suite": {"item_set_hashes": hashes}}}

    # When the current suite is bound to that run, then the mismatch is a hard build error.
    with pytest.raises(ValueError, match="item-set hash mismatch"):
        verify_suite_itemset_hashes(tmp_path, "test-run", run)


def test_pinned_input_hash_paths_cannot_escape_run_directory(tmp_path: Path) -> None:
    # Given a manifest-controlled path that traverses above the pinned run directory.
    run_root = tmp_path / "run"
    run_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    entry = {"sha256": {"../outside.json": hashlib.sha256(outside.read_bytes()).hexdigest()}}

    # When pinned input hashes are checked, then containment is enforced before file access.
    with pytest.raises(ValueError, match="must stay within the pinned run directory"):
        _verify_run_files(run_root, entry)


def test_real_pinned_inputs_produce_locked_t2_local_selections() -> None:
    # Given the T1-pinned suite and four verified run bundles.
    repo_root = Path(__file__).resolve().parents[2]

    # When the local-only T2 selectors run.
    modules, exclusions = build_local_modules(repo_root)

    # Then all pre-upstream module counts and frozen informative splits match the lock.
    by_name = {module.name: module for module in modules}
    assert len(by_name["coding"].items) == 96
    assert len(by_name["instruction"].items) == 120
    assert len(by_name["math-legacy"].items) == 30
    assert len(by_name["tools-single"].items) == 54
    assert all(item.item_id.startswith("bcbh-") for item in by_name["coding"].items)
    assert all(item.item_id.startswith("ifbench-") for item in by_name["instruction"].items)
    assert Counter(item.selection_stratum for item in by_name["coding"].items) == {
        "complement": 58,
        "informative": 38,
    }
    assert Counter(item.selection_stratum for item in by_name["instruction"].items) == {
        "count": 23,
        "custom": 4,
        "format": 35,
        "ratio": 16,
        "repeat": 2,
        "sentence": 10,
        "words": 30,
    }
    assert Counter(item.selection_stratum for item in by_name["math-legacy"].items) == {
        "legacy-informative": 30,
    }
    assert Counter(item.selection_stratum for item in by_name["tools-single"].items) == {
        "bfcl-complement": 1,
        "bfcl-informative": 23,
        "fresh-common-tools": 30,
    }
    assert exclusions == (
        {"item_id": "bcbh-006", "module": "coding", "reason": "sandbox-unscoreable"},
        {"item_id": "bcbh-007", "module": "coding", "reason": "sandbox-unscoreable"},
        {"item_id": "bcbh-014", "module": "coding", "reason": "sandbox-unscoreable"},
        {"item_id": "bcbh-035", "module": "coding", "reason": "sandbox-unscoreable"},
        {"item_id": "bcbh-074", "module": "coding", "reason": "sandbox-unscoreable"},
        {"item_id": "bcbh-096", "module": "coding", "reason": "sandbox-unscoreable"},
        {"item_id": "bcbh-104", "module": "coding", "reason": "sandbox-unscoreable"},
    )
