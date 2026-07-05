"""Tests for native reasoning-mode registry entries."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from localbench.reasoning_registry import (
    ANSWER_ONLY_PROFILE,
    GEMMA4_LEAK_REGEXES,
    GEMMA4_REASONING_ENTRY,
    QWEN_REASONING_ENTRY,
    ReasoningRegistryEntry,
    execution_profile_digest,
    execution_profile_payload,
    ranked_execution_profiles,
    reasoning_entry_for_activation,
)


def test_reasoning_registry_entry_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        QWEN_REASONING_ENTRY.id = "changed"


def test_qwen_registry_entry_records_existing_native_forcing_behavior() -> None:
    entry = reasoning_entry_for_activation("qwen3")

    assert isinstance(entry, ReasoningRegistryEntry)
    assert entry is QWEN_REASONING_ENTRY
    assert entry.id == "qwen_thinking_native_v1"
    assert entry.status == "ranked"
    assert entry.activation["method"] == "native_chatml_default"
    assert entry.activation["chat_template_kwargs"] == {}
    assert entry.activation["system_prompt_injection"] is False
    assert entry.forcing.close == "</think>"
    assert entry.forcing.forced_close == "\n</think>\n\n"
    assert entry.forcing.answer_stop == ("<|im_end|>",)
    assert entry.forcing.reparse is None


def test_execution_profile_identity_is_per_entry_and_ranked_allowlisted() -> None:
    payload = execution_profile_payload(QWEN_REASONING_ENTRY)
    digest = execution_profile_digest(QWEN_REASONING_ENTRY)
    ranked = ranked_execution_profiles()

    assert payload["id"] == "qwen_thinking_native_v1"
    assert payload["forcing"]["close"] == "</think>"
    assert len(digest) == 64
    assert ranked["qwen_thinking_native_v1"] == digest
    assert ranked["gemma4_thinking_native_v1"] == execution_profile_digest(GEMMA4_REASONING_ENTRY)
    assert ranked["answer_only_v1"] == execution_profile_digest(ANSWER_ONLY_PROFILE)


def test_answer_only_profile_records_profile_dispatch_contract() -> None:
    payload = execution_profile_payload(ANSWER_ONLY_PROFILE)

    assert payload["id"] == "answer_only_v1"
    assert payload["status"] == "ranked"
    assert payload["model_match"] == ["*"]
    assert payload["activation"] == {
        "method": "chat_template_kwargs_when_supported",
        "chat_template_kwargs": {"enable_thinking": False},
        "system_prompt_injection": False,
    }
    assert payload["forcing"] is None
    assert payload["parser"]["scored_text"] == "final_text_only"


def test_gemma4_registry_entry_records_verified_provenance_verbatim() -> None:
    entry = reasoning_entry_for_activation("gemma4")

    assert entry is GEMMA4_REASONING_ENTRY
    assert entry.id == "gemma4_thinking_native_v1"
    assert entry.status == "ranked"
    assert entry.model_match == ("unsloth/gemma-4-31B-it", "gemma-4", "gemma4")
    assert entry.activation == {
        "method": "chat_template_kwargs",
        "reasoning_activation": "gemma4",
        "chat_template_kwargs": {"enable_thinking": True},
        "system_prompt_injection": False,
    }
    assert entry.forcing.reasoning_open == "<|channel>thought\n"
    assert entry.forcing.close == "<channel|>"
    assert entry.forcing.forced_close == "\n<channel|>"
    assert entry.forcing.answer_stop == ("<turn|>",)
    assert entry.forcing.reparse == r"(?s)<\|channel>thought\n(.*?)<channel\|>"
    assert entry.provenance["hf_model_id"] == "unsloth/gemma-4-31B-it"
    assert entry.provenance["revision"] == "a1c85d1c2db7dcd15c41ad4082955240a9465743"
    assert entry.provenance["chat_template_sha256"] == (
        "94899c0f917d93f6fe81c95744d1e8ddab2d21d39228d2e4aec1fb2a25bff413"
    )
    assert entry.provenance["eot_token"] == "<turn|>"
    assert entry.provenance["eos_token"] == "<turn|>"
    assert entry.provenance["answer_stop"] == ("<turn|>",)
    assert entry.provenance["template_confirmed"] == "contains enable_thinking + channel/think tags"
    assert entry.conformance["leak_regexes"] == GEMMA4_LEAK_REGEXES
