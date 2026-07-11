from __future__ import annotations

from pathlib import Path

import pytest

import localbench.orchestrate as orchestrate
from localbench.scoring.agentic_exec.execution_contract import (
    ExecutionContractDriftError,
    assert_execution_contract,
    extract_contract_payload,
    load_execution_contract,
    signed_contract,
)
from localbench.scoring.agentic_exec.task_pool import (
    ordered_task_ids_sha256,
    selection_recipe_sha256,
    semantic_task_sha256,
)
from localbench.submissions.keys import write_private_key


def test_contract_extraction_and_signature_are_deterministic(tmp_path: Path) -> None:
    key = tmp_path / "contract.pem"
    write_private_key(key, seed=bytes(range(32)))
    args = {
        "ordered_task_ids": ["task-b", "task-a"],
        "semantic_task_contents": {
            "task-a": {"instructions": {"instruction": "A"}},
            "task-b": {"instructions": {"instruction": "B"}},
        },
        "appworld_identity": {"appworld_version": "fixture"},
        "sandbox_identity": {"bubblewrap_version": "fixture"},
    }

    first = signed_contract(extract_contract_payload(**args), key)
    second = signed_contract(extract_contract_payload(**args), key)

    assert first == second
    assert first["payload_sha256"] == second["payload_sha256"]


def test_contract_assertion_fails_closed_on_budget_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    assert_execution_contract()
    monkeypatch.setattr(orchestrate, "_AGENTIC_SCORED_MAX_OUTPUT_TOKENS_PER_TURN", 4096)

    with pytest.raises(ExecutionContractDriftError, match="execution contract drift"):
        assert_execution_contract()


def test_task_identity_hashes_respond_only_to_their_own_inputs() -> None:
    ids = ["task-b", "task-a"]
    contents = {
        "task-a": {"instructions": "A", "setup_state": []},
        "task-b": {"instructions": "B", "setup_state": []},
    }
    ordered = ordered_task_ids_sha256(ids)
    recipe = selection_recipe_sha256(split="test_normal", seed=7, selection_version="v1")
    semantic = semantic_task_sha256(contents)

    assert ordered_task_ids_sha256(list(reversed(ids))) != ordered
    assert semantic_task_sha256(dict(reversed(list(contents.items())))) == semantic
    assert selection_recipe_sha256(split="test_normal", seed=8, selection_version="v1") != recipe
    assert ordered_task_ids_sha256(ids) == ordered
    changed_contents = {**contents, "task-a": {"instructions": "changed", "setup_state": []}}
    assert semantic_task_sha256(changed_contents) != semantic
    assert selection_recipe_sha256(split="test_normal", seed=7, selection_version="v1") == recipe


def test_checked_in_contract_is_signed_and_carries_frozen_c0_identity() -> None:
    contract = load_execution_contract()
    payload = contract["payload"]
    assert isinstance(payload, dict)
    identity = payload["task_identity"]
    assert isinstance(identity, dict)
    assert len(identity["ordered_task_ids"]) == 96
    assert identity["ordered_task_ids_sha256"] == (
        "16394237615c06aa419135cca2543ab66957a6af092e7da817565d3518ee648c"
    )
    assert {item["sha256"] for item in identity["historical_aliases"]} == {
        "1920064637cf2a780e0484fcdeb2752b200a247418148eeb9a172047fe7192ad",
        "7aabcf2af32300cf8769ce63cdc09353e7eab3a8681386d46fb0747950c85095",
    }
    assert payload["legacy_continuity"]["decision"] == "accepted_by_owner_fiat"
    assert payload["packaging_correctness_gate"]["required"] is True
