"""Tests for assembling the public Core Text v1 suite bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from localbench.suite_bundle import PUBLIC_BENCHES, assemble_core_text_v1_bundle

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SUITE = ROOT / "suite" / "v1"


def test_assemble_core_text_v1_bundle_contains_only_headline_benches(tmp_path: Path) -> None:
    # Given: the private source-tree suite/v1 data.
    out_dir = tmp_path / "bundle"

    # When: assembling the distributable public bundle.
    result = assemble_core_text_v1_bundle(source_suite=SOURCE_SUITE, out_dir=out_dir)

    # Then: only headline benches and required release files are present.
    suite = _json(result.path / "suite.json")
    lock = _json(result.path / "itemsets.lock.json")
    assert tuple(sorted(suite["benches"])) == tuple(sorted(PUBLIC_BENCHES))
    assert tuple(sorted(lock["files"])) == ("ifbench.jsonl", "mmlu_pro.jsonl")
    assert "template_text" in suite["benches"]["mmlu_pro"]
    assert "template_text" in suite["benches"]["ifbench"]
    assert suite["benches"]["mmlu_pro"]["itemsets"]["standard"]["item_count"] == 400
    assert suite["benches"]["ifbench"]["itemsets"]["standard"]["item_count"] == 294
    assert lock["files"]["ifbench.jsonl"]["license"] == "ODC-BY-1.0"
    assert lock["files"]["mmlu_pro.jsonl"]["license"] == "MIT"
    assert (result.path / "SCORECARD.json").exists()
    assert (result.path / "NOTICE").exists()
    assert (result.path / "ATTRIBUTION.md").exists()
    assert (result.path / "LICENSES" / "MMLU-Pro-MIT").exists()
    assert (result.path / "LICENSES" / "IFBench-ODC-BY-1.0").exists()
    assert (result.path / "LICENSES" / "IFEval-Apache-2.0").exists()
    assert not (result.path / "amo.jsonl").exists()
    assert not (result.path / "bfcl.jsonl").exists()


def test_assemble_core_text_v1_bundle_writes_valid_sha256sums(tmp_path: Path) -> None:
    # Given: an assembled bundle.
    result = assemble_core_text_v1_bundle(source_suite=SOURCE_SUITE, out_dir=tmp_path / "bundle")

    # When: reading SHA256SUMS.
    lines = (result.path / "SHA256SUMS").read_text(encoding="utf-8").splitlines()

    # Then: every listed file exists and matches its digest.
    assert lines
    assert result.sha256sums_path == result.path / "SHA256SUMS"
    assert result.suite_hash == result.path.name
    for line in lines:
        digest, relative = line.split("  ", maxsplit=1)
        target = result.path / relative
        assert target.exists(), relative
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest


def _json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data
