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
