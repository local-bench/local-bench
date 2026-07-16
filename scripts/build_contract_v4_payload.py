#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Build the default unsigned draft:
#      uv run scripts/build_contract_v4_payload.py
# 3. Ceremony build (sign-first, fail-closed): gate-status=passed is signed BEFORE the
#    differential can run — worker startup refuses any other status — and the C0 packaging
#    differential is the mandatory release post-condition validating the shipped bytes:
#      uv run scripts/build_contract_v4_payload.py --gate-status passed-current-repo-harness-vs-appliance
# ──────────────────

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Final, Literal

from localbench._types import JsonObject
from localbench.scoring.agentic_exec.execution_contract import (
    _C6_SOURCE_MODULES,
    _HOST_SOURCE_MODULES,
    _extract_covered_behavior,
    _leaf_provenance,
    _object,
    _source_bundle_sha256,
    load_execution_contract,
    validate_execution_contract_payload,
)
from localbench.scoring.agentic_exec.worker_identity import worker_implementation_identity
from localbench.submissions.canon import canonical_json_hash, write_json_file

# Literal (not derived from CONTRACT_ID): the builder must produce identical payloads before
# AND after the activation bump of execution_contract.CONTRACT_ID to the v4 id.
V4_CONTRACT_ID: Final = "agentic-execution-contract-aw013p1-pypi28113a7a-v4"
BASE_CONTRACT_ID: Final = "agentic-execution-contract-aw013p1-pypi28113a7a-v3"
V4_CONTRACT_VERSION: Final = 4
V4_WHOLE_TASK_RETRY_COUNT: Final = 2
GateStatus = Literal[
    "not-yet-passed",
    "passed-current-repo-harness-vs-appliance",
]
GATE_STATUSES: Final[tuple[GateStatus, ...]] = (
    "not-yet-passed",
    "passed-current-repo-harness-vs-appliance",
)
REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT: Final = REPO_ROOT / "scratchpad/contract-v4-payload-DRAFT.json"
RAW_RUN_PROVENANCE_PATHS: Final = (
    "runs/bench/ranked-5axis-capped-2026-07-03/agentic/localbench-run/"
    "gemma-4-12b-it-qat-ud-q4-k-xl.scored.run1.json",
    "cli/runs/agentic/qwen36-27b-Q6_K.scored.run1.json",
)
TASK_IDENTITY_RUN_EXCERPT_CITATION: Final = (
    "cli/src/localbench/data/contracts/agentic-task-identity-run-excerpts-v1.json:1"
)


def build_v4_payload(*, gate_status: GateStatus) -> JsonObject:
    # The v3 predecessor is the base regardless of which contract id is currently active.
    base_contract = load_execution_contract(
        REPO_ROOT / "cli/src/localbench/data/contracts" / f"{BASE_CONTRACT_ID}.json",
        expected_contract_id=BASE_CONTRACT_ID,
    )
    base = deepcopy(_object(base_contract["payload"]))
    behavior, _ = _extract_covered_behavior()
    behavior["host_agent_loop_scorer_source_sha256"] = _source_bundle_sha256(
        (*_HOST_SOURCE_MODULES, *_C6_SOURCE_MODULES)
    )
    behavior["run_aggregation"] = deepcopy(
        _object(_object(base["covered_behavior"])["run_aggregation"])
    )
    transport = _object(behavior["transport_policy"])
    transport["whole_task_retry_count"] = V4_WHOLE_TASK_RETRY_COUNT
    transport["retryable_failure_classes"] = [
        "infra_sandbox",
        "infra_timeout",
    ]
    transport["non_retryable_failure_classes"] = [
        "cap_exceeded",
        "harness_error",
        "model_failure",
        "model_no_progress",
        "no_final_answer",
    ]
    behavior["failure_to_score"] = {
        "success": 1,
        "cap_exceeded": 0,
        "no_final_answer": 0,
        "model_failure": 0,
        "model_no_progress": 0,
        "infra_timeout": "non_measurement",
        "infra_sandbox": "non_measurement",
        "harness_error": "non_measurement",
        "denominator": "accepted_measurements",
    }
    behavior["rank_gate"] = {
        "policy": "non_measurement",
        "required_measurements_per_task": 1,
        "maximum_unresolved_infra_tasks": 0,
        "maximum_uncertain_teardowns": 0,
        "ranked_score_field": "agentic_success_rate",
    }

    base["contract_id"] = V4_CONTRACT_ID
    base["contract_version"] = V4_CONTRACT_VERSION
    base["covered_behavior"] = behavior
    base["covered_behavior_sha256"] = canonical_json_hash(behavior)
    sandbox_identity = deepcopy(_object(base["sandbox_identity"]))
    sandbox_identity["worker_content_sha256"] = worker_implementation_identity()[
        "worker_content_sha256"
    ]
    base["sandbox_identity"] = sandbox_identity
    lineage = deepcopy(_object(base["identity_lineage"]))
    lineage["predecessor_contract_id"] = BASE_CONTRACT_ID
    lineage["predecessor_payload_sha256"] = str(base_contract["payload_sha256"])
    lineage["relationship"] = (
        "C6 successor activated under the release signing key; sign-first ceremony -- the"
        " C0 packaging differential is the mandatory release post-condition"
        if gate_status == "passed-current-repo-harness-vs-appliance"
        else "unsigned C6 successor draft; release signature required before activation"
    )
    base["identity_lineage"] = lineage
    packaging_gate = deepcopy(_object(base["packaging_correctness_gate"]))
    packaging_gate["status"] = gate_status
    base["packaging_correctness_gate"] = packaging_gate

    builder_citation = _builder_citation()
    previous_provenance = _object(base["provenance"])
    replaced_prefixes = (
        "contract_id",
        "covered_behavior",
        "covered_behavior_sha256",
        "identity_lineage",
        "packaging_correctness_gate",
        "sandbox_identity.worker_content_sha256",
    )
    provenance = {
        key: (
            TASK_IDENTITY_RUN_EXCERPT_CITATION
            if any(path in str(value) for path in RAW_RUN_PROVENANCE_PATHS)
            else value
        )
        for key, value in previous_provenance.items()
        if not key.startswith(replaced_prefixes)
    }
    provenance.update(
        {
            "contract_id": builder_citation,
            "contract_version": builder_citation,
            "covered_behavior": builder_citation,
            "covered_behavior_sha256": builder_citation,
            "identity_lineage": builder_citation,
            "packaging_correctness_gate": builder_citation,
            "sandbox_identity.worker_content_sha256": builder_citation,
        }
    )
    base["provenance"] = _leaf_provenance(base, provenance)
    validate_execution_contract_payload(base, expected_contract_id=V4_CONTRACT_ID)
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the unsigned C6 execution-contract v4 payload")
    parser.add_argument(
        "--gate-status",
        choices=GATE_STATUSES,
        default="not-yet-passed",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_v4_payload(gate_status=args.gate_status)
    write_json_file(args.output, payload)
    print(f"payload_sha256={canonical_json_hash(payload)}")
    return 0


def _builder_citation() -> str:
    line_count = len(Path(__file__).read_text(encoding="utf-8").splitlines())
    return f"scripts/build_contract_v4_payload.py:1-{line_count}"


if __name__ == "__main__":
    raise SystemExit(main())
