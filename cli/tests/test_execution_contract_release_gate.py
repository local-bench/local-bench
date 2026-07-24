"""Release gate: the baked signed contract must match the live covered behavior.

0.4.6 shipped with score-affecting host modules edited after the v5 contract was
signed, so every full-suite public run aborted at the agentic handoff after ~27h
of static work.  This gate makes that class of release impossible: any commit that
touches a covered module without a re-baked contract turns the suite red.

The same assertion must also be run against the BUILT WHEEL in a scratch venv
before publishing (see RELEASE-RUNBOOK): this in-repo test cannot see packaging
mistakes such as a stale contract JSON landing in the wheel data.
"""

from __future__ import annotations

from localbench.scoring.agentic_exec.execution_contract import (
    CONTRACT_ID,
    ExecutionContractDriftError,
    assert_execution_contract,
    load_execution_contract,
)


def test_live_covered_behavior_matches_baked_signed_contract() -> None:
    payload_sha256 = assert_execution_contract()
    assert isinstance(payload_sha256, str) and len(payload_sha256) == 64


def test_baked_contract_is_the_active_contract_id() -> None:
    contract = load_execution_contract()
    payload = contract["payload"]
    assert isinstance(payload, dict)
    assert payload["contract_id"] == CONTRACT_ID


def test_drift_error_names_both_digests() -> None:
    error = ExecutionContractDriftError("a" * 64, "b" * 64)
    message = str(error)
    assert "a" * 64 in message and "b" * 64 in message
