from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from localbench._types import JsonObject
from localbench.budget_forcing import ForcingFormat
from localbench.execution_contract import (
    ExecutionContractContext,
    ResolvedExecutionContract,
    resolved_execution_contract,
)
from localbench.prompt_rendering import PromptRenderer, TemplateIntrospection
from localbench.reasoning_registry import (
    ANSWER_ONLY_PROFILE,
    GEMMA4_CHANNEL_PROFILE,
    GENERIC_THINK_TAGS_PROFILE,
    ReasoningRegistryEntry,
)


@dataclass(frozen=True, slots=True)
class BoundedFinalProfileRuntime:
    entry: ReasoningRegistryEntry
    forcing: ForcingFormat | None
    prompt_renderer: PromptRenderer | None
    contract: ResolvedExecutionContract
    prompt_renderer_manifest: JsonObject | None = None

    def __post_init__(self) -> None:
        if self.forcing is not None and not self.forcing.answer_stop and self.contract.answer_stops:
            object.__setattr__(
                self,
                "forcing",
                replace(self.forcing, answer_stop=self.contract.answer_stops),
            )

    @property
    def answer_stop(self) -> tuple[str, ...]:
        return self.contract.answer_stops

    @property
    def chat_template_kwargs(self) -> Mapping[str, bool]:
        return self.contract.chat_template_kwargs


def answer_only_runtime(
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


def generic_runtime(
    introspection: TemplateIntrospection,
    prompt_renderer: PromptRenderer | None,
    prompt_renderer_manifest: JsonObject | None,
    context: ExecutionContractContext,
) -> BoundedFinalProfileRuntime:
    return BoundedFinalProfileRuntime(
        entry=GENERIC_THINK_TAGS_PROFILE,
        forcing=GENERIC_THINK_TAGS_PROFILE.forcing,
        prompt_renderer=prompt_renderer,
        contract=resolved_execution_contract(
            GENERIC_THINK_TAGS_PROFILE,
            introspection.chat_template_kwargs,
            introspection.answer_stop,
            context,
        ),
        prompt_renderer_manifest=prompt_renderer_manifest,
    )


def gemma_runtime(
    introspection: TemplateIntrospection,
    prompt_renderer: PromptRenderer | None,
    prompt_renderer_manifest: JsonObject | None,
    context: ExecutionContractContext,
) -> BoundedFinalProfileRuntime:
    answer_stop = (
        GEMMA4_CHANNEL_PROFILE.forcing.answer_stop
        if GEMMA4_CHANNEL_PROFILE.forcing is not None
        else ()
    )
    return BoundedFinalProfileRuntime(
        entry=GEMMA4_CHANNEL_PROFILE,
        forcing=GEMMA4_CHANNEL_PROFILE.forcing,
        prompt_renderer=prompt_renderer,
        contract=resolved_execution_contract(
            GEMMA4_CHANNEL_PROFILE,
            introspection.chat_template_kwargs,
            answer_stop,
            context,
        ),
        prompt_renderer_manifest=prompt_renderer_manifest,
    )
