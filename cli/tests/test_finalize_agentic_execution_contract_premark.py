from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from localbench.scoring.agentic_exec import execution_contract
from localbench.scoring.agentic_exec.execution_contract import (
    V5_CONTRACT_ID,
    load_execution_contract,
)
from localbench.scoring.agentic_exec.worker_identity import _WORKER_MODULES
from localbench.submissions.canon import write_json_file
from localbench.submissions.crypto import load_private_key
from localbench.submissions.keys import write_private_key

_CLI_ROOT = Path(__file__).parents[1]
_TOOL = _CLI_ROOT / "tools/finalize_agentic_execution_contract.py"
_V4_CONTRACT = (
    _CLI_ROOT
    / "src/localbench/data/contracts/agentic-execution-contract-aw013p1-pypi28113a7a-v4.json"
)

sys.path.insert(0, str(_TOOL.parent))
import finalize_agentic_execution_contract as finalize  # noqa: E402


def _args(tmp_path: Path, native: Path) -> list[str]:
    return [
        str(_TOOL),
        "--candidate-rootfs-sha256",
        "a" * 64,
        "--native-conformance-evidence",
        str(native),
        "--supersedes",
        str(_V4_CONTRACT),
        "--out",
        str(tmp_path / "out"),
        "--allow-dirty",
    ]


def test_premark_dry_run_is_deterministic_and_records_pending_evidence(
    tmp_path: Path,
) -> None:
    native = tmp_path / "native.json"
    native.write_bytes(b"native conformance evidence\n")
    first_out = tmp_path / "first"
    second_out = tmp_path / "second"
    common = [
        sys.executable,
        str(_TOOL),
        "--candidate-rootfs-sha256",
        "a" * 64,
        "--native-conformance-evidence",
        str(native),
        "--supersedes",
        str(_V4_CONTRACT),
        "--allow-dirty",
    ]

    first = subprocess.run(
        [*common, "--out", str(first_out)],
        cwd=_CLI_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [*common, "--out", str(second_out)],
        cwd=_CLI_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    assert (first_out / "payload.json").read_bytes() == (
        second_out / "payload.json"
    ).read_bytes()
    payload = json.loads((first_out / "payload.json").read_text(encoding="utf-8"))
    gate = payload["packaging_correctness_gate"]
    native_sha256 = hashlib.sha256(native.read_bytes()).hexdigest()
    assert gate["status"] == "passed-current-repo-harness-vs-appliance"
    assert gate["publication_authority"] == "signed-release-manifest"
    assert gate["evidence"] == {
        "candidate_rootfs_sha256": "a" * 64,
        "differential_report_sha256": [],
        "differential_status": "pending-post-sign-bound-in-manifest",
        "native_conformance_evidence_sha256": [native_sha256],
    }
    assert payload["score_protocol_equivalence"]["evidence_sha256"] == [
        native_sha256
    ]


def test_dry_run_writes_worker_and_host_module_origins(tmp_path: Path) -> None:
    native = tmp_path / "native.json"
    native.write_bytes(b"native conformance evidence\n")

    completed = subprocess.run(
        [sys.executable, *_args(tmp_path, native)],
        cwd=_CLI_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(
        (tmp_path / "out/modules-report.json").read_text(encoding="utf-8")
    )
    worker_modules = report["worker_modules"]
    host_modules = report["host_source_modules"]
    assert set(worker_modules) == set(_WORKER_MODULES)
    assert set(host_modules) == set(execution_contract._HOST_SOURCE_MODULES)
    for record in (*worker_modules.values(), *host_modules.values()):
        module_path = Path(record["path"])
        assert module_path.is_absolute()
        assert module_path.is_file()
        normalized = module_path.read_bytes().replace(b"\r\n", b"\n")
        assert record["sha256"] == hashlib.sha256(normalized).hexdigest()


def test_loader_rejects_signed_v5_without_publication_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = tmp_path / "native.json"
    native.write_bytes(b"native conformance evidence\n")
    key_path = tmp_path / "test-release-key.pem"
    write_private_key(key_path, seed=bytes(range(32)))
    public_key = load_private_key(key_path).public_key.hex()
    key_id = "localbench-test-v5-missing-publication-authority"
    monkeypatch.setattr(execution_contract, "CONTRACT_KEY_ID", key_id)
    monkeypatch.setattr(
        execution_contract,
        "CONTRACT_PUBLIC_KEYS",
        {**execution_contract.CONTRACT_PUBLIC_KEYS, key_id: public_key},
    )
    argv = _args(tmp_path, native)
    argv.extend(("--sign", "--signing-key", str(key_path)))
    monkeypatch.setattr(sys, "argv", argv)
    assert finalize.main() == 0
    signed_path = tmp_path / "out" / f"{V5_CONTRACT_ID}.json"
    contract = load_execution_contract(
        signed_path,
        expected_contract_id=V5_CONTRACT_ID,
    )
    payload = deepcopy(contract["payload"])
    del payload["packaging_correctness_gate"]["publication_authority"]
    invalid_path = tmp_path / "missing-authority.json"
    write_json_file(
        invalid_path,
        execution_contract.signed_contract(payload, key_path),
    )

    with pytest.raises(
        execution_contract.ExecutionContractDriftError,
        match="signed-release-manifest",
    ):
        load_execution_contract(invalid_path, expected_contract_id=V5_CONTRACT_ID)
