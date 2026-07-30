from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest

from localbench._types import JsonObject
from localbench.bounded_final_profiles import (
    BoundedFinalProfileRequest,
    resolve_bounded_final_profile,
)
from localbench.campaign_records import CampaignConfig, campaign_record
from localbench.execution_contract import (
    ResolvedExecutionContract,
    execution_contract_notice,
    execution_contract_record,
    execution_contract_resume_identity,
    execution_profile_record,
)
from localbench.orchestrate import UnsafeResumeError, _validate_resume_campaign

_MODEL_SHA: Final = "1" * 64
_TEMPLATE_SHA: Final = "2" * 64
_EFFECTIVE_SHA: Final = "3" * 64
_RENDERER_CONTEXT_SHA: Final = (
    "ef0535353a1068f838242a315bb63c10f0e759c550d193031489e61137ef0993"
)


class _TemplateTokenizer:
    chat_template = (
        "{% if enable_thinking %}<think>{% endif %}"
        "<|im_start|>assistant\n<|im_end|>"
    )
    eos_token = "<|im_end|>"
    eot_token = None


def _contract(
    *,
    profile_id: str = "generic_think_tags_8192_v1",
    effective_template_sha256: str | None = _EFFECTIVE_SHA,
    chat_template_kwargs: dict[str, bool] | None = None,
) -> ResolvedExecutionContract:
    return ResolvedExecutionContract(
        profile_id=profile_id,
        selection_policy_id="gguf-effective-template-v1",
        selection_reason="gguf_generic_think_confirmed",
        template_source="gguf-default",
        raw_template_sha256=_TEMPLATE_SHA,
        effective_template_sha256=effective_template_sha256,
        chat_template_kwargs=(
            {"enable_thinking": True}
            if chat_template_kwargs is None
            else chat_template_kwargs
        ),
        answer_stops=("<|im_end|>",),
        reasoning_mode="generic_think",
        reasoning_budget=8192,
        model_file_sha256=_MODEL_SHA,
        runtime_probe={"passed": True, "applied_prompt_sha256": _EFFECTIVE_SHA},
        prompt_renderer_engine="llama.cpp/apply-template",
        prompt_renderer_contract_version="localbench.prompt-renderer.v1",
        prompt_renderer_context_sha256=_RENDERER_CONTEXT_SHA,
    )


def _campaign_config(
    tmp_path: Path,
    contract: ResolvedExecutionContract,
) -> CampaignConfig:
    return CampaignConfig(
        endpoint="http://local/v1",
        model="demo",
        suite_id="suite-v0",
        suite_hash="4" * 64,
        suite_dir=tmp_path,
        suite_terms_accepted=True,
        tier="quick",
        lane="bounded-final-v1",
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


def test_execution_contract_record_preserves_full_structured_identity() -> None:
    # Given: a probe-verified generic GGUF execution contract.
    contract = _contract()

    # When: the contract is serialized for campaign and manifest records.
    record = execution_contract_record(contract)

    # Then: every score-affecting field stays structured and full-length.
    assert record == {
        "id": "generic_think_tags_8192_v1",
        "selection_policy_id": "gguf-effective-template-v1",
        "selection_reason": "gguf_generic_think_confirmed",
        "template_source": "gguf-default",
        "raw_template_sha256": _TEMPLATE_SHA,
        "effective_template_sha256": _EFFECTIVE_SHA,
        "chat_template_kwargs": {"enable_thinking": True},
        "answer_stops": ["<|im_end|>"],
        "reasoning_mode": "generic_think",
        "reasoning_budget": 8192,
        "model_file_sha256": _MODEL_SHA,
        "runtime_probe": {
            "passed": True,
            "applied_prompt_sha256": _EFFECTIVE_SHA,
        },
        "prompt_renderer_engine": "llama.cpp/apply-template",
        "prompt_renderer_contract_version": "localbench.prompt-renderer.v1",
        "prompt_renderer_context_sha256": _RENDERER_CONTEXT_SHA,
    }


def test_public_execution_profile_uses_effective_template_and_probe_result() -> None:
    # Given: a runtime-verified GGUF execution contract.
    contract = _contract()

    # When: its public execution-profile disclosure is built.
    profile = execution_profile_record(contract)

    # Then: only the frozen public fields are disclosed, with the full effective hash.
    assert profile == {
        "id": "generic_think_tags_8192_v1",
        "selection_policy_id": "gguf-effective-template-v1",
        "selection_reason": "gguf_generic_think_confirmed",
        "template_source": "gguf-default",
        "template_sha256": _EFFECTIVE_SHA,
        "chat_template_kwargs": {"enable_thinking": True},
        "answer_stops": ["<|im_end|>"],
        "runtime_probe_passed": True,
        "prompt_renderer_engine": "llama.cpp.apply-template",
    }


def test_execution_contract_notice_uses_reason_code_and_short_template_hash() -> None:
    # Given: a contract whose persisted template hash is full length.
    contract = _contract()

    # When: the bench-start notice is formatted.
    notice = execution_contract_notice(contract)

    # Then: console output is code-keyed and abbreviates only the displayed hash.
    assert notice == (
        "execution_profile=generic_think_tags_8192_v1 "
        "selection_reason=gguf_generic_think_confirmed "
        f"template_sha256={_EFFECTIVE_SHA[:12]}"
    )


def test_hf_contract_regression_keeps_current_profile_kwargs_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the existing HF-sidecar auto path over a Qwen-style tokenizer.
    monkeypatch.setattr(
        "localbench.bounded_final_profiles.load_hf_chat_template_tokenizer",
        lambda *_args, **_kwargs: _TemplateTokenizer(),
    )

    # When: the profile is wrapped in the immutable execution contract.
    runtime = resolve_bounded_final_profile(
        BoundedFinalProfileRequest(
            profile="auto",
            hf_model_id="owner/model",
            hf_revision="a" * 40,
            model_file_sha256=_MODEL_SHA,
        ),
    )

    # Then: the pre-contract runtime kwargs and prompt manifest stay byte-identical.
    assert runtime.entry.id == "generic_think_tags_8192_v1"
    assert runtime.answer_stop == ("<|im_end|>",)
    assert runtime.chat_template_kwargs == {"enable_thinking": True}
    assert runtime.prompt_renderer_manifest == {
        "source": "hf-chat-template",
        "hf_model_id": "owner/model",
        "hf_revision": "a" * 40,
        "chat_template_sha256": runtime.contract.raw_template_sha256,
        "answer_stop": ["<|im_end|>"],
        "template_kwargs": {"enable_thinking": True},
    }
    assert runtime.contract.selection_policy_id == "hf-canonical-template-v1"
    assert runtime.contract.selection_reason == "generic_think_tags_8192_v1"
    assert runtime.contract.effective_template_sha256 is None
    assert runtime.contract.reasoning_mode == "generic_think"
    assert runtime.contract.reasoning_budget == 8192
    assert runtime.contract.model_file_sha256 == _MODEL_SHA
    assert runtime.contract.prompt_renderer_engine == (
        "transformers-jinja/hf-chat-template"
    )
    assert (
        runtime.contract.prompt_renderer_contract_version
        == "localbench.prompt-renderer.v1"
    )
    assert runtime.contract.prompt_renderer_context_sha256 == (
        "b856117f297af4167c6af4931e925869b0041f7e0cb55f620f7a76384d3ad64a"
    )


def test_gguf_contract_resolution_is_deterministic_for_same_artifact_bytes() -> None:
    # Given: identical embedded-template evidence and exact artifact hash.
    metadata: JsonObject = {
        "tokenizer.chat_template": (
            "{% if thinking %}<think>{% endif %}<|im_end|>"
        ),
        "tokenizer.ggml.eos_token_id": 0,
        "tokenizer.ggml.tokens": ["<|im_end|>"],
    }
    request = BoundedFinalProfileRequest(
        profile="auto",
        hf_model_id=None,
        model_file_sha256=_MODEL_SHA,
        gguf_metadata=metadata,
        llama_apply_template_base_url="http://llama.test",
        llama_api_key="secret",
    )

    # When: selection is repeated over the same bytes.
    first = resolve_bounded_final_profile(request)
    second = resolve_bounded_final_profile(request)

    # Then: both resolutions produce the exact same contract.
    assert first.contract == second.contract
    assert first.prompt_renderer is not None
    assert first.contract.profile_id == "generic_think_tags_8192_v1"
    assert first.contract.selection_policy_id == "gguf-effective-template-v1"
    assert first.contract.chat_template_kwargs == {"thinking": True}
    assert first.contract.prompt_renderer_engine == "llama.cpp/apply-template"
    assert (
        first.contract.prompt_renderer_contract_version
        == "localbench.prompt-renderer.v1"
    )
    assert first.contract.prompt_renderer_context_sha256 == (
        "8c9580869102e37ef0a4ad27d6bc60f040eec882d82986401502955b8ebe370b"
    )


@pytest.mark.parametrize(
    "changed",
    [
        replace(_contract(), profile_id="answer_only_v1"),
        replace(_contract(), effective_template_sha256="5" * 64),
        replace(_contract(), chat_template_kwargs={"thinking": True}),
        replace(_contract(), prompt_renderer_engine="different-renderer"),
        replace(_contract(), prompt_renderer_contract_version="different-version"),
        replace(_contract(), prompt_renderer_context_sha256="6" * 64),
    ],
)
def test_resume_identity_changes_for_profile_template_or_kwargs(
    changed: ResolvedExecutionContract,
) -> None:
    # Given: a prior probe-verified contract and one score-affecting mutation.
    original = _contract()

    # When: resume identities are derived.
    original_identity = execution_contract_resume_identity(original)
    changed_identity = execution_contract_resume_identity(changed)

    # Then: no profile, effective-template, or kwargs mutation can reuse checkpoints.
    assert changed_identity != original_identity


def test_campaign_resume_refuses_legacy_answer_only_partial_under_generic_contract(
    tmp_path: Path,
) -> None:
    # Given: a 0.4.11 partial campaign that recorded only answer_only_v1.
    config = _campaign_config(tmp_path, _contract())
    campaign = campaign_record(config, {}, tmp_path, [], started_at="2026-07-30T00:00:00Z")
    campaign["execution_profile"] = {"id": "answer_only_v1"}
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(campaign), encoding="utf-8")

    # When / Then: the new generic contract refuses the legacy partial.
    with pytest.raises(UnsafeResumeError, match="execution_contract"):
        _validate_resume_campaign(path, config)


def test_campaign_resume_refuses_archived_0_4_12_contract_shape(
    tmp_path: Path,
) -> None:
    config = _campaign_config(tmp_path, _contract())
    campaign = campaign_record(
        config,
        {},
        tmp_path,
        [],
        started_at="2026-07-30T00:00:00Z",
    )
    archived = campaign["execution_profile"]
    assert isinstance(archived, dict)
    for field in (
        "prompt_renderer_engine",
        "prompt_renderer_contract_version",
        "prompt_renderer_context_sha256",
    ):
        archived.pop(field)
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(campaign), encoding="utf-8")

    with pytest.raises(UnsafeResumeError, match="execution_contract"):
        _validate_resume_campaign(path, config)


def test_retry_errored_refuses_changed_execution_contract(tmp_path: Path) -> None:
    # Given: a completed campaign whose retry uses a different effective template.
    original = _campaign_config(tmp_path, _contract())
    campaign = campaign_record(original, {}, tmp_path, [], started_at="2026-07-30T00:00:00Z")
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(campaign), encoding="utf-8")
    retry = _campaign_config(
        tmp_path,
        replace(_contract(), effective_template_sha256="5" * 64),
    )

    # When / Then: retry-errored cannot mix checkpoints across contracts.
    with pytest.raises(UnsafeResumeError, match="execution_contract"):
        _validate_resume_campaign(path, retry)
