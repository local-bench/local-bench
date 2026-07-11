from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import subprocess

import pytest

from localbench.appliance.worker import _localbench_record_tree_sha256
import localbench.appliance.worker as appliance_worker
from localbench.scoring.agentic_exec import wsl_worker


class FakeDistribution:
    def __init__(self, root: Path, files: list[PurePosixPath]) -> None:
        self.root = root
        self.files = files

    def locate_file(self, relative: object) -> Path:
        return self.root / str(relative)


def test_provision_force_reinstalls_downloaded_official_wheel_after_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel_bytes = b"official-wheel-bytes"
    wheel_sha = hashlib.sha256(wheel_bytes).hexdigest()
    calls: list[list[str]] = []

    def download(_url: str, path: Path, expected_sha: str, maximum: int) -> None:
        body = wheel_bytes if path.suffix == ".whl" else b"x"
        assert hashlib.sha256(body).hexdigest() == expected_sha
        assert len(body) == maximum
        path.write_bytes(body)

    def run(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="installed from wheel\n", stderr="")

    manifest = {
        "appworld": {
            "version": "0.1.3.post1",
            "installed_tree_sha256": "22" * 32,
            "data_tree_sha256": "33" * 32,
            "package": {
                "filename": "appworld-0.1.3.post1-py3-none-any.whl",
                "url": "https://example.invalid/appworld.whl",
                "sha256": wheel_sha,
                "size_bytes": len(wheel_bytes),
            },
            "dependency_locks": {
                "x86_64": {
                    "url": "https://example.invalid/requirements.lock",
                    "sha256": hashlib.sha256(b"x").hexdigest(),
                    "size_bytes": 1,
                }
            },
            "data_distribution": {
                "filename": "data.bundle",
                "url": "https://example.invalid/data.bundle",
                "sha256": hashlib.sha256(b"x").hexdigest(),
                "size_bytes": 1,
            },
        }
    }
    monkeypatch.setattr(appliance_worker, "_download", download)
    monkeypatch.setattr(appliance_worker.subprocess, "run", run)
    monkeypatch.setattr(appliance_worker, "_unpack_official_data", lambda path: None)
    monkeypatch.setattr(appliance_worker, "_distribution_version", lambda name: "0.1.3.post1")
    monkeypatch.setattr(appliance_worker, "_verified_appworld_tree_sha256", lambda: "22" * 32)
    monkeypatch.setattr(appliance_worker, "_tree_sha", lambda path: "33" * 32)
    monkeypatch.setattr(appliance_worker.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        appliance_worker,
        "_successor_appworld_identity",
        lambda: {"official_wheel_sha256": wheel_sha, "installed_tree_sha256": "22" * 32},
        raising=False,
    )

    appliance_worker.provision(manifest)

    pip_calls = [call for call in calls if call[1:4] == ["-m", "pip", "install"]]
    assert "-r" in pip_calls[0]
    assert "--force-reinstall" in pip_calls[1]
    assert "--no-deps" in pip_calls[1]
    assert pip_calls[1][-1].endswith("appworld-0.1.3.post1-py3-none-any.whl")


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
