from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final, Literal

from localbench._types import JsonObject
from localbench.budget_forcing import ForcingFormat
from localbench.execution_contract import (
    ExecutionContractContext,
    GGUF_EFFECTIVE_TEMPLATE_POLICY,
    GgufCandidateUnresolvedError,
    HF_CANONICAL_TEMPLATE_POLICY,
    ResolvedExecutionContract,
    gguf_contract_context,
    resolved_execution_contract,
)
from localbench.gguf_template import (
    LLAMA_BUILTIN_CHATML_NONTHINKING,
    StaticProfileCandidate,
    load_gguf_template_facade,
    static_profile_candidate,
)
from localbench.prompt_rendering import (
    HfChatPromptRenderer,
    LlamaApplyTemplatePromptRenderer,
    PromptRenderer,
    TemplateIntrospection,
    chat_template_sha256,
    derive_template_introspection,
    load_hf_chat_template_tokenizer,
)
from localbench.reasoning_registry import (
    ANSWER_ONLY_PROFILE,
    GEMMA4_CHANNEL_32768_PROFILE,
    GEMMA4_CHANNEL_PROFILE,
    GENERIC_THINK_TAGS_32768_PROFILE,
    GENERIC_THINK_TAGS_PROFILE,
    ReasoningRegistryEntry,
)

BoundedFinalProfileChoice = Literal[
    "auto",
    "answer_only_v1",
    "generic_think_tags_32768_v1",
    "generic_think_tags_8192_v1",
    "gemma4_channel_32768_v1",
    "gemma4_channel_8192_v1",
]
BOUNDED_FINAL_PROFILE_CHOICES: Final[tuple[BoundedFinalProfileChoice, ...]] = (
    "auto",
    "answer_only_v1",
    "generic_think_tags_32768_v1",
    "generic_think_tags_8192_v1",
    "gemma4_channel_32768_v1",
    "gemma4_channel_8192_v1",
)


@dataclass(frozen=True, slots=True)
class BoundedFinalProfileRuntime:
    entry: ReasoningRegistryEntry
    forcing: ForcingFormat | None
    prompt_renderer: PromptRenderer | None
    contract: ResolvedExecutionContract
    prompt_renderer_manifest: JsonObject | None = None

    def __post_init__(self) -> None:
        forcing = self.forcing
        if forcing is not None:
            forcing = replace(
                forcing,
                answer_stop=(
                    forcing.answer_stop
                    if forcing.answer_stop
                    else self.contract.answer_stops
                ),
                execution_contract=self.contract,
            )
        if forcing is not self.forcing:
            object.__setattr__(
                self,
                "forcing",
                forcing,
            )

    @property
    def answer_stop(self) -> tuple[str, ...]:
        return self.contract.answer_stops

    @property
    def chat_template_kwargs(self) -> Mapping[str, bool]:
        return self.contract.chat_template_kwargs


@dataclass(frozen=True, slots=True)
class UnsupportedBoundedFinalProfileError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class BoundedFinalProfileRequest:
    profile: BoundedFinalProfileChoice
    hf_model_id: str | None
    hf_revision: str | None = None
    model_file_sha256: str = ""
    gguf_metadata: JsonObject | None = None
    gguf_repo_only: bool = False
    llama_apply_template_base_url: str | None = None
    llama_api_key: str | None = None


def _with_llama_apply_template_renderer(
    runtime: BoundedFinalProfileRuntime,
    *,
    base_url: str,
    api_key: str,
    template: str,
    raw_template_sha256: str,
) -> BoundedFinalProfileRuntime:
    renderer = LlamaApplyTemplatePromptRenderer(
        base_url=base_url,
        api_key=api_key,
        template=template,
        contract_raw_template_sha256=raw_template_sha256,
        chat_template_kwargs=runtime.chat_template_kwargs,
    )
    manifest: JsonObject = {
        "source": "llama.cpp/apply-template",
        "chat_template_sha256": raw_template_sha256,
        "answer_stop": list(runtime.answer_stop),
        "template_kwargs": dict(runtime.chat_template_kwargs),
    }
    return replace(
        runtime,
        prompt_renderer=renderer,
        prompt_renderer_manifest=manifest,
    )


def _answer_only_runtime(
    answer_stop: tuple[str, ...],
    context: ExecutionContractContext,
    chat_template_kwargs: Mapping[str, bool] | None = None,
) -> BoundedFinalProfileRuntime:
    return BoundedFinalProfileRuntime(
        entry=ANSWER_ONLY_PROFILE,
        forcing=None,
        prompt_renderer=None,
        contract=resolved_execution_contract(
            ANSWER_ONLY_PROFILE,
            (
                {"enable_thinking": False}
                if chat_template_kwargs is None
                else chat_template_kwargs
            ),
            answer_stop,
            context,
        ),
        prompt_renderer_manifest=None,
    )


def _generic_runtime(
    entry: ReasoningRegistryEntry,
    introspection: TemplateIntrospection,
    prompt_renderer: PromptRenderer | None,
    prompt_renderer_manifest: JsonObject | None,
    context: ExecutionContractContext,
) -> BoundedFinalProfileRuntime:
    return BoundedFinalProfileRuntime(
        entry=entry,
        forcing=entry.forcing,
        prompt_renderer=prompt_renderer,
        contract=resolved_execution_contract(
            entry,
            introspection.chat_template_kwargs,
            introspection.answer_stop,
            context,
        ),
        prompt_renderer_manifest=prompt_renderer_manifest,
    )


def _gemma_runtime(
    entry: ReasoningRegistryEntry,
    introspection: TemplateIntrospection,
    prompt_renderer: PromptRenderer | None,
    prompt_renderer_manifest: JsonObject | None,
    context: ExecutionContractContext,
) -> BoundedFinalProfileRuntime:
    answer_stop = (
        entry.forcing.answer_stop
        if entry.forcing is not None
        else ()
    )
    return BoundedFinalProfileRuntime(
        entry=entry,
        forcing=entry.forcing,
        prompt_renderer=prompt_renderer,
        contract=resolved_execution_contract(
            entry,
            introspection.chat_template_kwargs,
            answer_stop,
            context,
        ),
        prompt_renderer_manifest=prompt_renderer_manifest,
    )


def resolve_bounded_final_profile(
    request: BoundedFinalProfileRequest,
) -> BoundedFinalProfileRuntime:
    if request.hf_model_id is None:
        if request.gguf_metadata is not None:
            return _resolve_gguf_profile(request, static_profile_candidate(request.gguf_metadata))
        if request.profile == "answer_only_v1":
            return _answer_only_runtime(
                (),
                ExecutionContractContext(
                    selection_policy_id=GGUF_EFFECTIVE_TEMPLATE_POLICY,
                    selection_reason=ANSWER_ONLY_PROFILE.id,
                    template_source="llama-builtin-chatml",
                    raw_template_sha256=None,
                    model_file_sha256=request.model_file_sha256,
                ),
            )
        if request.profile == "auto" and not request.gguf_repo_only:
            return _answer_only_runtime(
                (),
                ExecutionContractContext(
                    selection_policy_id=GGUF_EFFECTIVE_TEMPLATE_POLICY,
                    selection_reason=LLAMA_BUILTIN_CHATML_NONTHINKING,
                    template_source="llama-builtin-chatml",
                    raw_template_sha256=None,
                    model_file_sha256=request.model_file_sha256,
                ),
            )
        raise _unsupported(
            request.profile,
            "GGUF template metadata is required when --gguf-repo-only is active",
        )
    activation = (
        "gemma4"
        if request.profile in {"gemma4_channel_32768_v1", "gemma4_channel_8192_v1"}
        else None
    )
    tokenizer = load_hf_chat_template_tokenizer(
        request.hf_model_id,
        activation,
        revision=request.hf_revision,
    )
    introspection = derive_template_introspection(tokenizer)
    template_sha256 = chat_template_sha256(tokenizer)
    resolved = resolve_bounded_final_profile_from_introspection(
        request.profile,
        introspection,
        prompt_renderer_manifest={
            "source": "hf-chat-template",
            "hf_model_id": request.hf_model_id,
            "hf_revision": request.hf_revision,
            "chat_template_sha256": template_sha256,
            "answer_stop": list(introspection.answer_stop),
            "template_kwargs": dict(introspection.chat_template_kwargs),
        },
        contract_context=ExecutionContractContext(
            selection_policy_id=HF_CANONICAL_TEMPLATE_POLICY,
            selection_reason=None,
            template_source="hf-chat-template",
            raw_template_sha256=template_sha256,
            model_file_sha256=request.model_file_sha256,
        ),
    )
    if resolved.entry is ANSWER_ONLY_PROFILE:
        return resolved
    return BoundedFinalProfileRuntime(
        entry=resolved.entry,
        forcing=resolved.forcing,
        prompt_renderer=HfChatPromptRenderer(
            tokenizer=tokenizer,
            activation=None,
            chat_template_kwargs=resolved.chat_template_kwargs,
            answer_stop=resolved.answer_stop,
        ),
        contract=resolved.contract,
        prompt_renderer_manifest=resolved.prompt_renderer_manifest,
    )


def resolve_bounded_final_profile_from_introspection(
    profile: BoundedFinalProfileChoice,
    introspection: TemplateIntrospection,
    *,
    prompt_renderer: PromptRenderer | None = None,
    prompt_renderer_manifest: JsonObject | None = None,
    contract_context: ExecutionContractContext | None = None,
) -> BoundedFinalProfileRuntime:
    context = contract_context or ExecutionContractContext(
        selection_policy_id=HF_CANONICAL_TEMPLATE_POLICY,
        selection_reason=None,
        template_source="hf-chat-template",
        raw_template_sha256=None,
        model_file_sha256="",
    )
    if profile == "answer_only_v1":
        return _answer_only_runtime(
            introspection.answer_stop,
            context,
            _deactivation_kwargs(introspection),
        )
    if profile == "auto":
        if introspection.supports_gemma_channel:
            return _gemma_runtime(
                GEMMA4_CHANNEL_32768_PROFILE,
                introspection,
                prompt_renderer,
                prompt_renderer_manifest,
                context,
            )
        if introspection.supports_generic_thinking:
            _require_answer_stop("generic_think_tags_32768_v1", introspection.answer_stop)
            return _generic_runtime(
                GENERIC_THINK_TAGS_32768_PROFILE,
                introspection,
                prompt_renderer,
                prompt_renderer_manifest,
                context,
            )
        return _answer_only_runtime(
            introspection.answer_stop,
            context,
            _deactivation_kwargs(introspection),
        )
    if profile == "generic_think_tags_8192_v1":
        if not introspection.supports_generic_thinking:
            raise _unsupported(profile, "the canonical chat template exposes no native think tags or thinking kwarg")
        _require_answer_stop("generic_think_tags_8192_v1", introspection.answer_stop)
        return _generic_runtime(
            GENERIC_THINK_TAGS_PROFILE,
            introspection,
            prompt_renderer,
            prompt_renderer_manifest,
            context,
        )
    if profile == "generic_think_tags_32768_v1":
        if not introspection.supports_generic_thinking:
            raise _unsupported(profile, "the canonical chat template exposes no native think tags or thinking kwarg")
        _require_answer_stop("generic_think_tags_32768_v1", introspection.answer_stop)
        return _generic_runtime(
            GENERIC_THINK_TAGS_32768_PROFILE,
            introspection,
            prompt_renderer,
            prompt_renderer_manifest,
            context,
        )
    if profile == "gemma4_channel_8192_v1":
        if not introspection.supports_gemma_channel:
            raise _unsupported(profile, "the canonical chat template exposes no Gemma channel tags")
        return _gemma_runtime(
            GEMMA4_CHANNEL_PROFILE,
            introspection,
            prompt_renderer,
            prompt_renderer_manifest,
            context,
        )
    if profile == "gemma4_channel_32768_v1":
        if not introspection.supports_gemma_channel:
            raise _unsupported(profile, "the canonical chat template exposes no Gemma channel tags")
        return _gemma_runtime(
            GEMMA4_CHANNEL_32768_PROFILE,
            introspection,
            prompt_renderer,
            prompt_renderer_manifest,
            context,
        )
    raise _unsupported(profile, "unknown bounded-final profile")


def _resolve_gguf_profile(
    request: BoundedFinalProfileRequest,
    candidate: StaticProfileCandidate,
) -> BoundedFinalProfileRuntime:
    if candidate.introspection is None:
        if (
            request.profile in {"auto", "answer_only_v1"}
            and candidate.reason_code == LLAMA_BUILTIN_CHATML_NONTHINKING
        ):
            return _answer_only_runtime(
                (),
                ExecutionContractContext(
                    selection_policy_id=GGUF_EFFECTIVE_TEMPLATE_POLICY,
                    selection_reason=LLAMA_BUILTIN_CHATML_NONTHINKING,
                    template_source="llama-builtin-chatml",
                    raw_template_sha256=None,
                    model_file_sha256=request.model_file_sha256,
                ),
            )
        raise _unsupported(request.profile, candidate.reason_code)
    try:
        context = gguf_contract_context(
            candidate,
            model_file_sha256=request.model_file_sha256,
        )
    except GgufCandidateUnresolvedError as error:
        raise _unsupported(request.profile, error.reason_code) from error
    resolved = resolve_bounded_final_profile_from_introspection(
        request.profile,
        candidate.introspection,
        contract_context=context,
    )
    if resolved.entry is ANSWER_ONLY_PROFILE:
        return resolved
    if request.llama_apply_template_base_url is None or request.llama_api_key is None:
        raise _unsupported(request.profile, "GGUF renderer requires a llama.cpp endpoint and API key")
    facade, _ = load_gguf_template_facade(request.gguf_metadata or {})
    if facade is None or resolved.contract.raw_template_sha256 is None:
        raise _unsupported(request.profile, "GGUF renderer requires a valid embedded template")
    return _with_llama_apply_template_renderer(
        resolved,
        base_url=request.llama_apply_template_base_url,
        api_key=request.llama_api_key,
        template=facade.chat_template,
        raw_template_sha256=resolved.contract.raw_template_sha256,
    )


def _deactivation_kwargs(
    introspection: TemplateIntrospection,
) -> dict[str, bool]:
    if not introspection.chat_template_kwargs:
        return {"enable_thinking": False}
    return {key: False for key in introspection.chat_template_kwargs}


def _require_answer_stop(profile: str, answer_stop: tuple[str, ...]) -> None:
    if not answer_stop:
        raise _unsupported(
            profile,
            "the canonical chat template did not expose an assistant-turn terminator",
        )
    if any("`" in stop for stop in answer_stop):
        raise _unsupported(
            profile,
            "the canonical chat template answer stop contains a backtick",
        )


def _unsupported(profile: str, reason: str) -> UnsupportedBoundedFinalProfileError:
    return UnsupportedBoundedFinalProfileError(
        f"bounded-final-v1 profile {profile!r} is unsupported for this model: {reason}. "
        "Use the ranked answer_only_v1 path, or pass --profile auto with a model whose "
        "canonical tokenizer/template advertises native thinking support.",
    )
