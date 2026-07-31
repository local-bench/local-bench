from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final, Protocol

from localbench._types import JsonObject
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
