"""Native reasoning-mode registry entries for ranked local lanes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from typing import Final, Literal, Mapping, assert_never

from localbench._types import JsonValue
from localbench.budget_forcing import GEMMA4_FORCING, QWEN_FORCING, ForcingFormat
from localbench.prompt_rendering import ReasoningActivation
from localbench.reasoning_leaks import CANONICAL_REASONING_LEAK_REGEXES

ReasoningRegistryStatus = Literal["ranked", "diagnostic", "experimental"]
ContextFitPolicy = Literal["exact-or-fail"]
ContextExtensionPolicy = Literal["none"]
KvCacheDtype = Literal["f16"]

GEMMA4_LEAK_REGEXES: Final[tuple[str, ...]] = (
    r"<\|channel>",
    r"<channel\|>",
    r"<\|think\|>",
    r"<turn\|>",
)


@dataclass(frozen=True, slots=True)
class ExecutionProfileBudget:
    static_think_tokens: int
    static_final_tokens: int
    static_max_generated_tokens: int
    server_context_tokens: int
    agentic_max_turns: int
    agentic_max_output_tokens_per_turn: int
    agentic_max_generated_tokens_per_task: int
    agentic_context_tokens: int
    kv_cache_k_dtype: KvCacheDtype
    kv_cache_v_dtype: KvCacheDtype
    context_fit_policy: ContextFitPolicy
    context_extension_policy: ContextExtensionPolicy
    per_task_timeout_s: int


@dataclass(frozen=True, slots=True)
class ReasoningRegistryEntry:
    """Frozen identity for one native reasoning operating mode."""

    id: str
    version: str
    status: ReasoningRegistryStatus
    model_match: tuple[str, ...]
    activation: Mapping[str, JsonValue]
    forcing: ForcingFormat | None
    parser: Mapping[str, JsonValue]
    conformance: Mapping[str, JsonValue]
    provenance: Mapping[str, JsonValue]
    budget: ExecutionProfileBudget


_LEGACY_PROFILE_BUDGET: Final = ExecutionProfileBudget(
    static_think_tokens=8192,
    static_final_tokens=8192,
    static_max_generated_tokens=16384,
    server_context_tokens=32768,
    agentic_max_turns=24,
    agentic_max_output_tokens_per_turn=1024,
    agentic_max_generated_tokens_per_task=32768,
    agentic_context_tokens=32768,
    kv_cache_k_dtype="f16",
    kv_cache_v_dtype="f16",
    context_fit_policy="exact-or-fail",
    context_extension_policy="none",
    per_task_timeout_s=1800,
)


QWEN_REASONING_ENTRY: Final = ReasoningRegistryEntry(
    id="qwen_thinking_native_v1",
    version="1",
    status="ranked",
    model_match=("qwen3", "qwen", "qwen3-*"),
    activation={
        "method": "native_chatml_default",
        "reasoning_activation": "qwen3",
        "chat_template_kwargs": {},
        "system_prompt_injection": False,
    },
    forcing=QWEN_FORCING,
    parser={
        "reasoning_close": "</think>",
        "answer_reparse": "split_on_final_reasoning_close",
        "reasoning_parser": "qwen3",
    },
    conformance={
        "lane": "capped-thinking",
        "think_budget": 8192,
        "answer_budget": "max(max_tokens - think_budget, 1024)",
        "qwen_byte_equivalent_required": True,
    },
    provenance={
        "source": "existing localbench Qwen3 capped-thinking two-pass forcing behavior",
        "renderer": "render_qwen3_chat_prompt",
        "answer_stop": ("<|im_end|>",),
    },
    budget=_LEGACY_PROFILE_BUDGET,
)

GEMMA4_REASONING_ENTRY: Final = ReasoningRegistryEntry(
    id="gemma4_thinking_native_v1",
    version="1",
    status="ranked",
    model_match=("unsloth/gemma-4-31B-it", "gemma-4", "gemma4"),
    activation={
        "method": "chat_template_kwargs",
        "reasoning_activation": "gemma4",
        "chat_template_kwargs": {"enable_thinking": True},
        "system_prompt_injection": False,
    },
    forcing=GEMMA4_FORCING,
    parser={
        "reasoning_open": "<|channel>thought\n",
        "reasoning_close": "<channel|>",
        "answer_reparse_regex": r"(?s)<\|channel>thought\n(.*?)<channel\|>",
    },
    conformance={
        "lane": "capped-thinking",
        "leak_regexes": GEMMA4_LEAK_REGEXES,
        "static_render_requires": (
            "enable_thinking",
            "<|turn>",
            "<turn|>",
            "single_bos",
            "no_empty_preclosed_thought_channel",
        ),
    },
    provenance={
        "hf_model_id": "unsloth/gemma-4-31B-it",
        "revision": "a1c85d1c2db7dcd15c41ad4082955240a9465743",
        "chat_template_sha256": "94899c0f917d93f6fe81c95744d1e8ddab2d21d39228d2e4aec1fb2a25bff413",
        "eot_token": "<turn|>",
        "eos_token": "<turn|>",
        "answer_stop": ("<turn|>",),
        "template_confirmed": "contains enable_thinking + channel/think tags",
    },
    budget=_LEGACY_PROFILE_BUDGET,
)

ANSWER_ONLY_PROFILE: Final = ReasoningRegistryEntry(
    id="answer_only_v1",
    version="1",
    status="ranked",
    model_match=("*",),
    activation={
        "method": "chat_template_kwargs_when_supported",
        "chat_template_kwargs": {"enable_thinking": False},
        "system_prompt_injection": False,
    },
    forcing=None,
    parser={
        "reasoning_mode": "disabled",
        "reasoning_tokens": 0,
        "scored_text": "final_text_only",
    },
    conformance={
        "lane": "bounded-final-v1",
        "single_pass": True,
        "max_tokens": "suite item max_tokens",
        "stops": "canonical tokenizer/template EOS/EOT only",
    },
    provenance={
        "source": "bounded-final-v1 answer-only execution profile",
        "renderer": "canonical_chat_template",
    },
    budget=ExecutionProfileBudget(
        static_think_tokens=0,
        static_final_tokens=16384,
        static_max_generated_tokens=16384,
        server_context_tokens=32768,
        agentic_max_turns=24,
        agentic_max_output_tokens_per_turn=1024,
        agentic_max_generated_tokens_per_task=32768,
        agentic_context_tokens=32768,
        kv_cache_k_dtype="f16",
        kv_cache_v_dtype="f16",
        context_fit_policy="exact-or-fail",
        context_extension_policy="none",
        per_task_timeout_s=1800,
    ),
)

GENERIC_THINK_TAGS_FORCING: Final = ForcingFormat("</think>", "\n</think>\n\n", ())

GENERIC_THINK_TAGS_PROFILE: Final = ReasoningRegistryEntry(
    id="generic_think_tags_8192_v1",
    version="1",
    status="ranked",
    model_match=("<think>", "enable_thinking", "thinking"),
    activation={
        "method": "template_introspection",
        "chat_template_kwargs": "derived_from_canonical_template",
        "system_prompt_injection": False,
    },
    forcing=GENERIC_THINK_TAGS_FORCING,
    parser={
        "reasoning_close": "</think>",
        "answer_reparse": "split_on_final_reasoning_close",
        "reasoning_parser": "generic_think_tags",
        "answer_stop": "derived_from_canonical_template_eos_eot",
    },
    conformance={
        "lane": "bounded-final-v1",
        "think_cap": 8192,
        "min_final": 1024,
        "think_budget": "min(8192, max(0, T_i - 1024))",
        "answer_budget": "T_i - reasoning_tokens_used",
        "leak_regexes": CANONICAL_REASONING_LEAK_REGEXES,
    },
    provenance={
        "source": "bounded-final-v1 generic think-tags two-pass forcing",
        "renderer": "canonical_chat_template",
        "answer_stop": "derived at run time from tokenizer/template EOS/EOT",
    },
    budget=_LEGACY_PROFILE_BUDGET,
)

GENERIC_THINK_TAGS_32768_PROFILE: Final = ReasoningRegistryEntry(
    id="generic_think_tags_32768_v1",
    version="1",
    status="ranked",
    model_match=GENERIC_THINK_TAGS_PROFILE.model_match,
    activation=GENERIC_THINK_TAGS_PROFILE.activation,
    forcing=GENERIC_THINK_TAGS_FORCING,
    parser=GENERIC_THINK_TAGS_PROFILE.parser,
    conformance={
        "lane": "bounded-final-v1",
        "think_cap": 32768,
        "min_final": 16384,
        "think_budget": "32768",
        "answer_budget": "16384",
        "max_generated_tokens": "32768 + 16384",
        "leak_regexes": CANONICAL_REASONING_LEAK_REGEXES,
    },
    provenance={
        **GENERIC_THINK_TAGS_PROFILE.provenance,
        "source": "profile-owned 32k generic think-tags two-pass forcing",
    },
    budget=ExecutionProfileBudget(
        static_think_tokens=32768,
        static_final_tokens=16384,
        static_max_generated_tokens=49152,
        server_context_tokens=65536,
        agentic_max_turns=40,
        agentic_max_output_tokens_per_turn=1024,
        agentic_max_generated_tokens_per_task=65536,
        agentic_context_tokens=32768,
        kv_cache_k_dtype="f16",
        kv_cache_v_dtype="f16",
        context_fit_policy="exact-or-fail",
        context_extension_policy="none",
        per_task_timeout_s=3000,
    ),
)

GEMMA4_CHANNEL_PROFILE: Final = ReasoningRegistryEntry(
    id="gemma4_channel_8192_v1",
    version="1",
    status="ranked",
    model_match=GEMMA4_REASONING_ENTRY.model_match,
    activation=GEMMA4_REASONING_ENTRY.activation,
    forcing=GEMMA4_FORCING,
    parser=GEMMA4_REASONING_ENTRY.parser,
    conformance={
        "lane": "bounded-final-v1",
        "think_cap": 8192,
        "min_final": 1024,
        "think_budget": "min(8192, max(0, T_i - 1024))",
        "answer_budget": "T_i - reasoning_tokens_used",
        "leak_regexes": GEMMA4_LEAK_REGEXES,
        "static_render_requires": GEMMA4_REASONING_ENTRY.conformance["static_render_requires"],
    },
    provenance={
        **GEMMA4_REASONING_ENTRY.provenance,
        "source": "bounded-final-v1 Gemma 4 channel override profile",
    },
    budget=_LEGACY_PROFILE_BUDGET,
)

REASONING_REGISTRY: Final[tuple[ReasoningRegistryEntry, ...]] = (
    ANSWER_ONLY_PROFILE,
    GENERIC_THINK_TAGS_PROFILE,
    GENERIC_THINK_TAGS_32768_PROFILE,
    GEMMA4_CHANNEL_PROFILE,
    QWEN_REASONING_ENTRY,
    GEMMA4_REASONING_ENTRY,
)


def reasoning_entry_for_activation(
    activation: ReasoningActivation,
) -> ReasoningRegistryEntry | None:
    """Return the registry entry used by a forced local activation, if ranked."""
    match activation:
        case "qwen3":
            return QWEN_REASONING_ENTRY
        case "gemma4":
            return GEMMA4_REASONING_ENTRY
        case "granite" | "nemotron" | "r1":
            return None
        case unreachable:
            assert_never(unreachable)


def reasoning_registry_payload() -> list[dict[str, JsonValue]]:
    """Canonical serialization of the reasoning registry for informational embedding."""
    return [_entry_payload(entry) for entry in REASONING_REGISTRY]


def execution_profile_payload(entry: ReasoningRegistryEntry) -> dict[str, JsonValue]:
    """Canonical serialization of one execution profile."""
    return _entry_payload(entry)


def execution_profile_digest(entry: ReasoningRegistryEntry) -> str:
    """sha256 of one execution profile's canonical payload."""
    return _digest(execution_profile_payload(entry))


def ranked_execution_profiles() -> Mapping[str, str]:
    """Server-side allowlist of ranked execution-profile ids and digests."""
    return {
        entry.id: execution_profile_digest(entry)
        for entry in REASONING_REGISTRY
        if entry.status == "ranked"
    }


def execution_profile_for_id(profile_id: str) -> ReasoningRegistryEntry | None:
    for entry in REASONING_REGISTRY:
        if entry.id == profile_id:
            return entry
    return None


def _entry_payload(entry: ReasoningRegistryEntry) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {}
    for field in fields(ReasoningRegistryEntry):
        if field.name == "budget":
            continue
        value = getattr(entry, field.name)
        if isinstance(value, ForcingFormat):
            payload[field.name] = {
                "reasoning_open": value.reasoning_open,
                "close": value.close,
                "forced_close": value.forced_close,
                "answer_stop": list(value.answer_stop),
                "reparse": value.reparse,
            }
        else:
            payload[field.name] = _json_value(value)
    return payload


def _json_value(value: object) -> JsonValue:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"reasoning registry value is not JSON-serializable: {value!r}")


def _digest(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
