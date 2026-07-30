"""Chat-template prompt rendering for local capped-thinking forcing.

Generic GGUF profiles deliberately use llama.cpp's ``/apply-template`` as the
raw-prompt renderer. This keeps scoring on the pinned server's effective
renderer and avoids reimplementing its template wrapper and token namespace in
the client while preserving the existing two-pass forcing protocol.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol, assert_never

import httpx

from localbench._types import ChatMessage, JsonObject, JsonValue
from localbench.runtime_probe_evidence import apply_template_request

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
_LLAMA_APPLY_TEMPLATE_TIMEOUT: Final = httpx.Timeout(
    connect=5.0,
    read=30.0,
    write=10.0,
    pool=10.0,
)
_LLAMA_APPLY_TEMPLATE_LIMITS: Final = httpx.Limits(
    max_connections=8,
    max_keepalive_connections=4,
    keepalive_expiry=30.0,
)
_STRFTIME_NOW_PATTERN: Final = re.compile(r"\bstrftime_now\b")


@dataclass(frozen=True, slots=True)
class _OfflineTokenizerRequest:
    hf_model_id: str
    activation: ReasoningActivation | None
    revision: str | None


class PromptRenderingError(RuntimeError):
    """A chat-template renderer could not be constructed or applied."""


class TokenizerCacheMissError(PromptRenderingError):
    pass


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


@dataclass(frozen=True, slots=True)
class TemplateIntrospection:
    answer_stop: tuple[str, ...]
    chat_template_kwargs: Mapping[str, bool]
    supports_generic_thinking: bool
    supports_gemma_channel: bool


@dataclass(slots=True)
class HfChatPromptRenderer:
    """Render prompts with one HF tokenizer and cache repeated message sets."""

    tokenizer: ChatTemplateTokenizer
    activation: ReasoningActivation | None
    chat_template_kwargs: Mapping[str, bool] | None = None
    answer_stop: tuple[str, ...] = ()
    _cache: dict[str, str] = field(default_factory=dict)

    def render(self, messages: list[ChatMessage]) -> str:
        key = _messages_cache_key(messages)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rendered = render_hf_chat_prompt(
            messages,
            self.tokenizer,
            self.activation,
            chat_template_kwargs=self.chat_template_kwargs,
        )
        self._cache[key] = rendered
        return rendered


@dataclass(frozen=True, slots=True)
class LlamaApplyTemplatePromptRenderer:
    """Render generic GGUF prompts with the pinned llama.cpp server."""

    base_url: str
    api_key: str
    template: str
    contract_raw_template_sha256: str
    chat_template_kwargs: Mapping[str, bool]
    transport: httpx.BaseTransport | None = None
    _cache: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        actual_sha256 = hashlib.sha256(self.template.encode("utf-8")).hexdigest()
        if actual_sha256 != self.contract_raw_template_sha256:
            raise PromptRenderingError(
                "GGUF template sha256 does not match the resolved execution contract",
            )
        if _STRFTIME_NOW_PATTERN.search(self.template) is not None:
            raise PromptRenderingError(
                "ranked GGUF prompt rendering rejects undeclared external variable "
                "strftime_now because it is nondeterministic",
            )

    def render(
        self,
        messages: Sequence[Mapping[str, JsonValue]],
        *,
        tools: Sequence[JsonObject] | None = None,
        documents: Sequence[JsonObject] | None = None,
    ) -> str:
        if tools is not None:
            raise PromptRenderingError(
                "separate tools are unsupported by the GGUF prompt renderer",
            )
        if documents is not None:
            raise PromptRenderingError(
                "separate documents are unsupported by the GGUF prompt renderer",
            )
        key = _messages_cache_key(messages)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        payload = apply_template_request(messages, self.chat_template_kwargs)
        try:
            transport = self.transport or httpx.HTTPTransport(
                retries=3,
                limits=_LLAMA_APPLY_TEMPLATE_LIMITS,
            )
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=_LLAMA_APPLY_TEMPLATE_TIMEOUT,
                transport=transport,
                follow_redirects=True,
            ) as client:
                response = client.post("/apply-template", json=payload)
                response.raise_for_status()
                response_payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            raise PromptRenderingError(
                f"llama.cpp /apply-template request failed: {error}",
            ) from error
        rendered = _unbatch_apply_template_prompt(response_payload)
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
    return HfChatPromptRenderer(
        tokenizer=load_hf_chat_template_tokenizer(hf_model_id, activation),
        activation=activation,
    )


def load_hf_chat_template_tokenizer(
    hf_model_id: str,
    activation: ReasoningActivation | None = None,
    *,
    revision: str | None = None,
) -> ChatTemplateTokenizer:
    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        from transformers import AutoTokenizer

        tokenizer = _load_offline_tokenizer(
            AutoTokenizer,
            _OfflineTokenizerRequest(
                hf_model_id=hf_model_id,
                activation=activation,
                revision=revision,
            ),
        )
    except ImportError as exc:
        raise PromptRenderingError(
            "transformers is required when --hf-model-id is set; "
            "install localbench[hf] to enable Hugging Face chat-template rendering"
        ) from exc
    except (OSError, ValueError) as exc:
        tokenizer_ref = _tokenizer_ref(hf_model_id, revision)
        raise TokenizerCacheMissError(
            f"could not load tokenizer for {tokenizer_ref!r} from the offline HF cache. "
            "Template introspection is offline-only; pre-cache the tokenizer once with:\n"
            f'  hf download {hf_model_id} --include "*.json" '
            '--include "*.model" --include "*.jinja"\n'
            f"{_revision_cache_hint(revision)}"
            "(gated repos need `hf auth login` after accepting the license on huggingface.co)\n"
            "For `localbench bench` against a GGUF-only repo with no tokenizer files, "
            "declare --gguf-repo-only instead of --hf-model-id (basic identity, "
            "null template digests)."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - third-party tokenizer stacks raise freely
        tokenizer_ref = _tokenizer_ref(hf_model_id, revision)
        raise PromptRenderingError(
            f"could not introspect tokenizer for {tokenizer_ref!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline
    return tokenizer


def _load_offline_tokenizer(
    auto_tokenizer,
    request: _OfflineTokenizerRequest,
) -> ChatTemplateTokenizer:
    if request.activation != "gemma4" or request.hf_model_id != _GEMMA4_HF_MODEL_ID:
        return auto_tokenizer.from_pretrained(
            request.hf_model_id,
            local_files_only=True,
            revision=request.revision,
        )
    resolved_revision = request.revision or _GEMMA4_REVISION
    try:
        return auto_tokenizer.from_pretrained(
            request.hf_model_id,
            local_files_only=True,
            revision=resolved_revision,
        )
    except OSError:
        if request.revision is not None:
            raise
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


def _tokenizer_ref(hf_model_id: str, revision: str | None) -> str:
    if revision is None:
        return hf_model_id
    return f"{hf_model_id}@{revision}"


def _revision_cache_hint(revision: str | None) -> str:
    if revision is None:
        return ""
    return "A pinned revision was requested; ensure that exact repo@revision snapshot is cached.\n"


def render_hf_chat_prompt(
    messages: list[ChatMessage],
    tokenizer: ChatTemplateTokenizer,
    activation: ReasoningActivation | None,
    *,
    chat_template_kwargs: Mapping[str, bool] | None = None,
) -> str:
    """Render messages through the model's own tokenizer chat template."""
    rendered = tokenizer.apply_chat_template(
        _messages_for_activation(messages, activation) if activation is not None else _copy_messages(messages),
        tokenize=False,
        add_generation_prompt=True,
        **_resolved_chat_template_kwargs(activation, chat_template_kwargs),
    )
    if not isinstance(rendered, str):
        raise PromptRenderingError("chat template did not render to a string")
    return rendered


def derive_template_introspection(tokenizer: ChatTemplateTokenizer) -> TemplateIntrospection:
    template = _tokenizer_template(tokenizer)
    lowered = template.casefold()
    behavior = _generation_behavior(tokenizer)
    kwargs = _thinking_template_kwargs(lowered)
    supports_gemma_channel = (
        "<|channel>thought" in lowered
        or "<channel|>" in lowered
        or ("gemma" in behavior and "channel" in behavior)
    )
    supports_generic_thinking = (
        "<think" in lowered
        or "</think" in lowered
        or "think" in behavior
        or "reasoning" in behavior
        or (bool(kwargs) and not supports_gemma_channel)
    )
    return TemplateIntrospection(
        answer_stop=_derived_answer_stops(tokenizer, template),
        chat_template_kwargs=kwargs,
        supports_generic_thinking=supports_generic_thinking,
        supports_gemma_channel=supports_gemma_channel,
    )


def chat_template_sha256(tokenizer: ChatTemplateTokenizer) -> str | None:
    template = _tokenizer_template(tokenizer)
    if template == "":
        return None
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def _messages_for_activation(
    messages: list[ChatMessage],
    activation: ReasoningActivation,
) -> list[ChatMessage]:
    copied = _copy_messages(messages)
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


def _copy_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    return [{"role": message["role"], "content": message["content"]} for message in messages]


def _resolved_chat_template_kwargs(
    activation: ReasoningActivation | None,
    chat_template_kwargs: Mapping[str, bool] | None,
) -> dict[str, bool]:
    if chat_template_kwargs is not None:
        return dict(chat_template_kwargs)
    if activation is None:
        return {}
    return _chat_template_kwargs(activation)


def _tokenizer_template(tokenizer: ChatTemplateTokenizer) -> str:
    value = getattr(tokenizer, "chat_template", "")
    return value if isinstance(value, str) else ""


def _generation_behavior(tokenizer: ChatTemplateTokenizer) -> str:
    values: list[str] = [type(tokenizer).__name__]
    for attr in ("generation_behavior", "generation_behavior_class", "chat_template_behavior"):
        value = getattr(tokenizer, attr, None)
        if isinstance(value, str):
            values.append(value)
        elif value is not None:
            values.append(type(value).__name__)
    return " ".join(values).casefold()


def _thinking_template_kwargs(template: str) -> dict[str, bool]:
    if "enable_thinking" in template:
        return {"enable_thinking": True}
    if "thinking" in template:
        return {"thinking": True}
    return {}


def _derived_answer_stops(tokenizer: ChatTemplateTokenizer, template: str) -> tuple[str, ...]:
    stops: list[str] = []
    for attr in ("eot_token", "eos_token"):
        value = getattr(tokenizer, attr, None)
        if isinstance(value, str) and value and (template == "" or value in template):
            stops.append(value)
    return tuple(dict.fromkeys(stops))


def _messages_cache_key(messages: Sequence[Mapping[str, JsonValue]]) -> str:
    return json.dumps(
        messages,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _unbatch_apply_template_prompt(payload: JsonValue) -> str:
    if isinstance(payload, dict):
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            return prompt
        if (
            isinstance(prompt, list)
            and len(prompt) == 1
            and isinstance(prompt[0], str)
        ):
            return prompt[0]
    raise PromptRenderingError(
        "llama.cpp /apply-template response must contain exactly one string prompt",
    )
