from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

import pytest

import localbench.orchestrate as orchestrate
from localbench.scoring.agentic_exec.execution_contract import (
    CONTRACT_ID,
    CONTRACT_SCHEMA,
    CONTRACT_SIGNATURE_DOMAIN,
    LEGACY_CONTRACT_ID,
    ExecutionContractDriftError,
    RuntimeIdentityDriftError,
    assert_execution_contract,
    assert_packaging_correctness_gate,
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


_CITATION_PATTERN = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")
_CONSTRUCTION_MARKERS = {
    "covered_behavior_sha256": '"covered_behavior_sha256": canonical_json_hash(behavior)',
}


def _payload_leaves(value: object, prefix: str = "") -> list[tuple[str, object]]:
    if isinstance(value, dict):
        leaves: list[tuple[str, object]] = []
        for key, child in value.items():
            if key != "provenance":
                child_prefix = f"{prefix}.{key}" if prefix else key
                leaves.extend(_payload_leaves(child, child_prefix))
        return leaves
    if isinstance(value, list):
        leaves = []
        for index, child in enumerate(value):
            leaves.extend(_payload_leaves(child, f"{prefix}[{index}]"))
        return leaves
    return [(prefix, value)]


def _literal_spellings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if value is True:
        return ("True", "true")
    if value is False:
        return ("False", "false")
    if value is None:
        return ("None", "null")
    return (str(value),)


def _literal_in_text(value: object, text: str) -> bool:
    searchable = text.replace("_", "") if isinstance(value, int | float) else text
    return any(spelling in searchable for spelling in _literal_spellings(value))


def _assert_provenance_citations(payload: dict[str, object], repo: Path) -> None:
    provenance = payload["provenance"]
    assert isinstance(provenance, dict)
    source_corpus: dict[Path, str] = {}
    for citation in provenance.values():
        assert isinstance(citation, str)
        for ref in citation.split(";"):
            match = _CITATION_PATTERN.fullmatch(ref)
            assert match is not None, ref
            source = repo / match.group(1)
            assert source.is_file(), source
            source_corpus[source] = source.read_text(encoding="utf-8")

    for path, value in _payload_leaves(payload):
        citation = provenance.get(path)
        assert isinstance(citation, str), path
        cited_spans: list[str] = []
        cited_sources: list[str] = []
        for ref in citation.split(";"):
            match = _CITATION_PATTERN.fullmatch(ref)
            assert match is not None, f"{path}: {ref}"
            source = repo / match.group(1)
            lines = source_corpus[source].splitlines()
            start = int(match.group(2))
            end = int(match.group(3) or start)
            assert 1 <= start <= end <= len(lines), f"{path}: {ref}"
            cited_spans.append("\n".join(lines[start - 1 : end]))
            cited_sources.append(source_corpus[source])

        literal_exists_in_cited_source = any(
            _literal_in_text(value, source) for source in cited_sources
        )
        if literal_exists_in_cited_source:
            assert any(_literal_in_text(value, span) for span in cited_spans), (
                f"{path}: literal {value!r} is outside {citation}"
            )

        marker = _CONSTRUCTION_MARKERS.get(path)
        if marker is not None:
            assert any(marker in span for span in cited_spans), (
                f"{path}: construction is outside {citation}"
            )


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
    with pytest.raises(ExecutionContractDriftError, match="not-yet-passed"):
        assert_packaging_correctness_gate()


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
    assert payload["packaging_correctness_gate"]["status"] == "not-yet-passed"
    assert payload["appworld_identity"]["appworld_data_sha256"] == identity[
        "semantic_task_sha256"
    ]
    assert len(payload["appworld_identity"]["appworld_package_sha256"]) == 64


def test_official_wheel_contract_preserves_signed_legacy_identity() -> None:
    current = load_execution_contract()
    payload = current["payload"]
    assert isinstance(payload, dict)
    assert payload["appworld_identity"]["appworld_package_sha256"] == (
        "28113a7a68f5d5a4c5e9ea5bce4743633916e741430cfb96b56030660707308a"
    )
    lineage = payload["identity_lineage"]
    assert isinstance(lineage, dict)
    legacy_path = (
        Path(__file__).parents[1]
        / "src/localbench/data/contracts/agentic-execution-contract-v1.json"
    )
    legacy = load_execution_contract(
        legacy_path, expected_contract_id=LEGACY_CONTRACT_ID
    )
    assert lineage["legacy_contract_id"] == LEGACY_CONTRACT_ID
    assert lineage["legacy_payload_sha256"] == legacy["payload_sha256"]
    assert legacy["payload"]["appworld_identity"]["appworld_package_sha256"] == (
        "faa6332bcbe379ad07561cdf270ee9c57e74d648f6a1b8d7835998ea288a1135"
    )


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
    repo = Path(__file__).resolve().parents[2]
    _assert_provenance_citations(payload, repo)


@pytest.mark.parametrize(
    "path,stale_citation",
    [
        (
            "covered_behavior_sha256",
            "cli/src/localbench/scoring/agentic_exec/execution_contract.py:95",
        ),
        (
            "task_identity.selection_recipe.seed",
            "cli/src/localbench/scoring/agentic_exec/funnel.py:57-71",
        ),
        (
            "covered_behavior.run_aggregation.threshold_pp",
            "cli/src/localbench/scoring/agentic_exec/funnel.py:425-428;"
            "cli/src/localbench/scoring/agentic_exec/funnel.py:465-541",
        ),
    ],
)
def test_provenance_validator_rejects_known_stale_citation_classes(
    path: str, stale_citation: str
) -> None:
    payload = deepcopy(load_execution_contract()["payload"])
    assert isinstance(payload, dict)
    provenance = payload["provenance"]
    assert isinstance(provenance, dict)
    provenance[path] = stale_citation

    with pytest.raises(AssertionError, match=re.escape(path)):
        _assert_provenance_citations(payload, Path(__file__).resolve().parents[2])


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


def test_successor_contract_truthfully_closes_unpassed_packaging_gate() -> None:
    payload = load_execution_contract()["payload"]
    gate = payload["packaging_correctness_gate"]
    assert gate == {
        "required": True,
        "status": "not-yet-passed",
        "kind": "current_repo_harness_vs_appliance_worker_differential",
        "equal_fields": ["model_turn_requests", "sandbox_operations", "finalize_verdict", "scored_envelopes", "aggregates"],
        "gpu_required": False,
        "admission": "fail-closed",
        "reason": "R2 reverify found the prior direct-session comparison exercised installed code against itself",
    }
