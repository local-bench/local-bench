from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, assert_never

from localbench._types import JsonObject, JsonValue
from localbench.execution_profile_semantics import (
    EXECUTION_PROFILE_SEMANTIC_FIELDS,
    InvalidExecutionProfileSemanticRecordError,
    MissingExecutionProfileBudgetError,
    execution_profile_semantic_payload as execution_profile_semantic_payload,
    optional_execution_profile_semantic_record,
    parse_semantic_budget_record,
    semantic_payload_for_budget,
    semantic_sha256_for_budget,
)
from localbench.gguf_template import StaticProfileCandidate
from localbench.reasoning_registry import (
    ANSWER_ONLY_PROFILE,
    ExecutionProfileBudget,
    GENERIC_THINK_TAGS_32768_PROFILE,
    ReasoningRegistryEntry,
    execution_profile_for_id,
)

HF_CANONICAL_TEMPLATE_POLICY: Final = "hf-canonical-template-v1"
GGUF_EFFECTIVE_TEMPLATE_POLICY: Final = "gguf-effective-template-v1"
HF_PROMPT_RENDERER_ENGINE: Final = "transformers-jinja/hf-chat-template"
LLAMA_PROMPT_RENDERER_ENGINE: Final = "llama.cpp/apply-template"
PROMPT_RENDERER_CONTRACT_VERSION: Final = "localbench.prompt-renderer.v1"
PROMPT_RENDERER_DETERMINISM_POLICY_VERSION: Final = (
    "localbench.ranked-template-determinism.v1"
)
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
_DEEP_BUDGET_PROFILE_ID: Final = "generic_think_tags_32768_v1"
PUBLIC_EXECUTION_PROFILE_V2: Final = "localbench.execution_profile.v2"


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
    prompt_renderer_engine: str
    prompt_renderer_contract_version: str
    prompt_renderer_context_sha256: str
    budget: ExecutionProfileBudget | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chat_template_kwargs",
            MappingProxyType(dict(self.chat_template_kwargs)),
        )

    @property
    def semantic_sha256(self) -> str:
        budget = self.budget
        if budget is None:
            raise MissingExecutionProfileBudgetError(self.profile_id)
        return semantic_sha256_for_budget(budget)


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
    prompt_renderer_engine = (
        HF_PROMPT_RENDERER_ENGINE
        if context.template_source == "hf-chat-template"
        else LLAMA_PROMPT_RENDERER_ENGINE
    )
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
        reasoning_budget=None if is_answer_only else entry.budget.static_think_tokens,
        model_file_sha256=context.model_file_sha256,
        runtime_probe=None,
        prompt_renderer_engine=prompt_renderer_engine,
        prompt_renderer_contract_version=PROMPT_RENDERER_CONTRACT_VERSION,
        prompt_renderer_context_sha256=prompt_renderer_context_sha256(
            raw_template_sha256=context.raw_template_sha256,
            chat_template_kwargs=chat_template_kwargs,
        ),
        budget=entry.budget,
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
        "prompt_renderer_engine": contract.prompt_renderer_engine,
        "prompt_renderer_contract_version": contract.prompt_renderer_contract_version,
        "prompt_renderer_context_sha256": contract.prompt_renderer_context_sha256,
        **optional_execution_profile_semantic_record(contract),
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
    profile: JsonObject = {
        "id": contract.profile_id,
        "selection_policy_id": contract.selection_policy_id,
        "selection_reason": contract.selection_reason,
        "template_source": contract.template_source,
        "template_sha256": template_sha256,
        "chat_template_kwargs": dict(contract.chat_template_kwargs),
        "answer_stops": list(contract.answer_stops),
        "runtime_probe_passed": runtime_probe_passed,
        "prompt_renderer_engine": prompt_renderer_engine,
        **optional_execution_profile_semantic_record(contract),
    }
    if contract.profile_id == _DEEP_BUDGET_PROFILE_ID:
        profile["schema_version"] = PUBLIC_EXECUTION_PROFILE_V2
    return profile


def structured_execution_profile(value: JsonValue) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    if value.get("id") == _DEEP_BUDGET_PROFILE_ID:
        for field in _PUBLIC_EXECUTION_PROFILE_FIELDS:
            if field not in value:
                raise InvalidExecutionProfileSemanticRecordError(
                    field,
                    f"is required for {_DEEP_BUDGET_PROFILE_ID}",
                )
    if not all(field in value for field in _PUBLIC_EXECUTION_PROFILE_FIELDS):
        return None
    profile = {field: value[field] for field in _PUBLIC_EXECUTION_PROFILE_FIELDS}
    if profile["id"] != _DEEP_BUDGET_PROFILE_ID:
        return {**profile, **_trusted_legacy_semantic_record(value)}
    if value.get("schema_version") != PUBLIC_EXECUTION_PROFILE_V2:
        raise InvalidExecutionProfileSemanticRecordError(
            "schema_version",
            f"must equal {PUBLIC_EXECUTION_PROFILE_V2!r} for {_DEEP_BUDGET_PROFILE_ID}",
        )
    parsed_budget = parse_semantic_budget_record(value)
    expected_payload = semantic_payload_for_budget(
        GENERIC_THINK_TAGS_32768_PROFILE.budget
    )
    parsed_payload = semantic_payload_for_budget(parsed_budget)
    for field in EXECUTION_PROFILE_SEMANTIC_FIELDS:
        if parsed_payload[field] != expected_payload[field]:
            raise InvalidExecutionProfileSemanticRecordError(
                field,
                f"does not match the frozen {_DEEP_BUDGET_PROFILE_ID} tuple",
            )
    return {
        **profile,
        "schema_version": PUBLIC_EXECUTION_PROFILE_V2,
        **{
            field: value[field]
            for field in (*EXECUTION_PROFILE_SEMANTIC_FIELDS, "semantic_sha256")
        },
    }


def _trusted_legacy_semantic_record(value: JsonObject) -> JsonObject:
    semantic_fields = (*EXECUTION_PROFILE_SEMANTIC_FIELDS, "semantic_sha256")
    if not all(field in value for field in semantic_fields):
        return {}
    profile_id = value.get("id")
    if not isinstance(profile_id, str):
        return {}
    canonical_entry = execution_profile_for_id(profile_id)
    if canonical_entry is None:
        return {}
    canonical_payload = semantic_payload_for_budget(canonical_entry.budget)
    for field in EXECUTION_PROFILE_SEMANTIC_FIELDS:
        observed = value[field]
        expected = canonical_payload[field]
        if type(observed) is not type(expected) or observed != expected:
            return {}
    if value["semantic_sha256"] != semantic_sha256_for_budget(canonical_entry.budget):
        return {}
    return {field: value[field] for field in semantic_fields}


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


def prompt_renderer_context_sha256(
    *,
    raw_template_sha256: str | None,
    chat_template_kwargs: Mapping[str, bool],
) -> str:
    payload = json.dumps(
        {
            "add_generation_prompt": True,
            "chat_template_kwargs": dict(chat_template_kwargs),
            "determinism_policy_version": PROMPT_RENDERER_DETERMINISM_POLICY_VERSION,
            "raw_template_sha256": raw_template_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
