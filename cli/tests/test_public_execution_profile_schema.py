from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from localbench.execution_contract import (
    ExecutionContractContext,
    execution_profile_record,
    resolved_execution_contract,
    structured_execution_profile,
)
from localbench.execution_profile_semantics import semantic_sha256_for_budget
from localbench.reasoning_registry import GENERIC_THINK_TAGS_32768_PROFILE
from localbench.reasoning_registry import ANSWER_ONLY_PROFILE


def _legacy_profile() -> dict[str, object]:
    return {
        "id": "generic_think_tags_8192_v1",
        "selection_policy_id": "gguf-effective-template-v1",
        "selection_reason": "gguf_generic_think_confirmed",
        "template_source": "gguf-default",
        "template_sha256": "a" * 64,
        "chat_template_kwargs": {"enable_thinking": True},
        "answer_stops": ["<|im_end|>"],
        "runtime_probe_passed": True,
        "prompt_renderer_engine": "llama.cpp.apply-template",
    }


def _base_t2_8192_profile_record() -> dict[str, object]:
    return {
        **_legacy_profile(),
        "static_think_tokens": 8192,
        "static_final_tokens": 8192,
        "static_max_generated_tokens": 16384,
        "server_context_tokens": 32768,
        "agentic_max_turns": 24,
        "agentic_max_output_tokens_per_turn": 1024,
        "agentic_max_generated_tokens_per_task": 32768,
        "agentic_context_tokens": 32768,
        "kv_cache_k_dtype": "f16",
        "kv_cache_v_dtype": "f16",
        "context_fit_policy": "exact-or-fail",
        "context_extension_policy": "none",
        "per_task_timeout_s": 1800,
        "semantic_sha256": (
            "a6bf105b73ad3f8120751151707ce2d15f4b20617a64250679a0dce8977d9bb3"
        ),
    }


def _v2_profile() -> dict[str, object]:
    contract = resolved_execution_contract(
        GENERIC_THINK_TAGS_32768_PROFILE,
        {"enable_thinking": True},
        ("<|im_end|>",),
        ExecutionContractContext(
            selection_policy_id="hf-canonical-template-v1",
            selection_reason=None,
            template_source="hf-chat-template",
            raw_template_sha256="1" * 64,
            model_file_sha256="2" * 64,
        ),
    )
    return execution_profile_record(contract)


def test_legacy_v1_public_profile_parses_without_reinterpretation() -> None:
    # Given: an unchanged 0.4.12/0.4.13 structured public profile.
    legacy = _legacy_profile()

    # When: it crosses the public-record parser.
    parsed = structured_execution_profile(legacy)

    # Then: its exact v1 representation is preserved.
    assert parsed == legacy


def test_base_t2_8192_public_profile_parses_without_field_loss() -> None:
    # Given: the exact enriched 8192 public record emitted at BASE 5c6e41f.
    base_record = _base_t2_8192_profile_record()

    # When: it crosses the current public-record parser.
    parsed = structured_execution_profile(base_record)

    # Then: all 23 BASE fields and their values survive unchanged.
    assert len(base_record) == 23
    assert parsed == base_record


def test_untrusted_v1_tuple_and_digest_cannot_claim_semantic_identity() -> None:
    # Given: an unknown v1 profile with a complete, self-consistent attacker-chosen tuple.
    profile = _base_t2_8192_profile_record()
    profile["id"] = "client-forged-v1"
    forged_budget = replace(
        GENERIC_THINK_TAGS_32768_PROFILE.budget,
        static_think_tokens=12_345,
    )
    profile.update(
        {
            "static_think_tokens": 12_345,
            "static_final_tokens": forged_budget.static_final_tokens,
            "static_max_generated_tokens": forged_budget.static_max_generated_tokens,
            "server_context_tokens": forged_budget.server_context_tokens,
            "agentic_max_turns": forged_budget.agentic_max_turns,
            "agentic_max_output_tokens_per_turn": forged_budget.agentic_max_output_tokens_per_turn,
            "agentic_max_generated_tokens_per_task": (
                forged_budget.agentic_max_generated_tokens_per_task
            ),
            "agentic_context_tokens": forged_budget.agentic_context_tokens,
            "kv_cache_k_dtype": forged_budget.kv_cache_k_dtype,
            "kv_cache_v_dtype": forged_budget.kv_cache_v_dtype,
            "context_fit_policy": forged_budget.context_fit_policy,
            "context_extension_policy": forged_budget.context_extension_policy,
            "per_task_timeout_s": forged_budget.per_task_timeout_s,
            "semantic_sha256": semantic_sha256_for_budget(forged_budget),
        },
    )

    # When: it crosses the public-record parser.
    parsed = structured_execution_profile(profile)

    # Then: display-safe v1 fields remain parseable but semantic authority is discarded.
    assert parsed == _legacy_profile() | {"id": "client-forged-v1"}


def test_answer_only_v1_zero_think_tuple_remains_parseable() -> None:
    # Given: the canonical answer-only v1 semantic tuple with zero reasoning tokens.
    profile = {
        **_legacy_profile(),
        "id": ANSWER_ONLY_PROFILE.id,
        "static_think_tokens": 0,
        "static_final_tokens": 16384,
        "static_max_generated_tokens": 16384,
        "server_context_tokens": 32768,
        "agentic_max_turns": 24,
        "agentic_max_output_tokens_per_turn": 1024,
        "agentic_max_generated_tokens_per_task": 32768,
        "agentic_context_tokens": 32768,
        "kv_cache_k_dtype": "f16",
        "kv_cache_v_dtype": "f16",
        "context_fit_policy": "exact-or-fail",
        "context_extension_policy": "none",
        "per_task_timeout_s": 1800,
        "semantic_sha256": semantic_sha256_for_budget(ANSWER_ONLY_PROFILE.budget),
    }

    # When / Then: the complete canonical tuple crosses unchanged.
    assert structured_execution_profile(profile) == profile


def test_32768_public_profile_serializes_as_complete_v2() -> None:
    # Given / When: the minted 32768 contract is serialized publicly.
    profile = _v2_profile()

    # Then: it explicitly declares v2 and carries the complete semantic identity.
    assert profile["schema_version"] == "localbench.execution_profile.v2"
    assert profile["semantic_sha256"] == (
        "e02ef5b5e75f19ca39d8949711bdd2d6517d1ce9267012ac923abffb94fbf058"
    )
    assert structured_execution_profile(profile) == profile


@pytest.mark.parametrize(
    "missing_field",
    ["selection_policy_id", "agentic_max_turns", "semantic_sha256"],
)
def test_32768_public_profile_rejects_incomplete_v2(missing_field: str) -> None:
    # Given: a declared 32768-v2 record missing one required identity field.
    profile = deepcopy(_v2_profile())
    del profile[missing_field]

    # When / Then: contract parsing fails instead of downgrading or dropping it.
    with pytest.raises(RuntimeError, match=missing_field):
        structured_execution_profile(profile)


def test_32768_public_profile_rejects_semantically_inconsistent_v2() -> None:
    # Given: a complete v2 record whose tuple no longer matches its semantic digest.
    profile = deepcopy(_v2_profile())
    profile["agentic_max_turns"] = 39

    # When / Then: contract parsing rejects the inconsistent identity.
    with pytest.raises(RuntimeError, match="semantic_sha256"):
        structured_execution_profile(profile)


def test_32768_public_profile_rejects_a_rehashed_different_tuple() -> None:
    # Given: a self-consistent tuple/digest pair that does not match the minted profile.
    profile = deepcopy(_v2_profile())
    changed_budget = replace(
        GENERIC_THINK_TAGS_32768_PROFILE.budget,
        agentic_max_turns=39,
    )
    profile["agentic_max_turns"] = 39
    profile["semantic_sha256"] = semantic_sha256_for_budget(changed_budget)

    # When / Then: the profile ID cannot be rebound to a different semantic tuple.
    with pytest.raises(RuntimeError, match="agentic_max_turns"):
        structured_execution_profile(profile)
