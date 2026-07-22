from __future__ import annotations

import base64
import hashlib
import importlib.metadata
from pathlib import Path, PurePosixPath
import subprocess

import pytest

from localbench.appliance.worker import _localbench_record_tree_sha256
import localbench.appliance.worker as appliance_worker
from localbench.scoring.agentic_exec import wsl_worker


def test_download_sends_identifying_user_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The local-bench.ai edge 403s an anonymous urllib User-Agent, so the signed-artifact
    # download must identify the client.
    payload = b"lock-bytes\n"
    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self) -> None:
            self._chunks = [payload, b""]

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://local-bench.ai/artifacts/agentic/x/appworld.lock"

        def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        captured["user_agent"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(appliance_worker, "urlopen", fake_urlopen, raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    destination = tmp_path / "appworld.lock"
    appliance_worker._download(
        "https://local-bench.ai/artifacts/agentic/x/appworld.lock",
        destination,
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    assert captured["user_agent"] == appliance_worker.DOWNLOAD_USER_AGENT
    assert destination.read_bytes() == payload


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


def test_ndjson_worker_rejects_unpassed_v3_gate_before_identity_or_task_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from localbench.scoring.agentic_exec import execution_contract

    identity_collected = False

    def collect_identity() -> dict[str, object]:
        nonlocal identity_collected
        identity_collected = True
        return {}

    def reject_gate() -> str:
        raise RuntimeError("not-yet-passed")

    monkeypatch.setattr(execution_contract, "assert_execution_contract", reject_gate)
    monkeypatch.setattr(wsl_worker, "collect_identity", collect_identity)
    assert wsl_worker.main() == 2
    assert identity_collected is False


def test_appliance_handshake_exposes_c4_measured_identity_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from localbench.scoring.agentic_exec import execution_contract, task_pool

    # Given: real values copied from the signed v3 execution-contract artifact.
    contract = execution_contract.load_execution_contract()
    payload = contract["payload"]
    assert isinstance(payload, dict)
    appworld = payload["appworld_identity"]
    sandbox = payload["sandbox_identity"]
    tasks = payload["task_identity"]
    assert isinstance(appworld, dict)
    assert isinstance(sandbox, dict)
    assert isinstance(tasks, dict)
    measured = {
        "localbench_distribution_version": "0.4.3",
        "worker_content_sha256": sandbox["worker_content_sha256"],
        "python_version": appworld["python_version"],
        "bwrap_version": sandbox["bubblewrap_version"],
        "appworld_package_sha256": appworld["appworld_package_sha256"],
    }
    monkeypatch.setattr(appliance_worker, "assert_execution_contract", lambda: contract["payload_sha256"])
    monkeypatch.setattr(appliance_worker, "assert_packaging_correctness_gate", lambda: None)
    monkeypatch.setattr(appliance_worker, "collect_identity", lambda _root: measured)
    monkeypatch.setattr(execution_contract, "contract_task_ids", lambda: list(tasks["ordered_task_ids"]))
    monkeypatch.setattr(task_pool, "load_semantic_task_contents", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(task_pool, "ordered_task_ids_sha256", lambda _ids: tasks["ordered_task_ids_sha256"])
    monkeypatch.setattr(task_pool, "semantic_task_sha256", lambda _contents: tasks["semantic_task_sha256"])
    monkeypatch.setattr(appliance_worker, "selection_recipe_sha256", lambda **_kwargs: tasks["selection_recipe_sha256"])
    monkeypatch.setattr(appliance_worker, "_file_sha", lambda _path: "ab" * 32)
    monkeypatch.setattr(appliance_worker, "_localbench_record_tree_sha256", lambda: "ab" * 32)
    monkeypatch.setattr(appliance_worker, "_verified_appworld_tree_sha256", lambda: appworld["appworld_package_sha256"])
    monkeypatch.setattr(appliance_worker, "_tree_sha", lambda _path: appworld["appworld_data_sha256"])
    monkeypatch.setattr(appliance_worker, "_owner_marker", lambda: {"runtime_id": "agentic-amd64-v1"})
    monkeypatch.setattr(appliance_worker, "_name", lambda _flag: "lbworker")

    # When: the managed worker emits its handshake.
    identity = appliance_worker.handshake()

    # Then: C4 receives measured versions and AppWorld package/data digests.
    assert identity["python_version"] == appworld["python_version"]
    assert identity["bubblewrap_version"] == sandbox["bubblewrap_version"]
    assert identity["appworld_package_sha256"] == appworld["appworld_package_sha256"]
    assert identity["appworld_data_sha256"] == appworld["appworld_data_sha256"]
    assert identity["localbench_distribution_version"] == "0.4.3"
    assert identity["worker_content_sha256"] == sandbox["worker_content_sha256"]


def test_worker_provision_interruption_stops_before_pip_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = {
        "appworld": {
            "version": "0.1.3.post1",
            "installed_tree_sha256": "22" * 32,
            "data_tree_sha256": "33" * 32,
            "package": {"filename": "appworld.whl", "url": "https://example.invalid/wheel", "sha256": "11" * 32, "size_bytes": 1},
            "dependency_locks": {"x86_64": {"url": "https://example.invalid/lock", "sha256": "44" * 32, "size_bytes": 1}},
            "data_distribution": {"filename": "data.bundle", "url": "https://example.invalid/data", "sha256": "55" * 32, "size_bytes": 1},
        }
    }
    pip_executed = False

    def interrupted_download(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected download interruption")

    def run(*_args: object, **_kwargs: object) -> object:
        nonlocal pip_executed
        pip_executed = True
        raise AssertionError("pip must not execute after interrupted download")

    monkeypatch.setattr(appliance_worker.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(appliance_worker, "_download", interrupted_download)
    monkeypatch.setattr(appliance_worker.subprocess, "run", run)
    monkeypatch.setattr(
        appliance_worker,
        "_successor_appworld_identity",
        lambda: {"official_wheel_sha256": "11" * 32, "installed_tree_sha256": "22" * 32},
    )
    with pytest.raises(OSError, match="injected download interruption"):
        appliance_worker.provision(manifest)
    assert pip_executed is False


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


def test_can_set_root_treats_unmapped_userns_root_as_unescalatable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _einval(_uid: int) -> None:
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(appliance_worker.os, "setuid", _einval, raising=False)
    assert appliance_worker._can_set_root() is False

    def _eperm(_uid: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(appliance_worker.os, "setuid", _eperm, raising=False)
    assert appliance_worker._can_set_root() is False

    monkeypatch.setattr(
        appliance_worker.os, "setuid", lambda _uid: None, raising=False
    )
    assert appliance_worker._can_set_root() is True
