from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from localbench.scoring.agentic_exec.execution_contract import (
    CONTRACT_ID,
    load_execution_contract,
    validate_execution_contract_payload,
)
from localbench.submissions.canon import canonical_json_hash
from scripts.build_contract_v4_payload import (
    V4_CONTRACT_ID,
    build_v4_payload,
)


def test_v4_payload_builder_is_deterministic_and_preserves_contract_store(
    tmp_path: Path,
) -> None:
    # Given: the immutable signed v3 base and a byte snapshot of the production contract store.
    contracts = Path(__file__).parents[1] / "src/localbench/data/contracts"
    before = {path.name: path.read_bytes() for path in contracts.iterdir() if path.is_file()}
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    script = Path(__file__).parents[2] / "scripts/build_contract_v4_payload.py"

    # When: the unsigned draft is regenerated twice from current sources.
    first_run = subprocess.run(
        [sys.executable, str(script), "--output", str(first)],
        check=True,
        capture_output=True,
        text=True,
    )
    second_run = subprocess.run(
        [sys.executable, str(script), "--output", str(second)],
        check=True,
        capture_output=True,
        text=True,
    )

    # Then: bytes and printed hashes match, the loader accepts the unsigned payload shape,
    # and no production contract byte was touched.
    assert first.read_bytes() == second.read_bytes()
    assert first_run.stdout == second_run.stdout
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    validate_execution_contract_payload(payload, expected_contract_id=V4_CONTRACT_ID)
    assert first_run.stdout.strip() == f"payload_sha256={canonical_json_hash(payload)}"
    assert "signature" not in payload
    assert {path.name: path.read_bytes() for path in contracts.iterdir() if path.is_file()} == before


def test_v4_payload_builder_carries_gate_status_and_v3_lineage_verbatim() -> None:
    # Given / When: both authorized gate-status payload variants are built.
    default = build_v4_payload(gate_status="not-yet-passed")
    passed = build_v4_payload(
        gate_status="passed-current-repo-harness-vs-appliance"
    )

    # Then: only the requested status changes and v3 is the direct predecessor.
    assert default["packaging_correctness_gate"]["status"] == "not-yet-passed"
    assert passed["packaging_correctness_gate"]["status"] == (
        "passed-current-repo-harness-vs-appliance"
    )
    assert default["identity_lineage"]["predecessor_contract_id"] == CONTRACT_ID
    assert default["identity_lineage"]["predecessor_payload_sha256"] == (
        load_execution_contract()["payload_sha256"]
    )
    assert default["covered_behavior"]["run_aggregation"] == (
        load_execution_contract()["payload"]["covered_behavior"]["run_aggregation"]
    )


def test_v4_payload_builder_refuses_unknown_gate_status(tmp_path: Path) -> None:
    # Given: an unsupported packaging-gate status.
    script = Path(__file__).parents[2] / "scripts/build_contract_v4_payload.py"

    # When: the CLI parser receives it.
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--gate-status",
            "builder-invented-status",
            "--output",
            str(tmp_path / "refused.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: generation fails before writing an artifact.
    assert completed.returncode != 0
    assert not (tmp_path / "refused.json").exists()
