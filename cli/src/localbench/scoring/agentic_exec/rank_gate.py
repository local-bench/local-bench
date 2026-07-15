from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.contract_scope import active_execution_contract
from localbench.scoring.agentic_exec.execution_contract import (
    CONTRACT_ID,
    load_execution_contract,
)
from localbench.scoring.agentic_exec.task_journal import (
    JournalCorruptionError,
    TaskJournal,
)
from localbench.scoring.agentic_exec.task_journal_validation import (
    committed_key,
    record_key,
)


class RankGatePolicy(StrEnum):
    LEGACY_ZEROS_IN_DENOMINATOR = "legacy_zeros_in_denominator"
    NON_MEASUREMENT = "non_measurement"


@dataclass(frozen=True, slots=True)
class ContractSemantics:
    contract_id: str
    contract_version: int
    whole_task_retry_count: int
    retryable_failure_classes: frozenset[str]
    non_retryable_failure_classes: frozenset[str]
    non_measurement_failure_classes: frozenset[str]
    rank_gate_policy: RankGatePolicy


@dataclass(frozen=True, slots=True)
class ContractSemanticsError(RuntimeError):
    field: str
    detail: str

    def __str__(self) -> str:
        return f"execution contract C6 semantics error at {self.field}: {self.detail}"


@dataclass(frozen=True, slots=True)
class RankGateVerdict:
    decision: bool
    accepted_result_record_sequences: tuple[int, ...]
    missing_measurement_task_ids: tuple[str, ...]
    unexpected_measurement_task_ids: tuple[str, ...]
    unresolved_infra_task_ids: tuple[str, ...]
    unresolved_infra_record_sequences: tuple[int, ...]
    uncertain_teardown_record_sequences: tuple[int, ...]


def resolve_contract_semantics(path: Path | None = None) -> ContractSemantics:
    selected_path, contract_id = active_execution_contract(path)
    contract = load_execution_contract(
        selected_path,
        expected_contract_id=contract_id,
    )
    payload = _object(contract.get("payload"), "payload")
    covered = _object(payload.get("covered_behavior"), "covered_behavior")
    failure_to_score = _object(
        covered.get("failure_to_score"),
        "covered_behavior.failure_to_score",
    )
    failure_classes = frozenset(
        key for key in failure_to_score if key not in {"success", "denominator"}
    )
    if contract_id == CONTRACT_ID:
        return ContractSemantics(
            contract_id=contract_id,
            contract_version=3,
            whole_task_retry_count=0,
            retryable_failure_classes=frozenset(),
            non_retryable_failure_classes=failure_classes,
            non_measurement_failure_classes=frozenset(),
            rank_gate_policy=RankGatePolicy.LEGACY_ZEROS_IN_DENOMINATOR,
        )

    contract_version = _integer(payload.get("contract_version"), "contract_version")
    if contract_version < 4:
        raise ContractSemanticsError("contract_version", "successor contracts must be v4+")
    transport = _object(
        covered.get("transport_policy"),
        "covered_behavior.transport_policy",
    )
    retries = _integer(
        transport.get("whole_task_retry_count"),
        "covered_behavior.transport_policy.whole_task_retry_count",
    )
    if retries < 0:
        raise ContractSemanticsError(
            "covered_behavior.transport_policy.whole_task_retry_count",
            "must be non-negative",
        )
    retryable = _string_set(
        transport.get("retryable_failure_classes"),
        "covered_behavior.transport_policy.retryable_failure_classes",
    )
    non_retryable = _string_set(
        transport.get("non_retryable_failure_classes"),
        "covered_behavior.transport_policy.non_retryable_failure_classes",
    )
    if retryable & non_retryable or retryable | non_retryable != failure_classes:
        raise ContractSemanticsError(
            "covered_behavior.transport_policy",
            "retryable and non-retryable classes must partition failure_to_score",
        )
    gate = _object(covered.get("rank_gate"), "covered_behavior.rank_gate")
    policy = gate.get("policy")
    if policy != RankGatePolicy.NON_MEASUREMENT.value:
        raise ContractSemanticsError(
            "covered_behavior.rank_gate.policy",
            f"expected {RankGatePolicy.NON_MEASUREMENT.value!r}, observed {policy!r}",
        )
    non_measurements = frozenset(
        key for key, value in failure_to_score.items() if value == "non_measurement"
    )
    return ContractSemantics(
        contract_id=contract_id,
        contract_version=contract_version,
        whole_task_retry_count=retries,
        retryable_failure_classes=retryable,
        non_retryable_failure_classes=non_retryable,
        non_measurement_failure_classes=non_measurements,
        rank_gate_policy=RankGatePolicy.NON_MEASUREMENT,
    )


def evaluate_rank_gate(
    journal: TaskJournal,
    *,
    required_task_ids: tuple[str, ...],
    run_index: int,
) -> RankGateVerdict:
    semantics = resolve_contract_semantics()
    required = frozenset(required_task_ids)
    accepted_records = [
        record
        for record in journal.records
        if record.record_type == "attempt_result_committed"
        and committed_key(record.payload).run_index == run_index
    ]
    accepted_by_task = {
        task_id: tuple(
            record.sequence
            for record in accepted_records
            if committed_key(record.payload).task_id == task_id
        )
        for task_id in required
    }
    missing = tuple(
        sorted(task_id for task_id, sequences in accepted_by_task.items() if len(sequences) != 1)
    )
    unexpected = tuple(
        sorted(
            {
                committed_key(record.payload).task_id
                for record in accepted_records
                if committed_key(record.payload).task_id not in required
            }
        )
    )
    failure_records = [
        record
        for record in journal.records
        if record.record_type == "attempt_failed"
        and record_key(record.record_type, record.payload).run_index == run_index
    ]
    unresolved_records = [
        record
        for record in failure_records
        if record.payload.get("failure_class")
        in semantics.non_measurement_failure_classes
        and record_key(record.record_type, record.payload).task_id in missing
    ]
    unresolved_tasks = tuple(
        sorted(
            {
                record_key(record.record_type, record.payload).task_id
                for record in unresolved_records
            }
        )
    )
    uncertain = tuple(
        record.sequence
        for record in failure_records
        if record.payload.get("teardown_state") == "uncertain"
    )
    accepted_sequences = tuple(record.sequence for record in accepted_records)
    decision = (
        journal.rankable
        and not missing
        and not unexpected
        and not unresolved_tasks
        and not uncertain
    )
    verdict = RankGateVerdict(
        decision=decision,
        accepted_result_record_sequences=accepted_sequences,
        missing_measurement_task_ids=missing,
        unexpected_measurement_task_ids=unexpected,
        unresolved_infra_task_ids=unresolved_tasks,
        unresolved_infra_record_sequences=tuple(
            record.sequence for record in unresolved_records
        ),
        uncertain_teardown_record_sequences=uncertain,
    )
    evidence: JsonObject = {
        "accepted_result_records": list(accepted_sequences),
        "missing_measurement_task_ids": list(missing),
        "unexpected_measurement_task_ids": list(unexpected),
        "unresolved_infra_task_ids": list(unresolved_tasks),
        "unresolved_infra_records": list(
            verdict.unresolved_infra_record_sequences
        ),
        "uncertain_teardown_records": list(uncertain),
    }
    if semantics.rank_gate_policy is RankGatePolicy.NON_MEASUREMENT:
        existing = journal.gate_verdict(run_index)
        if existing is not None:
            if existing.get("decision") != decision or existing.get("evidence") != evidence:
                raise JournalCorruptionError(
                    f"C6 gate verdict for run {run_index} differs from recovered evidence"
                )
            return verdict
        journal.append_gate_verdict(
            run_index=run_index,
            decision=decision,
            evidence=evidence,
        )
    return verdict


def _object(value: JsonValue | None, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ContractSemanticsError(field, "must be an object")
    return value


def _integer(value: JsonValue | None, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ContractSemanticsError(field, "must be an integer")
    return value


def _string_set(value: JsonValue | None, field: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ContractSemanticsError(field, "must be a list of non-empty strings")
    return frozenset(value)
