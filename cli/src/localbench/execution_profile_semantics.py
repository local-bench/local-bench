from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Final, Protocol

from localbench._types import JsonObject, JsonValue
from localbench.reasoning_registry import ExecutionProfileBudget

EXECUTION_PROFILE_SEMANTIC_FIELDS: Final = (
    "static_think_tokens",
    "static_final_tokens",
    "static_max_generated_tokens",
    "server_context_tokens",
    "agentic_max_turns",
    "agentic_max_output_tokens_per_turn",
    "agentic_max_generated_tokens_per_task",
    "agentic_context_tokens",
    "kv_cache_k_dtype",
    "kv_cache_v_dtype",
    "context_fit_policy",
    "context_extension_policy",
    "per_task_timeout_s",
)


@dataclass(frozen=True, slots=True)
class MissingExecutionProfileBudgetError(RuntimeError):
    profile_id: str

    def __str__(self) -> str:
        return f"execution profile {self.profile_id!r} has no resolved budget tuple"


@dataclass(frozen=True, slots=True)
class InvalidExecutionProfileSemanticRecordError(RuntimeError):
    field: str
    detail: str

    def __str__(self) -> str:
        return f"public execution profile {self.field}: {self.detail}"


class _BudgetedExecutionContract(Protocol):
    profile_id: str
    budget: ExecutionProfileBudget | None


def semantic_payload_for_budget(budget: ExecutionProfileBudget) -> JsonObject:
    return {
        "static_think_tokens": budget.static_think_tokens,
        "static_final_tokens": budget.static_final_tokens,
        "static_max_generated_tokens": budget.static_max_generated_tokens,
        "server_context_tokens": budget.server_context_tokens,
        "agentic_max_turns": budget.agentic_max_turns,
        "agentic_max_output_tokens_per_turn": budget.agentic_max_output_tokens_per_turn,
        "agentic_max_generated_tokens_per_task": budget.agentic_max_generated_tokens_per_task,
        "agentic_context_tokens": budget.agentic_context_tokens,
        "kv_cache_k_dtype": budget.kv_cache_k_dtype,
        "kv_cache_v_dtype": budget.kv_cache_v_dtype,
        "context_fit_policy": budget.context_fit_policy,
        "context_extension_policy": budget.context_extension_policy,
        "per_task_timeout_s": budget.per_task_timeout_s,
    }


def execution_profile_semantic_payload(
    contract: _BudgetedExecutionContract,
) -> JsonObject:
    budget = contract.budget
    if budget is None:
        raise MissingExecutionProfileBudgetError(contract.profile_id)
    return semantic_payload_for_budget(budget)


def optional_execution_profile_semantic_record(
    contract: _BudgetedExecutionContract,
) -> JsonObject:
    budget = contract.budget
    if budget is None:
        return {}
    return {
        **semantic_payload_for_budget(budget),
        "semantic_sha256": semantic_sha256_for_budget(budget),
    }


def semantic_sha256_for_budget(budget: ExecutionProfileBudget) -> str:
    payload = json.dumps(
        semantic_payload_for_budget(budget),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_semantic_budget_record(
    record: Mapping[str, JsonValue],
) -> ExecutionProfileBudget:
    integer_values = {
        field: _positive_integer(record, field)
        for field in EXECUTION_PROFILE_SEMANTIC_FIELDS
        if field not in {
            "kv_cache_k_dtype",
            "kv_cache_v_dtype",
            "context_fit_policy",
            "context_extension_policy",
        }
    }
    _require_literal(record, "kv_cache_k_dtype", "f16")
    _require_literal(record, "kv_cache_v_dtype", "f16")
    _require_literal(record, "context_fit_policy", "exact-or-fail")
    _require_literal(record, "context_extension_policy", "none")
    budget = ExecutionProfileBudget(
        static_think_tokens=integer_values["static_think_tokens"],
        static_final_tokens=integer_values["static_final_tokens"],
        static_max_generated_tokens=integer_values["static_max_generated_tokens"],
        server_context_tokens=integer_values["server_context_tokens"],
        agentic_max_turns=integer_values["agentic_max_turns"],
        agentic_max_output_tokens_per_turn=integer_values[
            "agentic_max_output_tokens_per_turn"
        ],
        agentic_max_generated_tokens_per_task=integer_values[
            "agentic_max_generated_tokens_per_task"
        ],
        agentic_context_tokens=integer_values["agentic_context_tokens"],
        kv_cache_k_dtype="f16",
        kv_cache_v_dtype="f16",
        context_fit_policy="exact-or-fail",
        context_extension_policy="none",
        per_task_timeout_s=integer_values["per_task_timeout_s"],
    )
    declared_digest = record.get("semantic_sha256")
    expected_digest = semantic_sha256_for_budget(budget)
    if declared_digest != expected_digest:
        raise InvalidExecutionProfileSemanticRecordError(
            "semantic_sha256",
            "does not match the canonical budget tuple",
        )
    return budget


def _positive_integer(record: Mapping[str, JsonValue], field: str) -> int:
    value = record.get(field)
    if type(value) is not int or value <= 0:
        raise InvalidExecutionProfileSemanticRecordError(
            field,
            "must be a positive integer",
        )
    return value


def _require_literal(
    record: Mapping[str, JsonValue],
    field: str,
    expected: str,
) -> None:
    value = record.get(field)
    if value != expected:
        raise InvalidExecutionProfileSemanticRecordError(
            field,
            f"must equal {expected!r}",
        )
