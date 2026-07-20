from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from localbench.scoring.agentic_exec import execution_contract
from localbench.scoring.agentic_exec.execution_contract import (
    V5_CONTRACT_ID,
    load_execution_contract,
)
from localbench.submissions.canon import (
    canonical_json_bytes,
    canonical_json_hash,
)
from localbench.submissions.crypto import load_private_key, verify_bytes
from localbench.submissions.keys import write_private_key


_CLI_ROOT = Path(__file__).parents[1]
_TOOL = _CLI_ROOT / "tools/finalize_agentic_execution_contract.py"
_V4_CONTRACT = (
    _CLI_ROOT
    / "src/localbench/data/contracts/agentic-execution-contract-aw013p1-pypi28113a7a-v4.json"
)
_V4_PAYLOAD_SHA256 = "fbc49a592bb46f047c9785bc9a6036bd64de0ad548597e2ff8ea540b1edfa5ac"
_V4_FILE_SHA256 = "b722a296899fc8a26b3c5c422ce072fe52b51abf40e432751d273bfd3575bd1c"

sys.path.insert(0, str(_TOOL.parent))
import finalize_agentic_execution_contract as finalize  # noqa: E402


def _dry_run_args(
    tmp_path: Path,
    *,
    differential_reports: tuple[Path, ...] = (),
    native_evidence: tuple[Path, ...] = (),
    allow_dirty: bool = True,
) -> list[str]:
    args = [
        str(_TOOL),
        "--candidate-rootfs-sha256",
        "a" * 64,
    ]
    for report in differential_reports:
        args.extend(("--differential-report", str(report)))
    for evidence in native_evidence:
        args.extend(("--native-conformance-evidence", str(evidence)))
    args.extend(
        (
            "--supersedes",
            str(_V4_CONTRACT),
            "--out",
            str(tmp_path / "out"),
        )
    )
    if allow_dirty:
        args.append("--allow-dirty")
    return args


def test_dry_run_is_deterministic(tmp_path: Path) -> None:
    # Given: fixed release evidence and the committed v4 predecessor.
    differential = tmp_path / "differential.json"
    differential.write_text('{"verdict":"pass"}\n', encoding="utf-8")
    first_out = tmp_path / "first"
    second_out = tmp_path / "second"
    common = [
        sys.executable,
        str(_TOOL),
        "--candidate-rootfs-sha256",
        "a" * 64,
        "--differential-report",
        str(differential),
        "--supersedes",
        str(_V4_CONTRACT),
        "--allow-dirty",
    ]

    # When: the default dry-run is invoked twice.
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

    # Then: both payload artifacts and printed digests are byte-identical.
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (first_out / "payload.json").read_bytes() == (
        second_out / "payload.json"
    ).read_bytes()
    assert first.stdout == second.stdout


def test_dry_run_does_not_import_signing_code(tmp_path: Path) -> None:
    # Given: a fresh interpreter that rejects any signing-module import.
    differential = tmp_path / "differential.json"
    differential.write_bytes(b"approved differential\n")
    guard = """
import builtins
import runpy
import sys

real_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == "localbench.submissions.crypto":
        raise AssertionError("dry-run imported signing code")
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
tool = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(tool, run_name="__main__")
"""

    # When: the default mode is invoked under the import guard.
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            guard,
            *_dry_run_args(tmp_path, differential_reports=(differential,)),
        ],
        cwd=_CLI_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: payload extraction succeeds without importing the signing module.
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "out/payload.json").is_file()


def test_dry_run_flips_gate_and_binds_release_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: differential and cross-topology evidence files.
    differential = tmp_path / "differential.json"
    native = tmp_path / "native.json"
    differential.write_bytes(b"differential evidence\n")
    native.write_bytes(b"native evidence\n")
    monkeypatch.setattr(
        sys,
        "argv",
        _dry_run_args(
            tmp_path,
            differential_reports=(differential,),
            native_evidence=(native,),
        ),
    )

    # When: the payload is finalized without signing.
    assert finalize.main() == 0

    # Then: the passed gate binds the candidate rootfs and every evidence digest.
    payload = json.loads((tmp_path / "out/payload.json").read_text(encoding="utf-8"))
    gate = payload["packaging_correctness_gate"]
    assert gate["status"] == "passed-current-repo-harness-vs-appliance"
    assert gate["publication_authority"] == "signed-release-manifest"
    assert gate["evidence"] == {
        "candidate_rootfs_sha256": "a" * 64,
        "differential_report_sha256": [
            hashlib.sha256(differential.read_bytes()).hexdigest()
        ],
        "native_conformance_evidence_sha256": [
            hashlib.sha256(native.read_bytes()).hexdigest()
        ],
    }


def test_dry_run_carries_v4_successor_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the committed, signed v4 contract and differential evidence.
    differential = tmp_path / "differential.json"
    differential.write_bytes(b"differential evidence\n")
    monkeypatch.setattr(
        sys,
        "argv",
        _dry_run_args(tmp_path, differential_reports=(differential,)),
    )

    # When: the v5 payload is extracted.
    assert finalize.main() == 0

    # Then: v4 is identified by both its signed id and canonical payload digest.
    payload = json.loads((tmp_path / "out/payload.json").read_text(encoding="utf-8"))
    predecessor = load_execution_contract(
        _V4_CONTRACT,
        expected_contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v4",
    )
    assert payload["contract_id"] == V5_CONTRACT_ID
    assert payload["contract_version"] == 5
    assert payload["supersedes_contract_id"] == predecessor["payload"]["contract_id"]
    assert payload["supersedes_payload_sha256"] == _V4_PAYLOAD_SHA256
    assert payload["score_protocol_equivalence"] == {
        "asserted_equivalent_to": predecessor["payload"]["contract_id"],
        "basis": "packaging-differential+cross-topology",
        "evidence_sha256": [hashlib.sha256(differential.read_bytes()).hexdigest()],
    }


def test_sign_mode_round_trips_through_real_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an ephemeral Ed25519 release key trusted for this test only.
    native = tmp_path / "native.json"
    native.write_bytes(b"native conformance evidence\n")
    key_path = tmp_path / "test-release-key.pem"
    write_private_key(key_path, seed=bytes(range(32)))
    public_key = load_private_key(key_path).public_key.hex()
    test_key_id = "localbench-test-v5-finalize"
    monkeypatch.setattr(execution_contract, "CONTRACT_KEY_ID", test_key_id)
    monkeypatch.setattr(
        execution_contract,
        "CONTRACT_PUBLIC_KEYS",
        {**execution_contract.CONTRACT_PUBLIC_KEYS, test_key_id: public_key},
    )
    argv = _dry_run_args(tmp_path, native_evidence=(native,))
    argv.extend(("--sign", "--signing-key", str(key_path)))
    monkeypatch.setattr(sys, "argv", argv)

    # When: the approved payload is signed and self-checked.
    assert finalize.main() == 0

    # Then: the final artifact verifies and loads through the production loader.
    contract_path = tmp_path / "out" / f"{V5_CONTRACT_ID}.json"
    contract = load_execution_contract(
        contract_path,
        expected_contract_id=V5_CONTRACT_ID,
    )
    signature = contract["signature"]
    assert isinstance(signature, dict)
    assert verify_bytes(
        execution_contract.CONTRACT_SIGNATURE_DOMAIN
        + canonical_json_bytes(contract["payload"]),
        str(signature["signature"]),
        public_key,
    )


def test_committed_v4_contract_still_loads_with_pinned_payload_hash() -> None:
    # Given / When: the immutable v4 artifact is loaded through the production loader.
    contract = load_execution_contract(
        _V4_CONTRACT,
        expected_contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v4",
    )

    # Then: its stored and recomputed canonical payload digests retain the release value.
    assert contract["payload_sha256"] == _V4_PAYLOAD_SHA256
    assert canonical_json_hash(contract["payload"]) == _V4_PAYLOAD_SHA256
    assert hashlib.sha256(_V4_CONTRACT.read_bytes()).hexdigest() == _V4_FILE_SHA256


def test_dirty_tracked_tree_is_refused(tmp_path: Path) -> None:
    # Given: a tracked-file modification and no explicit dirty-tree override.
    differential = tmp_path / "differential.json"
    differential.write_bytes(b"approved differential\n")
    tracked_path = _CLI_ROOT / "README.md"
    original = tracked_path.read_bytes()
    tracked_path.write_bytes(original + b"\n")
    try:
        # When: finalize is invoked against the dirty worktree.
        completed = subprocess.run(
            [
                sys.executable,
                *_dry_run_args(
                    tmp_path,
                    differential_reports=(differential,),
                    allow_dirty=False,
                ),
            ],
            cwd=_CLI_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        tracked_path.write_bytes(original)

    # Then: no payload is written and the refusal explains the override.
    assert completed.returncode != 0
    assert "tracked git tree is dirty" in completed.stderr
    assert not (tmp_path / "out/payload.json").exists()
