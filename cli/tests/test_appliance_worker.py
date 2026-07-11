from __future__ import annotations

import base64
import hashlib
import importlib.metadata
from pathlib import Path, PurePosixPath

import pytest

from localbench.appliance.worker import _localbench_record_tree_sha256
from localbench.scoring.agentic_exec import wsl_worker


class FakeDistribution:
    def __init__(self, root: Path, files: list[PurePosixPath]) -> None:
        self.root = root
        self.files = files

    def locate_file(self, relative: object) -> Path:
        return self.root / str(relative)


def test_worker_distribution_mutation_is_detected_from_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = tmp_path / "localbench/appliance/worker.py"
    record = tmp_path / "local_bench_ai-0.3.1.dist-info/RECORD"
    worker.parent.mkdir(parents=True)
    record.parent.mkdir(parents=True)
    original = b"print('trusted worker')\n"
    worker.write_bytes(original)
    encoded = base64.urlsafe_b64encode(hashlib.sha256(original).digest()).decode().rstrip("=")
    record.write_text(
        f"localbench/appliance/worker.py,sha256={encoded},{len(original)}\n"
        "local_bench_ai-0.3.1.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    files = [
        PurePosixPath("localbench/appliance/worker.py"),
        PurePosixPath("local_bench_ai-0.3.1.dist-info/RECORD"),
    ]
    monkeypatch.setattr(
        importlib.metadata, "distribution", lambda name: FakeDistribution(tmp_path, files)
    )
    baseline = _localbench_record_tree_sha256()
    assert len(baseline) == 64
    worker.write_bytes(b"print('mutated worker')\n")
    with pytest.raises(RuntimeError, match="RECORD hash mismatch"):
        _localbench_record_tree_sha256()


def test_official_appworld_record_identity_is_path_independent_and_detects_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "appworld/module.py"
    record = tmp_path / "appworld-0.1.dist-info/RECORD"
    source.parent.mkdir(parents=True)
    record.parent.mkdir(parents=True)
    original = b"OFFICIAL = True\n"
    source.write_bytes(original)
    encoded = base64.urlsafe_b64encode(hashlib.sha256(original).digest()).decode().rstrip("=")
    canonical = (
        f"appworld-0.1.dist-info/RECORD,,\n"
        f"appworld/module.py,sha256={encoded},{len(original)}\n"
    ).encode()
    record.write_text(
        f"appworld/module.py,sha256={encoded},{len(original)}\n"
        "../../../bin/appworld,sha256=path-dependent,1\n"
        "appworld-0.1.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    distribution = FakeDistribution(
        tmp_path,
        [
            PurePosixPath("appworld/module.py"),
            PurePosixPath("../../../bin/appworld"),
            PurePosixPath("appworld-0.1.dist-info/RECORD"),
        ],
    )
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: distribution)
    monkeypatch.setattr(
        wsl_worker,
        "_APPWORLD_WHEEL_RECORD_SHA256",
        hashlib.sha256(canonical).hexdigest(),
    )
    monkeypatch.setattr(wsl_worker, "_APPWORLD_OFFICIAL_TREE_SHA256", "cd" * 32)
    assert wsl_worker._verified_appworld_tree_sha256() == "cd" * 32
    source.write_bytes(b"OFFICIAL = False\n")
    with pytest.raises(RuntimeError, match="distribution (size|hash) mismatch"):
        wsl_worker._verified_appworld_tree_sha256()
