from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Literal

import pytest

from localbench._types import JsonObject
from localbench.scoring.agentic_exec import execution_contract
from localbench.scoring.agentic_exec.execution_contract import (
    V5_CONTRACT_ID,
    SuccessorContractMetadata,
    extract_contract_payload,
    load_execution_contract,
)
from localbench.scoring.agentic_exec.worker_identity import _WORKER_MODULES
from localbench.submissions.canon import canonical_json_hash, write_json_file
from localbench.submissions.crypto import load_private_key
from localbench.submissions.keys import write_private_key

CLI_ROOT = Path(__file__).parents[1]
VERIFIER = CLI_ROOT / "tools/verify_release_evidence.py"
DIFFERENTIAL_TOOL = CLI_ROOT / "tools/packaging_differential.py"
V4_CONTRACT = (
    CLI_ROOT
    / "src/localbench/data/contracts/agentic-execution-contract-aw013p1-pypi28113a7a-v4.json"
)
ROOTFS_SHA256 = "a" * 64
WHEEL_SHA256 = "b" * 64

sys.path.insert(0, str(DIFFERENTIAL_TOOL.parent))
import packaging_differential as differential  # noqa: E402


@dataclass(frozen=True, slots=True)
class ReleaseFixture:
    contract_path: Path
    contract_id: str
    contract_payload_sha256: str
    key_id: str
    public_key: str


def _module_origins(prefix: str) -> JsonObject:
    origins: JsonObject = {
        name: f"{prefix}{name.replace('.', '/')}.py" for name in _WORKER_MODULES
    }
    origins.update(
        {
            "localbench": f"{prefix}localbench/__init__.py",
            "sys_prefix": "/opt/localbench/venv",
            "sys_path": [
                prefix.rstrip("/"),
                "/opt/localbench/venv/lib/python3.12/site-packages",
            ],
        }
    )
    return origins


def _trace() -> differential.TaskTrace:
    return differential.TaskTrace(
        model_turn_requests=[{"messages": [], "params": {"seed": 0}}],
        sandbox_operations=[{"request": {"op": "run_block"}, "reply": {}}],
        finalize_verdict={"success": True, "collateral_damage": False},
        scored_envelopes=[{"payload_sha256": "c" * 64}],
    )


def _side(prefix: str) -> differential.SideRun:
    return differential.SideRun(
        worker_identity={"worker_content_sha256": "d" * 64},
        per_task={task_id: _trace() for task_id in differential.TASK_IDS},
        aggregates={"tasks_total": len(differential.TASK_IDS)},
        spawn_argv=("wsl.exe", "--worker"),
        module_origins=_module_origins(prefix),
        cwd="/tmp/packaging-differential",
    )


def build_evidence(
    release: ReleaseFixture,
    *,
    mode: Literal["differential", "self-test"] = "differential",
) -> JsonObject:
    repo = _side("/opt/localbench/diff-src/")
    appliance = _side("/opt/localbench/venv/lib/python3.12/site-packages/")
    comparison = differential.compare_sides(repo, appliance, differential.TASK_IDS)
    return differential.build_evidence(
        runtime_id="runtime-v5",
        distro_name="LocalBench-Staging-runtime-v5",
        contract_id=release.contract_id,
        contract_payload_sha256=release.contract_payload_sha256,
        rootfs_sha256=ROOTFS_SHA256,
        worker_wheel_sha256=WHEEL_SHA256,
        task_ids=differential.TASK_IDS,
        repo=repo,
        appliance=appliance,
        comparison=comparison,
        staged_source=differential.StagedSource(
            staged_file_count=42,
            staged_manifest_sha256="e" * 64,
        ),
        mode=mode,
    )


def make_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ReleaseFixture:
    key_path = tmp_path / "release-key.pem"
    write_private_key(key_path, seed=bytes(range(32)))
    public_key = load_private_key(key_path).public_key.hex()
    key_id = "localbench-test-release-evidence"
    monkeypatch.setattr(execution_contract, "CONTRACT_KEY_ID", key_id)
    predecessor = load_execution_contract(V4_CONTRACT)
    predecessor_payload = predecessor["payload"]
    assert isinstance(predecessor_payload, dict)
    payload = extract_contract_payload(
        predecessor_payload=predecessor_payload,
        successor_metadata=SuccessorContractMetadata(
            contract_id=V5_CONTRACT_ID,
            contract_version=5,
            supersedes_contract_id=str(predecessor_payload["contract_id"]),
            supersedes_payload_sha256=canonical_json_hash(predecessor_payload),
            candidate_rootfs_sha256=ROOTFS_SHA256,
            differential_report_sha256=(),
            native_conformance_evidence_sha256=("f" * 64,),
            provenance_citation="cli/tools/finalize_agentic_execution_contract.py:1-220",
        ),
    )
    contract_path = tmp_path / "pending-v5.json"
    write_json_file(contract_path, execution_contract.signed_contract(payload, key_path))
    return ReleaseFixture(
        contract_path=contract_path,
        contract_id=V5_CONTRACT_ID,
        contract_payload_sha256=canonical_json_hash(payload),
        key_id=key_id,
        public_key=public_key,
    )


def run_verifier(
    release: ReleaseFixture,
    evidence_paths: tuple[Path, ...],
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    guard = "\n".join(
        (
            "import runpy",
            "import sys",
            "from localbench.scoring.agentic_exec import execution_contract",
            "execution_contract.CONTRACT_PUBLIC_KEYS = {sys.argv[1]: sys.argv[2]}",
            "tool = sys.argv[3]",
            "sys.argv = sys.argv[3:]",
            'runpy.run_path(tool, run_name="__main__")',
        )
    )
    args = [
        sys.executable,
        "-c",
        guard,
        release.key_id,
        release.public_key,
        str(VERIFIER),
    ]
    for path in evidence_paths:
        args.extend(("--evidence", str(path)))
    args.extend(
        (
            "--pending-contract",
            str(release.contract_path),
            "--rootfs-sha256",
            ROOTFS_SHA256,
            "--worker-wheel-sha256",
            WHEEL_SHA256,
            *extra,
        )
    )
    return subprocess.run(
        args,
        cwd=CLI_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_evidence(tmp_path: Path, evidence: JsonObject) -> Path:
    path = tmp_path / "evidence.json"
    write_json_file(path, evidence)
    return path
