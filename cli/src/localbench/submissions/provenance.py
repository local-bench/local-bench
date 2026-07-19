from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from localbench._types import JsonObject
from localbench.submissions.attestation import (
    expected_attester_public_key_hex,
    verify_verdict_attestation,
)

AgenticProvenanceLabel = Literal["none", "project_attested", "self_reported"]


@dataclass(frozen=True, slots=True)
class CarriedVerdict:
    bench: str
    task_id: str
    correct: bool


@dataclass(frozen=True, slots=True)
class AgenticProvenanceResult:
    label: AgenticProvenanceLabel
    notes: tuple[str, ...] = ()


def evaluate_agentic_provenance(
    carried: Sequence[CarriedVerdict],
    attestations: Sequence[JsonObject],
    *,
    bundle_sha256: str,
    grandfathered_bundle_sha256s: frozenset[str],
) -> AgenticProvenanceResult:
    if not carried:
        return AgenticProvenanceResult("none")
    if bundle_sha256 in grandfathered_bundle_sha256s:
        return AgenticProvenanceResult("project_attested")
    covered, mismatch = _covered_items(attestations)
    missing = [
        f"attestation_missing:{item.bench}/{item.task_id}"
        for item in carried
        if (item.bench, item.task_id, item.correct) not in covered
    ]
    if not missing and not mismatch:
        return AgenticProvenanceResult("project_attested")
    notes = (("attestation_pubkey_mismatch",) if mismatch else ()) + tuple(missing)
    return AgenticProvenanceResult("self_reported", notes)


def carried_from_result_items(
    items: Sequence[JsonObject],
    dynamic_benches: frozenset[str],
) -> list[CarriedVerdict]:
    return [
        CarriedVerdict(
            bench=item["bench"],
            task_id=item["id"],
            correct=item["correct"],
        )
        for item in items
        if item.get("bench") in dynamic_benches
        and isinstance(item.get("bench"), str)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("correct"), bool)
    ]


def carried_from_submission_items(
    items: Sequence[JsonObject],
    dynamic_benches: frozenset[str],
) -> list[CarriedVerdict]:
    carried: list[CarriedVerdict] = []
    for item in items:
        bench = item.get("bench")
        task_id = item.get("item_id")
        scoring = item.get("client_scoring")
        if bench not in dynamic_benches or not isinstance(bench, str) or not isinstance(task_id, str):
            continue
        correct = scoring.get("correct") if isinstance(scoring, dict) else None
        if not isinstance(correct, bool):
            continue
        carried.append(CarriedVerdict(bench=bench, task_id=task_id, correct=correct))
    return carried


def _covered_items(attestations: Sequence[JsonObject]) -> tuple[set[tuple[str, str, bool]], bool]:
    expected_key = expected_attester_public_key_hex()
    covered: set[tuple[str, str, bool]] = set()
    mismatch = False
    for record in attestations:
        signature = record.get("signature")
        if isinstance(signature, dict) and expected_key is not None:
            public_key = signature.get("public_key")
            mismatch = mismatch or (isinstance(public_key, str) and public_key.lower() != expected_key.lower())
        if not verify_verdict_attestation(record):
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        verdict = payload.get("verdict")
        if not isinstance(verdict, dict):
            continue
        bench = payload.get("bench")
        task_id = payload.get("task_id")
        success = verdict.get("success")
        if isinstance(bench, str) and isinstance(task_id, str) and isinstance(success, bool):
            covered.add((bench, task_id, success))
    return covered, mismatch
