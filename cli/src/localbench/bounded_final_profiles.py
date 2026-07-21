from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final, Literal

from localbench._types import JsonObject
from localbench.budget_forcing import ForcingFormat
from localbench.prompt_rendering import (
    HfChatPromptRenderer,
    PromptRenderer,
    TemplateIntrospection,
    chat_template_sha256,
    derive_template_introspection,
    load_hf_chat_template_tokenizer,
)
from localbench.reasoning_registry import (
    ANSWER_ONLY_PROFILE,
    GEMMA4_CHANNEL_PROFILE,
    GENERIC_THINK_TAGS_PROFILE,
    ReasoningRegistryEntry,
)

BoundedFinalProfileChoice = Literal[
    "auto",
    "answer_only_v1",
    "generic_think_tags_8192_v1",
    "gemma4_channel_8192_v1",
]
BOUNDED_FINAL_PROFILE_CHOICES: Final[tuple[BoundedFinalProfileChoice, ...]] = (
    "auto",
    "answer_only_v1",
    "generic_think_tags_8192_v1",
    "gemma4_channel_8192_v1",
)


@dataclass(frozen=True, slots=True)
class UnsupportedBoundedFinalProfileError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class BoundedFinalProfileRuntime:
    entry: ReasoningRegistryEntry
    forcing: ForcingFormat | None
    prompt_renderer: PromptRenderer | None
    answer_stop: tuple[str, ...]
    chat_template_kwargs: Mapping[str, bool]
    prompt_renderer_manifest: JsonObject | None = None

    def __post_init__(self) -> None:
        if self.forcing is not None and not self.forcing.answer_stop and self.answer_stop:
            object.__setattr__(
                self,
                "forcing",
                replace(self.forcing, answer_stop=self.answer_stop),
            )


@dataclass(frozen=True, slots=True)
class BoundedFinalProfileRequest:
    profile: BoundedFinalProfileChoice
    hf_model_id: str | None
    hf_revision: str | None = None


def resolve_bounded_final_profile(
    request: BoundedFinalProfileRequest,
) -> BoundedFinalProfileRuntime:
    if request.profile == "answer_only_v1":
        return _answer_only_runtime(())
    if request.profile == "auto" and request.hf_model_id is None:
        return _answer_only_runtime(())
    if request.hf_model_id is None:
        raise _unsupported(
            request.profile,
            "no --hf-model-id was supplied, so the canonical chat template cannot be inspected",
        )
    activation = "gemma4" if request.profile == "gemma4_channel_8192_v1" else None
    tokenizer = load_hf_chat_template_tokenizer(
        request.hf_model_id,
        activation,
        revision=request.hf_revision,
    )
    introspection = derive_template_introspection(tokenizer)
    resolved = resolve_bounded_final_profile_from_introspection(
        request.profile,
        introspection,
        prompt_renderer_manifest={
            "source": "hf-chat-template",
            "hf_model_id": request.hf_model_id,
            "hf_revision": request.hf_revision,
            "chat_template_sha256": chat_template_sha256(tokenizer),
            "answer_stop": list(introspection.answer_stop),
            "template_kwargs": dict(introspection.chat_template_kwargs),
        },
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
        answer_stop=resolved.answer_stop,
        chat_template_kwargs=resolved.chat_template_kwargs,
        prompt_renderer_manifest=resolved.prompt_renderer_manifest,
    )


def resolve_bounded_final_profile_from_introspection(
    profile: BoundedFinalProfileChoice,
    introspection: TemplateIntrospection,
    *,
    prompt_renderer: PromptRenderer | None = None,
    prompt_renderer_manifest: JsonObject | None = None,
) -> BoundedFinalProfileRuntime:
    if profile == "answer_only_v1":
        return _answer_only_runtime(introspection.answer_stop)
    if profile == "auto":
        if introspection.supports_gemma_channel:
            return _gemma_runtime(introspection, prompt_renderer, prompt_renderer_manifest)
        if introspection.supports_generic_thinking:
            return _generic_runtime(introspection, prompt_renderer, prompt_renderer_manifest)
        return _answer_only_runtime(introspection.answer_stop)
    if profile == "generic_think_tags_8192_v1":
        if not introspection.supports_generic_thinking:
            raise _unsupported(profile, "the canonical chat template exposes no native think tags or thinking kwarg")
        return _generic_runtime(introspection, prompt_renderer, prompt_renderer_manifest)
    if profile == "gemma4_channel_8192_v1":
        if not introspection.supports_gemma_channel:
            raise _unsupported(profile, "the canonical chat template exposes no Gemma channel tags")
        return _gemma_runtime(introspection, prompt_renderer, prompt_renderer_manifest)
    raise _unsupported(profile, "unknown bounded-final profile")


def _answer_only_runtime(answer_stop: tuple[str, ...]) -> BoundedFinalProfileRuntime:
    return BoundedFinalProfileRuntime(
        entry=ANSWER_ONLY_PROFILE,
        forcing=None,
        prompt_renderer=None,
        answer_stop=answer_stop,
        chat_template_kwargs={"enable_thinking": False},
        prompt_renderer_manifest=None,
    )


def _generic_runtime(
    introspection: TemplateIntrospection,
    prompt_renderer: PromptRenderer | None,
    prompt_renderer_manifest: JsonObject | None,
) -> BoundedFinalProfileRuntime:
    _require_answer_stop("generic_think_tags_8192_v1", introspection.answer_stop)
    return BoundedFinalProfileRuntime(
        entry=GENERIC_THINK_TAGS_PROFILE,
        forcing=GENERIC_THINK_TAGS_PROFILE.forcing,
        prompt_renderer=prompt_renderer,
        answer_stop=introspection.answer_stop,
        chat_template_kwargs=dict(introspection.chat_template_kwargs),
        prompt_renderer_manifest=prompt_renderer_manifest,
    )


def _gemma_runtime(
    introspection: TemplateIntrospection,
    prompt_renderer: PromptRenderer | None,
    prompt_renderer_manifest: JsonObject | None,
) -> BoundedFinalProfileRuntime:
    answer_stop = GEMMA4_CHANNEL_PROFILE.forcing.answer_stop if GEMMA4_CHANNEL_PROFILE.forcing is not None else ()
    _require_answer_stop("gemma4_channel_8192_v1", answer_stop)
    return BoundedFinalProfileRuntime(
        entry=GEMMA4_CHANNEL_PROFILE,
        forcing=GEMMA4_CHANNEL_PROFILE.forcing,
        prompt_renderer=prompt_renderer,
        answer_stop=answer_stop,
        chat_template_kwargs=dict(introspection.chat_template_kwargs),
        prompt_renderer_manifest=prompt_renderer_manifest,
    )


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
