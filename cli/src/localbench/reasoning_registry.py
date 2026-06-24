"""Native reasoning-mode registry entries for ranked local lanes."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Final, Literal, Mapping, assert_never

from localbench._types import JsonValue
from localbench.budget_forcing import GEMMA4_FORCING, QWEN_FORCING, ForcingFormat
from localbench.prompt_rendering import ReasoningActivation

ReasoningRegistryStatus = Literal["ranked", "diagnostic", "experimental"]

GEMMA4_LEAK_REGEXES: Final[tuple[str, ...]] = (
    r"<\|channel>",
    r"<channel\|>",
    r"<\|think\|>",
    r"<turn\|>",
)


@dataclass(frozen=True, slots=True)
class ReasoningRegistryEntry:
    """Frozen identity for one native reasoning operating mode."""

    id: str
    version: str
    status: ReasoningRegistryStatus
    model_match: tuple[str, ...]
    activation: Mapping[str, JsonValue]
    forcing: ForcingFormat
    parser: Mapping[str, JsonValue]
    conformance: Mapping[str, JsonValue]
    provenance: Mapping[str, JsonValue]


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
)

REASONING_REGISTRY: Final[tuple[ReasoningRegistryEntry, ...]] = (
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
    """Canonical serialization of the reasoning registry for scorecard identity."""
    return [_entry_payload(entry) for entry in REASONING_REGISTRY]


def _entry_payload(entry: ReasoningRegistryEntry) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {}
    for field in fields(ReasoningRegistryEntry):
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
