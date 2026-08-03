from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import pytest

from localbench.check.receipt import validate_run_dir
from localbench.check_cli import default_manifest_path, main

_BYTE_STABLE_OUTPUTS = (
    "check-record.json",
    "grades.jsonl",
    "grading-summary.json",
    "items.jsonl",
    "kld.json",
    "performance.json",
    "plan.lock.json",
    "receipt.json",
    "statistics.json",
    "verdict.json",
)
_FROZEN_MANIFEST_SHA256 = "f035c2d36663bf2b1e127fe1d0e12d4c59efa0e6080e3995abe8a814f8e64f7b"


def test_fresh_temp_dry_run_is_complete_valid_and_byte_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fixture = Path(__file__).resolve().parent / "fixtures" / "check" / "tiny-Q5_K_M.gguf"
    first = tmp_path / "first"
    second = tmp_path / "second"
    monkeypatch.chdir(tmp_path)

    common = ("check", str(fixture), "--parent", "dry-run-reference-v1", "--dry-run")
    assert main((*common, "--out", str(first))) == 0
    assert main((*common, "--out", str(second))) == 0

    validate_run_dir(first)
    validate_run_dir(second)
    for name in _BYTE_STABLE_OUTPUTS:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    golden = repo_root / "cli" / "tests" / "fixtures" / "check" / "golden-check-record.json"
    assert (first / "check-record.json").read_bytes() == golden.read_bytes()


def test_packaged_manifest_matches_the_frozen_source_bytes() -> None:
    packaged = default_manifest_path()
    source = Path(__file__).resolve().parents[2] / "checkset" / "check-set-v1.manifest.json"

    assert packaged.is_file()
    assert packaged.read_bytes() == source.read_bytes()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == _FROZEN_MANIFEST_SHA256


def test_v2_default_install_has_the_live_check_runtime_dependencies() -> None:
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "1.0.0.dev0"
    assert pyproject["project"]["dependencies"] == ["httpx>=0.27", "math-verify>=0.9.0"]
    assert pyproject["project"]["scripts"]["localbench"] == "localbench.check_cli:main"
