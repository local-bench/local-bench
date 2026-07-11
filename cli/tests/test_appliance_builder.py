from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from localbench.appliance.manifest import (
    MANIFEST_SIGNATURE_DOMAIN,
    PINNED_RUNTIME_ID,
    RUNTIME_KEY_ID,
)
from localbench.scoring.agentic_exec.execution_contract import load_execution_contract
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.crypto import verify_bytes
from localbench.submissions.keys import write_private_key


TOOLS = Path(__file__).parents[1] / "tools"
SPEC = importlib.util.spec_from_file_location(
    "build_agentic_runtime_under_test", TOOLS / "build_agentic_runtime.py"
)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(TOOLS))
SPEC.loader.exec_module(builder)


def valid_config() -> dict[str, object]:
    contract = load_execution_contract()["payload"]
    appworld_identity = contract["appworld_identity"]
    download = {"url": "https://local-bench.ai/input", "sha256": "11" * 32, "size_bytes": 1}
    script = TOOLS / "runtime_rootfs_build.sh"
    return {
        "runtime_id": PINNED_RUNTIME_ID,
        "builder_wsl_distro": "LocalBench-Staging-Test",
        "base": download,
        "apt_snapshot": {"url": "https://snapshot.ubuntu.com/ubuntu/test", "suites": ["noble"], "indexes_sha256": "22" * 32},
        "apt_packages": ["python3=3.12.3-0ubuntu1"],
        "worker_wheel_windows_path": "worker.whl",
        "dependency_lock_windows_path": "requirements.lock",
        "dependency_lock_sha256": "33" * 32,
        "wheelhouse_windows_path": "wheelhouse",
        "wheelhouse_sha256": "44" * 32,
        "worker": {"version": "0.3.1", "sha256": "55" * 32, "protocol_version": "localbench.agentic-worker.v1"},
        "python": {"version": appworld_identity["python_version"]},
        "bubblewrap": {"version": "0.9.0"},
        "appworld": {
            "version": appworld_identity["appworld_version"],
            "env_pins": appworld_identity["env_pins"],
            "package": {**download, "filename": "appworld.whl"},
            "dependency_locks": {"x86_64": download},
            "data_distribution": {**download, "filename": "data.bundle"},
            "installed_tree_sha256": appworld_identity["appworld_package_sha256"],
            "data_tree_sha256": "66" * 32,
            "semantic_task_sha256": appworld_identity["appworld_data_sha256"],
        },
        "disk_requirements": {"peak_free_bytes": 3, "steady_free_bytes": 1, "download_bytes": 1, "import_bytes": 1, "provision_growth_bytes": 1},
        "toolchain": {"gnu_tar": "1.35", "xz": "5.4.5", "builder_script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(), "source_date_epoch": 0, "umask": "022"},
        "artifact_url": f"https://local-bench.ai/{PINNED_RUNTIME_ID}/rootfs.tar.xz",
        "provenance_url": f"https://local-bench.ai/{PINNED_RUNTIME_ID}/provenance.json",
        "sbom_url": f"https://local-bench.ai/{PINNED_RUNTIME_ID}/sbom.json",
    }


def test_builder_rejects_c0_c1_appworld_identity_mismatch() -> None:
    config = valid_config()
    builder._validate_config(config)
    config["appworld"]["installed_tree_sha256"] = "ff" * 32
    with pytest.raises(ValueError, match="differs from signed C0"):
        builder._validate_config(config)


def test_offline_digest_signing_and_assembly_round_trip(tmp_path: Path) -> None:
    payload = {"schema": "test", "runtime_id": PINNED_RUNTIME_ID}
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    request = {
        "schema": "localbench.runtime_signing_request.v1",
        "domain": MANIFEST_SIGNATURE_DOMAIN.decode().rstrip("\n"),
        "key_id": RUNTIME_KEY_ID,
        "payload_sha256": digest,
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    key = tmp_path / "runtime.pem"
    public = write_private_key(key, seed=bytes(range(32)))
    signature_path = tmp_path / "signature.json"
    manifest_path = tmp_path / "manifest.json"
    subprocess.run(
        [sys.executable, str(TOOLS / "sign_runtime_release.py"), "--request", str(request_path), "--signing-key", str(key), "--out", str(signature_path)],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(TOOLS / "assemble_runtime_release.py"), "--payload", str(payload_path), "--signature", str(signature_path), "--out", str(manifest_path)],
        check=True,
    )
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert document["payload_sha256"] == digest
    assert verify_bytes(
        MANIFEST_SIGNATURE_DOMAIN + bytes.fromhex(digest),
        document["signature"]["signature"],
        public,
    )
