from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, assert_never

from localbench._types import JsonObject, JsonValue
from localbench.budget_forcing import CAPPED_THINKING_THINK_BUDGET
from localbench.gguf_template import StaticProfileCandidate
from localbench.reasoning_registry import (
    ANSWER_ONLY_PROFILE,
    ReasoningRegistryEntry,
)

HF_CANONICAL_TEMPLATE_POLICY: Final = "hf-canonical-template-v1"
GGUF_EFFECTIVE_TEMPLATE_POLICY: Final = "gguf-effective-template-v1"
_PUBLIC_EXECUTION_PROFILE_FIELDS: Final = (
    "id",
    "selection_policy_id",
    "selection_reason",
    "template_source",
    "template_sha256",
    "chat_template_kwargs",
    "answer_stops",
    "runtime_probe_passed",
    "prompt_renderer_engine",
)


@dataclass(frozen=True, slots=True)
class ResolvedExecutionContract:
    profile_id: str
    selection_policy_id: str
    selection_reason: str
    template_source: str
    raw_template_sha256: str | None
    effective_template_sha256: str | None
    chat_template_kwargs: Mapping[str, bool]
    answer_stops: tuple[str, ...]
    reasoning_mode: Literal["generic_think", "disabled"]
    reasoning_budget: int | None
    model_file_sha256: str
    runtime_probe: JsonObject | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chat_template_kwargs",
            MappingProxyType(dict(self.chat_template_kwargs)),
        )


@dataclass(frozen=True, slots=True)
class ExecutionContractContext:
    selection_policy_id: str
    selection_reason: str | None
    template_source: str
    raw_template_sha256: str | None
    model_file_sha256: str


@dataclass(frozen=True, slots=True)
class GgufCandidateUnresolvedError(RuntimeError):
    reason_code: str

    def __str__(self) -> str:
        return self.reason_code


@dataclass(frozen=True, slots=True)
class MissingExecutionContractError(RuntimeError):
    consumer: str

    def __str__(self) -> str:
        return f"{self.consumer} requires an execution contract resolved after artifact resolution"


@dataclass(frozen=True, slots=True)
class ExecutionContractArtifactMismatchError(RuntimeError):
    expected_sha256: str
    actual_sha256: str

    def __str__(self) -> str:
        return (
            "resolved execution contract model_file_sha256 does not match the served artifact: "
            f"contract={self.actual_sha256}, artifact={self.expected_sha256}"
        )


def gguf_contract_context(
    candidate: StaticProfileCandidate,
    *,
    model_file_sha256: str,
) -> ExecutionContractContext:
    match candidate.state:
        case "unresolved":
            raise GgufCandidateUnresolvedError(candidate.reason_code)
        case "thinking" | "nonthinking":
            pass
        case unreachable:
            assert_never(unreachable)
    match candidate.template_source:
        case "absent":
            template_source = "llama-builtin-chatml"
        case "gguf-default" | "gguf-tool-use-only":
            template_source = candidate.template_source
        case unreachable:
            assert_never(unreachable)
    return ExecutionContractContext(
        selection_policy_id=GGUF_EFFECTIVE_TEMPLATE_POLICY,
        selection_reason=candidate.reason_code,
        template_source=template_source,
        raw_template_sha256=candidate.template_sha256,
        model_file_sha256=model_file_sha256,
    )


def resolved_execution_contract(
    entry: ReasoningRegistryEntry,
    chat_template_kwargs: Mapping[str, bool],
    answer_stops: tuple[str, ...],
    context: ExecutionContractContext,
) -> ResolvedExecutionContract:
    is_answer_only = entry is ANSWER_ONLY_PROFILE
    return ResolvedExecutionContract(
        profile_id=entry.id,
        selection_policy_id=context.selection_policy_id,
        selection_reason=context.selection_reason or entry.id,
        template_source=context.template_source,
        raw_template_sha256=context.raw_template_sha256,
        effective_template_sha256=None,
        chat_template_kwargs=chat_template_kwargs,
        answer_stops=answer_stops,
        reasoning_mode="disabled" if is_answer_only else "generic_think",
        reasoning_budget=None if is_answer_only else CAPPED_THINKING_THINK_BUDGET,
        model_file_sha256=context.model_file_sha256,
        runtime_probe=None,
    )


def execution_contract_record(contract: ResolvedExecutionContract) -> JsonObject:
    return {
        "id": contract.profile_id,
        "selection_policy_id": contract.selection_policy_id,
        "selection_reason": contract.selection_reason,
        "template_source": contract.template_source,
        "raw_template_sha256": contract.raw_template_sha256,
        "effective_template_sha256": contract.effective_template_sha256,
        "chat_template_kwargs": dict(contract.chat_template_kwargs),
        "answer_stops": list(contract.answer_stops),
        "reasoning_mode": contract.reasoning_mode,
        "reasoning_budget": contract.reasoning_budget,
        "model_file_sha256": contract.model_file_sha256,
        "runtime_probe": contract.runtime_probe,
    }


def execution_profile_record(contract: ResolvedExecutionContract) -> JsonObject:
    template_sha256 = (
        contract.effective_template_sha256 or contract.raw_template_sha256
    )
    prompt_renderer_engine = (
        "transformers.apply_chat_template"
        if contract.template_source == "hf-chat-template"
        else "llama.cpp.apply-template"
    )
    runtime_probe_passed = (
        contract.runtime_probe is not None
        and contract.runtime_probe.get("passed") is True
    )
    return {
        "id": contract.profile_id,
        "selection_policy_id": contract.selection_policy_id,
        "selection_reason": contract.selection_reason,
        "template_source": contract.template_source,
        "template_sha256": template_sha256,
        "chat_template_kwargs": dict(contract.chat_template_kwargs),
        "answer_stops": list(contract.answer_stops),
        "runtime_probe_passed": runtime_probe_passed,
        "prompt_renderer_engine": prompt_renderer_engine,
    }


def structured_execution_profile(value: JsonValue) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    if not all(field in value for field in _PUBLIC_EXECUTION_PROFILE_FIELDS):
        return None
    return {field: value[field] for field in _PUBLIC_EXECUTION_PROFILE_FIELDS}


def execution_contract_notice(contract: ResolvedExecutionContract) -> str:
    template_sha256 = (
        contract.effective_template_sha256 or contract.raw_template_sha256
    )
    return (
        f"execution_profile={contract.profile_id} "
        f"selection_reason={contract.selection_reason} "
        f"template_sha256={template_sha256[:12] if template_sha256 else 'none'}"
    )


def execution_contract_resume_identity(contract: ResolvedExecutionContract) -> str:
    payload = json.dumps(
        execution_contract_record(contract),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
