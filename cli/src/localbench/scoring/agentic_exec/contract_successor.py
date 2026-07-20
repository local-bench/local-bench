from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from localbench._types import JsonObject
from localbench.submissions.canon import canonical_json_hash

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class SuccessorContractMetadata:
    contract_id: str
    contract_version: int
    supersedes_contract_id: str
    supersedes_payload_sha256: str
    candidate_rootfs_sha256: str
    differential_report_sha256: tuple[str, ...]
    native_conformance_evidence_sha256: tuple[str, ...]
    provenance_citation: str


def extract_successor_payload(
    predecessor_payload: JsonObject,
    metadata: SuccessorContractMetadata,
) -> JsonObject:
    from localbench.scoring.agentic_exec import execution_contract
    from localbench.scoring.agentic_exec.worker_identity import (
        worker_implementation_identity,
    )

    payload = deepcopy(predecessor_payload)
    behavior = execution_contract._actual_covered_behavior(predecessor_payload)
    payload["contract_id"] = metadata.contract_id
    payload["contract_version"] = metadata.contract_version
    payload["covered_behavior"] = behavior
    payload["covered_behavior_sha256"] = canonical_json_hash(behavior)

    sandbox_identity = deepcopy(execution_contract._object(payload["sandbox_identity"]))
    sandbox_identity["worker_content_sha256"] = worker_implementation_identity()[
        "worker_content_sha256"
    ]
    payload["sandbox_identity"] = sandbox_identity

    payload["supersedes_contract_id"] = metadata.supersedes_contract_id
    payload["supersedes_payload_sha256"] = metadata.supersedes_payload_sha256
    equivalence_evidence = _ordered_unique(
        (
            *metadata.differential_report_sha256,
            *metadata.native_conformance_evidence_sha256,
        )
    )
    payload["score_protocol_equivalence"] = {
        "asserted_equivalent_to": metadata.supersedes_contract_id,
        "basis": "packaging-differential+cross-topology",
        "evidence_sha256": list(equivalence_evidence),
    }

    gate = deepcopy(execution_contract._object(payload["packaging_correctness_gate"]))
    gate["status"] = "passed-current-repo-harness-vs-appliance"
    gate["evidence"] = {
        "candidate_rootfs_sha256": metadata.candidate_rootfs_sha256,
        "differential_report_sha256": list(metadata.differential_report_sha256),
        "native_conformance_evidence_sha256": list(
            metadata.native_conformance_evidence_sha256
        ),
    }
    payload["packaging_correctness_gate"] = gate

    lineage = deepcopy(execution_contract._object(payload["identity_lineage"]))
    lineage["predecessor_contract_id"] = metadata.supersedes_contract_id
    lineage["predecessor_payload_sha256"] = metadata.supersedes_payload_sha256
    lineage["relationship"] = (
        "c0v5 successor finalized after packaging differential approval"
    )
    payload["identity_lineage"] = lineage

    replaced_prefixes = (
        "contract_id",
        "contract_version",
        "covered_behavior",
        "covered_behavior_sha256",
        "identity_lineage",
        "packaging_correctness_gate",
        "sandbox_identity.worker_content_sha256",
        "score_protocol_equivalence",
        "supersedes_contract_id",
        "supersedes_payload_sha256",
    )
    previous_provenance = execution_contract._object(payload["provenance"])
    provenance = {
        key: value
        for key, value in previous_provenance.items()
        if not key.startswith(replaced_prefixes)
    }
    provenance.update(
        {prefix: metadata.provenance_citation for prefix in replaced_prefixes}
    )
    payload["provenance"] = execution_contract._leaf_provenance(payload, provenance)
    execution_contract.validate_execution_contract_payload(
        payload,
        expected_contract_id=metadata.contract_id,
    )
    return payload


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
