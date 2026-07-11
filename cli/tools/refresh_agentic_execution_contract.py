"""Mint a successor C0 contract without retargeting the legacy board contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from localbench.scoring.agentic_exec import execution_contract
from localbench.scoring.agentic_exec.worker_identity import worker_implementation_identity
from localbench.submissions.canon import canonical_json_hash, write_json_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--evidence-out", required=True, type=Path)
    parser.add_argument("--appworld-installed-tree-sha256", required=True)
    parser.add_argument("--official-wheel-sha256", required=True)
    parser.add_argument("--signing-key", required=True, type=Path)
    args = parser.parse_args()
    document = json.loads(args.contract.read_text(encoding="utf-8"))
    payload = dict(document["payload"])
    payload["contract_id"] = execution_contract.CONTRACT_ID
    behavior, provenance = execution_contract._extract_covered_behavior()
    payload["covered_behavior"] = behavior
    payload["covered_behavior_sha256"] = canonical_json_hash(behavior)
    existing_provenance = dict(payload["provenance"])
    existing_provenance.update(provenance)
    existing_provenance["covered_behavior_sha256"] = (
        "cli/src/localbench/scoring/agentic_exec/execution_contract.py:128"
    )
    existing_provenance["schema"] = (
        "cli/src/localbench/scoring/agentic_exec/execution_contract.py:24"
    )
    existing_provenance["contract_id"] = (
        "cli/src/localbench/scoring/agentic_exec/execution_contract.py:23"
    )
    for path in list(existing_provenance):
        if path == "legacy_continuity" or path.startswith("legacy_continuity."):
            existing_provenance[path] = (
                "cli/src/localbench/scoring/agentic_exec/execution_contract.py:153-159"
            )
    payload["provenance"] = execution_contract._leaf_provenance(payload, existing_provenance)
    sandbox = dict(payload["sandbox_identity"])
    implementation = worker_implementation_identity()
    sandbox["worker_content_sha256"] = implementation["worker_content_sha256"]
    payload["sandbox_identity"] = sandbox
    appworld = dict(payload["appworld_identity"])
    appworld["appworld_package_sha256"] = args.appworld_installed_tree_sha256
    payload["appworld_identity"] = appworld
    payload["packaging_correctness_gate"] = {
        "required": True,
        "status": "not-yet-passed",
        "kind": "current_repo_harness_vs_appliance_worker_differential",
        "equal_fields": [
            "model_turn_requests",
            "sandbox_operations",
            "finalize_verdict",
            "scored_envelopes",
            "aggregates",
        ],
        "gpu_required": False,
        "admission": "fail-closed",
        "reason": "R2 reverify found the prior direct-session comparison exercised installed code against itself",
    }
    prior_id = str(document["payload"]["contract_id"])
    prior_sha = str(document["payload_sha256"])
    payload["identity_lineage"] = {
        "legacy_contract_id": execution_contract.LEGACY_CONTRACT_ID,
        "legacy_payload_sha256": document["payload"]["identity_lineage"]["legacy_payload_sha256"],
        "predecessor_contract_id": prior_id,
        "predecessor_payload_sha256": prior_sha,
        "relationship": "owner-authorized successor for official PyPI AppWorld wheel; legacy contract remains authoritative for existing board rows and wave-1",
        "official_wheel_sha256": args.official_wheel_sha256,
    }
    provenance = dict(payload["provenance"])
    provenance["contract_id"] = "cli/src/localbench/scoring/agentic_exec/execution_contract.py:23"
    for path in list(provenance):
        if path == "packaging_correctness_gate" or path.startswith(
            "packaging_correctness_gate."
        ):
            del provenance[path]
    gate_source = "cli/src/localbench/data/contracts/README.md:19-25"
    for key, value in payload["packaging_correctness_gate"].items():
        if isinstance(value, list):
            for index in range(len(value)):
                provenance[f"packaging_correctness_gate.{key}[{index}]"] = gate_source
        else:
            provenance[f"packaging_correctness_gate.{key}"] = gate_source
    for key in appworld:
        prefix = f"appworld_identity.{key}"
        for path in list(provenance):
            if path == prefix or path.startswith(prefix + "."):
                provenance[path] = (
                    "cli/src/localbench/data/contracts/"
                    f"{execution_contract.CONTRACT_ID}-evidence.json:1"
                )
    provenance["sandbox_identity.worker_content_sha256"] = (
        "cli/src/localbench/data/contracts/"
        f"{execution_contract.CONTRACT_ID}-evidence.json:1"
    )
    for key in payload["identity_lineage"]:
        provenance[f"identity_lineage.{key}"] = (
            "cli/src/localbench/data/contracts/README.md:1-16"
        )
    payload["provenance"] = execution_contract._leaf_provenance(payload, provenance)
    signed = execution_contract.signed_contract(payload, args.signing_key)
    write_json_file(args.out, signed)
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    runtime = {
        key: value
        for key, value in dict(evidence["runtime_identity"]).items()
        if key in {"appworld_version", "python_version", "bwrap_sha256", "bwrap_version", "appworld_root_filesystem", "env_pins"}
    }
    runtime.update(implementation)
    runtime["appworld_package_sha256"] = args.appworld_installed_tree_sha256
    evidence["runtime_identity"] = runtime
    evidence["contract_id"] = execution_contract.CONTRACT_ID
    evidence["contract_payload_sha256"] = signed["payload_sha256"]
    evidence["official_pypi_wheel_sha256"] = args.official_wheel_sha256
    evidence["legacy_contract_id"] = execution_contract.LEGACY_CONTRACT_ID
    evidence["legacy_contract_payload_sha256"] = payload["identity_lineage"]["legacy_payload_sha256"]
    evidence["predecessor_contract_id"] = prior_id
    evidence["predecessor_contract_payload_sha256"] = prior_sha
    evidence["packaging_correctness_gate"] = payload["packaging_correctness_gate"]
    evidence["source"] = "R2 fail-closed successor contract extraction; packaging differential not yet passed"
    write_json_file(args.evidence_out, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
