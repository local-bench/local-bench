from __future__ import annotations

from pathlib import Path

import pytest
import json
import re

import localbench.orchestrate as orchestrate
from localbench.scoring.agentic_exec.execution_contract import (
    CONTRACT_ID,
    CONTRACT_SCHEMA,
    CONTRACT_SIGNATURE_DOMAIN,
    ExecutionContractDriftError,
    RuntimeIdentityDriftError,
    assert_execution_contract,
    assert_runtime_identity,
    extract_contract_payload,
    load_execution_contract,
    signed_contract,
)
from localbench.scoring.agentic_exec.funnel import SubsetSpec
from localbench.scoring.agentic_exec.task_pool import (
    ordered_task_ids_sha256,
    selection_recipe_sha256,
    semantic_task_sha256,
)
from localbench.submissions.keys import write_private_key
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.crypto import verify_bytes


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
    signature = first["signature"]
    assert isinstance(signature, dict)
    assert verify_bytes(
        CONTRACT_SIGNATURE_DOMAIN + canonical_json_bytes(first["payload"]),
        str(signature["signature"]),
        str(signature["public_key"]),
    )
    assert not verify_bytes(
        canonical_json_bytes(first["payload"]),
        str(signature["signature"]),
        str(signature["public_key"]),
    )


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
    assert payload["packaging_correctness_gate"]["status"] == "pending-C2"
    assert payload["appworld_identity"]["appworld_data_sha256"] == identity[
        "semantic_task_sha256"
    ]
    assert len(payload["appworld_identity"]["appworld_package_sha256"]) == 64


@pytest.mark.parametrize("field,wrong", [("schema", "wrong"), ("contract_id", "wrong")])
def test_loader_validates_contract_constants_before_signature(
    tmp_path: Path, field: str, wrong: str
) -> None:
    contract = load_execution_contract()
    payload = contract["payload"]
    assert isinstance(payload, dict)
    payload[field] = wrong
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")

    expected = CONTRACT_SCHEMA if field == "schema" else CONTRACT_ID
    with pytest.raises(ExecutionContractDriftError, match=re.escape(expected)):
        load_execution_contract(path)


def test_every_signed_runtime_identity_is_enforced() -> None:
    payload = load_execution_contract()["payload"]
    assert isinstance(payload, dict)
    appworld = payload["appworld_identity"]
    sandbox = payload["sandbox_identity"]
    assert isinstance(appworld, dict) and isinstance(sandbox, dict)
    current = {
        **appworld,
        "bwrap_sha256": sandbox["bubblewrap_sha256"],
        "bwrap_version": sandbox["bubblewrap_version"],
        "appworld_root_filesystem": sandbox["appworld_root_filesystem"],
        "worker_content_sha256": sandbox["worker_content_sha256"],
    }
    assert_runtime_identity(current)
    for field in (
        "appworld_version",
        "appworld_package_sha256",
        "python_version",
        "env_pins",
        "bwrap_sha256",
        "bwrap_version",
        "appworld_root_filesystem",
        "worker_content_sha256",
    ):
        with pytest.raises(RuntimeIdentityDriftError):
            assert_runtime_identity({**current, field: "drift"})


def test_provenance_citations_exist_and_are_in_range() -> None:
    payload = load_execution_contract()["payload"]
    assert isinstance(payload, dict)
    provenance = payload["provenance"]
    assert isinstance(provenance, dict)
    repo = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")
    for citation in provenance.values():
        assert isinstance(citation, str)
        for ref in citation.split(";"):
            match = pattern.fullmatch(ref)
            assert match is not None, ref
            source = repo / match.group(1)
            assert source.is_file(), source
            line_count = len(source.read_text(encoding="utf-8").splitlines())
            start = int(match.group(2))
            end = int(match.group(3) or start)
            assert 1 <= start <= end <= line_count, ref

    literal_paths = {
        "schema": CONTRACT_SCHEMA,
        "contract_id": CONTRACT_ID,
        "task_identity.ordered_task_ids[0]": "a30375d_1",
        "task_identity.ordered_task_ids[95]": "9dabbc9_3",
        "task_identity.historical_aliases[1].sha256": (
            "7aabcf2af32300cf8769ce63cdc09353e7eab3a8681386d46fb0747950c85095"
        ),
    }
    for path, value in literal_paths.items():
        citation = str(provenance[path]).split(";")[0]
        match = pattern.fullmatch(citation)
        assert match is not None
        lines = (repo / match.group(1)).read_text(encoding="utf-8").splitlines()
        start, end = int(match.group(2)), int(match.group(3) or match.group(2))
        assert value in "\n".join(lines[start - 1 : end])


def test_frozen_artifacts_keep_legacy_hashes_and_add_contract_hashes() -> None:
    payload = load_execution_contract()["payload"]
    assert isinstance(payload, dict)
    identity = payload["task_identity"]
    assert isinstance(identity, dict)
    ids = tuple(identity["ordered_task_ids"])
    scored = SubsetSpec(
        name="scored96", split="test_normal", size=96, seed=20260624, task_ids=ids
    ).as_dict()
    injected = SubsetSpec(name="injected", split="injected", size=96, seed=0, task_ids=ids).as_dict()
    assert scored["manifest_hash"] == (
        "1920064637cf2a780e0484fcdeb2752b200a247418148eeb9a172047fe7192ad"
    )
    assert injected["manifest_hash"] == (
        "7aabcf2af32300cf8769ce63cdc09353e7eab3a8681386d46fb0747950c85095"
    )
    for artifact in (scored, injected):
        for field in (
            "ordered_task_ids_sha256",
            "selection_recipe_sha256",
            "semantic_task_sha256",
        ):
            assert artifact[field] == identity[field]


@pytest.mark.skip(reason="requires C2 appliance — packaging differential gate, spec C0")
def test_current_harness_matches_c2_appliance_differential() -> None:
    current = run_scripted_tasks_through_current_harness()  # noqa: F821
    appliance = run_scripted_tasks_through_c2_appliance()  # noqa: F821
    assert current.per_turn_requests == appliance.per_turn_requests
    assert current.sandbox_ops == appliance.sandbox_ops
    assert current.verdicts == appliance.verdicts
    assert current.aggregates == appliance.aggregates
