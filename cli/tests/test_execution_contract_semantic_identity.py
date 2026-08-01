from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Never

import pytest

from localbench._types import JsonObject
from localbench.campaign_records import CampaignConfig, campaign_record
from localbench.bounded_final_profiles import resolve_bounded_final_profile_from_introspection
from localbench.execution_contract import (
    ExecutionContractContext,
    ResolvedExecutionContract,
    execution_contract_record,
    execution_contract_resume_identity,
    execution_profile_record,
    execution_profile_semantic_payload,
    resolved_execution_contract,
    structured_execution_profile,
)
from localbench.prompt_rendering import TemplateIntrospection
from localbench.reasoning_registry import GENERIC_THINK_TAGS_32768_PROFILE
from localbench.scoring.agentic_exec.funnel import Stage, SubsetSpec, run_with_reruns
from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.task_journal import (
    AgenticResumeSeed,
    ResumeIdentityMismatchError,
    TaskJournal,
)

_EXPECTED_SEMANTIC_SHA256 = (
    "e02ef5b5e75f19ca39d8949711bdd2d6517d1ce9267012ac923abffb94fbf058"
)
_EXPECTED_TUPLE: JsonObject = {
    "static_think_tokens": 32768,
    "static_final_tokens": 16384,
    "static_max_generated_tokens": 49152,
    "server_context_tokens": 65536,
    "agentic_max_turns": 40,
    "agentic_max_output_tokens_per_turn": 1024,
    "agentic_max_generated_tokens_per_task": 65536,
    "agentic_context_tokens": 32768,
    "kv_cache_k_dtype": "f16",
    "kv_cache_v_dtype": "f16",
    "context_fit_policy": "exact-or-fail",
    "context_extension_policy": "none",
    "per_task_timeout_s": 3000,
}


def _contract() -> ResolvedExecutionContract:
    return resolved_execution_contract(
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


def _campaign_config(
    tmp_path: Path,
    contract: ResolvedExecutionContract,
) -> CampaignConfig:
    return CampaignConfig(
        endpoint="http://local/v1",
        model="demo",
        suite_id="suite-v0",
        suite_hash="3" * 64,
        suite_dir=tmp_path,
        suite_terms_accepted=True,
        tier="quick",
        lane="bounded-final-v2",
        provider="local",
        concurrency=1,
        max_items=1,
        max_tokens=None,
        reasoning_effort=None,
        reasoning_activation="qwen3",
        hf_model_id=None,
        execution_contract=contract,
        output_path=tmp_path / "localbench-run.json",
    )


def _resume_seed(normalized_server_identity: str) -> AgenticResumeSeed:
    return AgenticResumeSeed(
        agentic_runtime_identity_sha256="4" * 64,
        model_sha256="5" * 64,
        normalized_server_identity=normalized_server_identity,
        host_loop_scorer_contract_digest="7" * 64,
        lane="bounded-final-v2",
        profile="generic_think_tags_32768_v1",
        wsl_kernel_family="6.6-microsoft-standard-WSL2",
        gpu_architecture="NVIDIA RTX PRO 6000 Blackwell",
        driver_runtime_family="driver=fixture",
    )


def _sampling(config: LoopConfig) -> JsonObject:
    return {
        "max_turns": config.max_turns,
        "max_output_tokens_per_turn": config.max_output_tokens_per_turn,
        "max_observation_chars": config.max_observation_chars,
        "context_window": config.context_window,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "seed": config.seed,
    }


def test_resolved_contract_semantic_digest_covers_exact_full_tuple() -> None:
    # Given: the minted 32k resolved execution contract.
    contract = _contract()

    # When: its canonical semantic payload and identity are read.
    payload = execution_profile_semantic_payload(contract)

    # Then: all thirteen owned fields and the independently calculated digest are exact.
    assert payload == _EXPECTED_TUPLE
    assert contract.semantic_sha256 == _EXPECTED_SEMANTIC_SHA256


def test_campaign_and_public_profile_share_the_contract_semantic_identity(
    tmp_path: Path,
) -> None:
    # Given: one resolved contract used for campaign and public records.
    contract = _contract()

    # When: the internal campaign contract and public profile are serialized.
    internal = execution_contract_record(contract)
    public = execution_profile_record(contract)
    campaign = campaign_record(
        _campaign_config(tmp_path, contract),
        {},
        tmp_path,
        [],
        started_at="2026-08-01T00:00:00Z",
    )

    # Then: every surface carries the same tuple-derived semantic identity.
    assert internal["semantic_sha256"] == _EXPECTED_SEMANTIC_SHA256
    assert public["semantic_sha256"] == _EXPECTED_SEMANTIC_SHA256
    assert campaign["execution_profile"]["semantic_sha256"] == _EXPECTED_SEMANTIC_SHA256
    for field, expected in _EXPECTED_TUPLE.items():
        assert internal[field] == expected
        assert public[field] == expected


def test_gemma4_32768_profile_flows_the_shared_semantic_identity_into_public_v2() -> None:
    # Given: a Gemma 4 family activation resolved through the shared auto policy.
    runtime = resolve_bounded_final_profile_from_introspection(
        "auto",
        TemplateIntrospection(
            answer_stop=("<turn|>",),
            chat_template_kwargs={"enable_thinking": True},
            supports_generic_thinking=True,
            supports_gemma_channel=True,
        ),
    )

    # When: its resolved contract is projected to the public execution-profile schema.
    public = execution_profile_record(runtime.contract)

    # Then: the Gemma-specific format keeps the exact shared tuple and semantic identity.
    assert public.get("id") == "gemma4_channel_32768_v1"
    assert public.get("schema_version") == "localbench.execution_profile.v2"
    assert public.get("semantic_sha256") == _EXPECTED_SEMANTIC_SHA256
    assert structured_execution_profile(public) == public
    for field, expected in _EXPECTED_TUPLE.items():
        assert public[field] == expected


def test_agentic_resume_refuses_40_to_39_semantic_drift_before_model_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a persisted agentic journal minted with max_turns=40 and an otherwise exact tuple.
    from localbench.scoring.agentic_exec import execution_contract as agentic_contract

    monkeypatch.setattr(agentic_contract, "assert_execution_contract", lambda: "contract")
    contract = _contract()
    changed_budget = replace(contract.budget, agentic_max_turns=39)
    changed_contract = replace(contract, budget=changed_budget)
    config = LoopConfig()
    original_identity = _resume_seed(execution_contract_resume_identity(contract)).build(
        task_set_sha256="8" * 64,
        sampling=_sampling(config),
    )
    changed_identity = _resume_seed(
        execution_contract_resume_identity(changed_contract)
    ).build(
        task_set_sha256="8" * 64,
        sampling=_sampling(config),
    )
    results_dir = tmp_path / "agentic"
    results_dir.mkdir()
    with TaskJournal.open(results_dir / "agentic-task-journal.bin", original_identity):
        pass
    model_requests: list[str] = []

    def model_factory(task_id: str) -> Never:
        model_requests.append(task_id)
        raise AssertionError("resume drift must refuse before model construction")

    def sandbox_factory(task_id: str) -> Never:
        raise AssertionError(f"resume drift must refuse before sandbox construction: {task_id}")

    # When: the same run is resumed with only agentic_max_turns changed to 39.
    with pytest.raises(
        ResumeIdentityMismatchError,
        match="normalized_server_identity drifted",
    ):
        run_with_reruns(
            label="semantic-resume",
            stage=Stage.SCORED,
            subset=SubsetSpec(
                name="semantic-resume",
                split="dev",
                size=1,
                seed=20260801,
                task_ids=("fac291d_1",),
            ),
            model_factory=model_factory,
            sandbox_factory=sandbox_factory,
            config=config,
            results_dir=results_dir,
            base_count=2,
            resume_identity=changed_identity,
        )

    # Then: persisted semantic identity rejects the run at the journal boundary.
    assert changed_contract.semantic_sha256 != contract.semantic_sha256
    assert model_requests == []
