"""Chat-template prompt rendering for local capped-thinking forcing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, assert_never

from localbench._types import ChatMessage

ReasoningActivation = Literal["qwen3", "granite", "nemotron", "r1", "gemma4"]
REASONING_ACTIVATIONS: Final[tuple[ReasoningActivation, ...]] = (
    "qwen3",
    "granite",
    "nemotron",
    "r1",
    "gemma4",
)
_NEMOTRON_SYSTEM_MESSAGE: Final[ChatMessage] = {
    "role": "system",
    "content": "detailed thinking on",
}
_GEMMA4_HF_MODEL_ID: Final = "unsloth/gemma-4-31B-it"
_GEMMA4_REVISION: Final = "a1c85d1c2db7dcd15c41ad4082955240a9465743"


class PromptRenderingError(RuntimeError):
    """A chat-template renderer could not be constructed or applied."""


class PromptRenderer(Protocol):
    def render(self, messages: list[ChatMessage]) -> str:
        """Render chat messages to a raw generation prompt."""


class ChatTemplateTokenizer(Protocol):
    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: Literal[False],
        add_generation_prompt: bool,
        **kwargs: bool,
    ) -> str:
        """Return the rendered chat template string."""


@dataclass(slots=True)
class HfChatPromptRenderer:
    """Render prompts with one HF tokenizer and cache repeated message sets."""

    tokenizer: ChatTemplateTokenizer
    activation: ReasoningActivation
    _cache: dict[str, str] = field(default_factory=dict)

    def render(self, messages: list[ChatMessage]) -> str:
        key = _messages_cache_key(messages)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rendered = render_hf_chat_prompt(messages, self.tokenizer, self.activation)
        self._cache[key] = rendered
        return rendered


def build_forced_prompt_renderer(
    hf_model_id: str | None,
    activation: ReasoningActivation,
) -> PromptRenderer | None:
    """Build the optional off-family renderer for local capped-thinking runs."""
    if hf_model_id is None:
        return None
    return load_hf_chat_prompt_renderer(hf_model_id, activation)


def load_hf_chat_prompt_renderer(
    hf_model_id: str,
    activation: ReasoningActivation,
) -> HfChatPromptRenderer:
    """Load a Hugging Face tokenizer from the offline cache."""
    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        from transformers import AutoTokenizer

        tokenizer = _load_offline_tokenizer(AutoTokenizer, hf_model_id, activation)
    except ImportError as exc:
        raise PromptRenderingError(
            "transformers is required when --hf-model-id is set; "
            "install localbench[hf] to enable Hugging Face chat-template rendering"
        ) from exc
    except (OSError, ValueError) as exc:
        raise PromptRenderingError(
            f"could not load tokenizer for {hf_model_id!r} from the offline HF cache"
        ) from exc
    finally:
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline
    return HfChatPromptRenderer(tokenizer=tokenizer, activation=activation)


def _load_offline_tokenizer(
    auto_tokenizer,
    hf_model_id: str,
    activation: ReasoningActivation,
):
    if activation != "gemma4" or hf_model_id != _GEMMA4_HF_MODEL_ID:
        return auto_tokenizer.from_pretrained(hf_model_id, local_files_only=True)
    try:
        return auto_tokenizer.from_pretrained(
            hf_model_id,
            local_files_only=True,
            revision=_GEMMA4_REVISION,
        )
    except OSError:
        snapshot = (
            Path.home()
            / ".cache"
            / "huggingface"
            / "hub"
            / "models--unsloth--gemma-4-31B-it"
            / "snapshots"
            / _GEMMA4_REVISION
        )
        return auto_tokenizer.from_pretrained(snapshot, local_files_only=True)


def render_hf_chat_prompt(
    messages: list[ChatMessage],
    tokenizer: ChatTemplateTokenizer,
    activation: ReasoningActivation,
) -> str:
    """Render messages through the model's own tokenizer chat template."""
    rendered = tokenizer.apply_chat_template(
        _messages_for_activation(messages, activation),
        tokenize=False,
        add_generation_prompt=True,
        **_chat_template_kwargs(activation),
    )
    if not isinstance(rendered, str):
        raise PromptRenderingError("chat template did not render to a string")
    return rendered


def _messages_for_activation(
    messages: list[ChatMessage],
    activation: ReasoningActivation,
) -> list[ChatMessage]:
    copied: list[ChatMessage] = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
    ]
    match activation:
        case "nemotron":
            if any(message["role"] == "system" for message in copied):
                return copied
            system_message: ChatMessage = {
                "role": _NEMOTRON_SYSTEM_MESSAGE["role"],
                "content": _NEMOTRON_SYSTEM_MESSAGE["content"],
            }
            return [system_message, *copied]
        case "qwen3" | "granite" | "r1" | "gemma4":
            return copied
        case unreachable:
            assert_never(unreachable)


def _chat_template_kwargs(activation: ReasoningActivation) -> dict[str, bool]:
    match activation:
        case "granite":
            return {"thinking": True}
        case "gemma4":
            return {"enable_thinking": True}
        case "qwen3" | "nemotron" | "r1":
            return {}
        case unreachable:
            assert_never(unreachable)


def _messages_cache_key(messages: list[ChatMessage]) -> str:
    return json.dumps(messages, sort_keys=True, separators=(",", ":"))
