from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import httpx
import pytest

from localbench._types import JsonObject
from localbench.bounded_final_forcing import bounded_final_answer_budget
from localbench.bounded_final_profiles import (
    BoundedFinalProfileRuntime,
    UnsupportedBoundedFinalProfileError,
    resolve_bounded_final_profile_from_introspection,
)
from localbench.prompt_rendering import (
    HfChatPromptRenderer,
    TemplateIntrospection,
    derive_template_introspection,
)
from localbench.reasoning_registry import (
    GEMMA4_CHANNEL_PROFILE,
    GEMMA4_REASONING_ENTRY,
    GENERIC_THINK_TAGS_PROFILE,
    QWEN_REASONING_ENTRY,
    execution_profile_digest,
    ranked_execution_profiles,
)
from localbench.lane_spec import bounded_final_think_budget
from localbench.scoring.scorecard import scorecard_identity
from localbench.orchestrate import OrchestrateConfig, run_localbench


FIXTURE_SUITE = Path(__file__).parent / "fixtures" / "suite_v0"
LEGACY_QWEN_DIGEST = "a2fd0e4701fc6724a71aa4ab8a0f43d908b1e69472b3b72617c759aa96f17dec"
LEGACY_GEMMA4_DIGEST = "bf66a190a9c04e27aa79d008c4e4e6c2c2deadb80ca9f9ee0b78cb19779d2f62"
WAVE_2A_BOUNDED_ANSWER_ONLY_SCORECARD_ID = (
    "a892f8a27a8bacd781a2117a16f1ccc107cf407b07cf317163390dbbc74fd80c"
)
WAVE_2A_BOUNDED_V2_ANSWER_ONLY_SCORECARD_ID = (
    "cf4cddf3d70b87652f851e466a4ba10dbe232dbbb657f4592489cb0e900c1981"
)


class _TemplateTokenizer:
    def __init__(
        self,
        *,
        chat_template: str,
        eos_token: str | None,
        additional_special_tokens: tuple[str, ...] = (),
    ) -> None:
        self.chat_template = chat_template
        self.eos_token = eos_token
        self.additional_special_tokens = additional_special_tokens
        self.calls: list[JsonObject] = []

    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        **kwargs: bool,
    ) -> str:
        self.calls.append(
            {
                "conversation": [dict(message) for message in conversation],
                "tokenize": tokenize,
                "add_generation_prompt": add_generation_prompt,
                "kwargs": dict(kwargs),
            },
        )
        return (
            "<|im_start|>user\n"
            f"{conversation[-1]['content']}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )


def test_template_introspection_derives_chatml_answer_stop_from_tokenizer_template() -> None:
    tokenizer = _TemplateTokenizer(
        chat_template=(
            "{% for message in messages %}<|im_start|>{{ message['role'] }}\n"
            "{{ message['content'] }}<|im_end|>{% endfor %}"
            "{% if enable_thinking %}<think>{% endif %}"
        ),
        eos_token="<|im_end|>",
    )

    introspection = derive_template_introspection(tokenizer)

    assert introspection.answer_stop == ("<|im_end|>",)
    assert introspection.supports_generic_thinking is True
    assert introspection.chat_template_kwargs == {"enable_thinking": True}


def test_template_introspection_derives_llama3_answer_stop_from_tokenizer_template() -> None:
    tokenizer = _TemplateTokenizer(
        chat_template=(
            "{% for message in messages %}<|start_header_id|>{{ message['role'] }}"
            "<|end_header_id|>\n\n{{ message['content'] }}<|eot_id|>{% endfor %}"
            "{% if thinking %}<think>{% endif %}"
        ),
        eos_token="<|eot_id|>",
    )

    introspection = derive_template_introspection(tokenizer)

    assert introspection.answer_stop == ("<|eot_id|>",)
    assert introspection.supports_generic_thinking is True
    assert introspection.chat_template_kwargs == {"thinking": True}


def test_template_introspection_derives_gemma_answer_stop_from_pinned_template() -> None:
    tokenizer = _TemplateTokenizer(
        chat_template=(
            "{{ bos_token }}<start_of_turn>user\n{{ prompt }}<turn|>"
            "{% if enable_thinking %}<|channel>thought\n{% endif %}"
        ),
        eos_token="<turn|>",
    )

    introspection = derive_template_introspection(tokenizer)

    assert introspection.answer_stop == ("<turn|>",)
    assert introspection.supports_gemma_channel is True
    assert introspection.chat_template_kwargs == {"enable_thinking": True}


def test_profile_auto_resolution_uses_think_profile_for_thinking_template() -> None:
    introspection = TemplateIntrospection(
        answer_stop=("<|im_end|>",),
        chat_template_kwargs={"enable_thinking": True},
        supports_generic_thinking=True,
        supports_gemma_channel=False,
    )

    resolved = resolve_bounded_final_profile_from_introspection("auto", introspection)

    assert resolved.entry is GENERIC_THINK_TAGS_PROFILE
    assert resolved.chat_template_kwargs == {"enable_thinking": True}
    assert resolved.answer_stop == ("<|im_end|>",)


def test_profile_auto_resolution_uses_answer_only_for_plain_template() -> None:
    introspection = TemplateIntrospection(
        answer_stop=("<|eot_id|>",),
        chat_template_kwargs={},
        supports_generic_thinking=False,
        supports_gemma_channel=False,
    )

    resolved = resolve_bounded_final_profile_from_introspection("auto", introspection)

    assert resolved.entry.id == "answer_only_v1"
    assert resolved.chat_template_kwargs == {"enable_thinking": False}
    assert resolved.answer_stop == ("<|eot_id|>",)


def test_explicit_think_profile_on_unsupported_template_fails_with_answer_only_guidance() -> None:
    introspection = TemplateIntrospection(
        answer_stop=("<|eot_id|>",),
        chat_template_kwargs={},
        supports_generic_thinking=False,
        supports_gemma_channel=False,
    )

    with pytest.raises(UnsupportedBoundedFinalProfileError, match="answer_only_v1"):
        resolve_bounded_final_profile_from_introspection(
            "generic_think_tags_8192_v1",
            introspection,
        )


def test_answer_stop_with_backtick_is_rejected_for_code_safe_bounded_final() -> None:
    introspection = TemplateIntrospection(
        answer_stop=("```",),
        chat_template_kwargs={"enable_thinking": True},
        supports_generic_thinking=True,
        supports_gemma_channel=False,
    )

    with pytest.raises(UnsupportedBoundedFinalProfileError, match="backtick"):
        resolve_bounded_final_profile_from_introspection(
            "generic_think_tags_8192_v1",
            introspection,
        )


def test_new_ranked_profiles_are_allowlisted_without_changing_legacy_digests() -> None:
    ranked = ranked_execution_profiles()

    assert execution_profile_digest(QWEN_REASONING_ENTRY) == LEGACY_QWEN_DIGEST
    assert execution_profile_digest(GEMMA4_REASONING_ENTRY) == LEGACY_GEMMA4_DIGEST
    assert ranked["generic_think_tags_8192_v1"] == execution_profile_digest(
        GENERIC_THINK_TAGS_PROFILE,
    )
    assert ranked["gemma4_channel_8192_v1"] == execution_profile_digest(GEMMA4_CHANNEL_PROFILE)


def test_gemma4_channel_profile_converts_legacy_payload_for_bounded_final_lane() -> None:
    payload = GEMMA4_CHANNEL_PROFILE

    assert payload.id == "gemma4_channel_8192_v1"
    assert payload is not GEMMA4_REASONING_ENTRY
    assert payload.forcing is not None
    assert payload.forcing.close == "<channel|>"
    assert payload.forcing.forced_close == "\n<channel|>"
    assert payload.forcing.answer_stop == ("<turn|>",)
    assert payload.conformance["lane"] == "bounded-final-v1"
    assert payload.conformance["think_budget"] == "min(8192, max(0, T_i - 1024))"


@pytest.mark.parametrize(
    ("total_cap", "expected"),
    [
        (512, 0),
        (1024, 0),
        (2048, 1024),
        (9216, 8192),
        (10000, 8192),
    ],
)
def test_bounded_final_think_budget_edges(total_cap: int, expected: int) -> None:
    assert bounded_final_think_budget(total_cap) == expected


@pytest.mark.parametrize(
    ("total_cap", "reasoning_tokens", "expected"),
    [
        (512, 0, 512),
        (1024, 0, 1024),
        (2048, 1024, 1024),
        (10000, 8192, 1808),
        (10000, 512, 9488),
    ],
)
def test_bounded_final_answer_budget_uses_actual_reasoning_tokens(
    total_cap: int,
    reasoning_tokens: int,
    expected: int,
) -> None:
    assert bounded_final_answer_budget(total_cap, reasoning_tokens) == expected


def test_adding_profiles_does_not_change_wave_2a_bounded_answer_only_scorecard_id() -> None:
    identity = scorecard_identity("answer_only_v1", lane_spec_id="bounded-final-v1")

    assert identity["scorecard_id"] == WAVE_2A_BOUNDED_ANSWER_ONLY_SCORECARD_ID
    assert identity["execution_profile_id"] == "answer_only_v1"


def test_bounded_final_v2_answer_only_scorecard_id_is_frozen() -> None:
    identity = scorecard_identity("answer_only_v1", lane_spec_id="bounded-final-v2")

    assert identity["scorecard_id"] == WAVE_2A_BOUNDED_V2_ANSWER_ONLY_SCORECARD_ID
    assert identity["execution_profile_id"] == "answer_only_v1"


def test_bounded_final_generic_two_pass_uses_actual_reasoning_tokens_for_budget_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        suite_dir = tmp_path / "suite"
        shutil.copytree(FIXTURE_SUITE, suite_dir)
        suite_json = json.loads((suite_dir / "suite.json").read_text(encoding="utf-8"))
        suite_json["benches"]["mmlu_pro"]["decoding"]["max_tokens"] = 2048
        (suite_dir / "suite.json").write_text(json.dumps(suite_json), encoding="utf-8")

        tokenizer = _TemplateTokenizer(
            chat_template=(
                "{% for message in messages %}<|im_start|>{{ message['role'] }}\n"
                "{{ message['content'] }}<|im_end|>{% endfor %}"
                "{% if enable_thinking %}<think>{% endif %}"
            ),
            eos_token="<|im_end|>",
        )
        runtime = BoundedFinalProfileRuntime(
            entry=GENERIC_THINK_TAGS_PROFILE,
            forcing=GENERIC_THINK_TAGS_PROFILE.forcing,
            prompt_renderer=HfChatPromptRenderer(
                tokenizer=tokenizer,
                activation=None,
                chat_template_kwargs={"enable_thinking": True},
                answer_stop=("<|im_end|>",),
            ),
            answer_stop=("<|im_end|>",),
            chat_template_kwargs={"enable_thinking": True},
            prompt_renderer_manifest={
                "source": "fixture-tokenizer",
                "answer_stop": ["<|im_end|>"],
                "template_kwargs": {"enable_thinking": True},
            },
        )
        monkeypatch.setattr("localbench.orchestrate.resolve_bounded_final_profile", lambda _config: runtime)
        seen: list[JsonObject] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "runtime-demo"}]})
            body = json.loads(request.content)
            seen.append(body)
            if body["stop"] == ["</think>"]:
                assert body["max_tokens"] == 1024
                return httpx.Response(
                    200,
                    json=_raw_completion(
                        "<think>\nfull budget",
                        "length",
                        prompt_tokens=10,
                        completion_tokens=1024,
                    ),
                )
            assert body["stop"] == ["<|im_end|>"]
            assert body["prompt"].endswith("<think>\nfull budget\n</think>\n\n")
            assert body["max_tokens"] == 1024
            return httpx.Response(
                200,
                json=_raw_completion(
                    "Answer: A<|im_end|>",
                    "stop",
                    prompt_tokens=20,
                    completion_tokens=1,
                ),
            )

        record = await run_localbench(
            OrchestrateConfig(
                endpoint="http://local/v1",
                model="demo-model",
                suite_dir=suite_dir,
                bench="mmlu_pro",
                out=tmp_path / "bounded-think.json",
                max_items=1,
                lane="bounded-final-v1",
                profile="generic_think_tags_8192_v1",
                publishable=True,
                sampler_temperature=0.0,
                sampler_top_k=1,
                sampler_seed=1234,
                determinism_policy="strict-greedy-temp0-seeded-v1",
                hf_model_id="fixture/thinking",
            ),
            transport=httpx.MockTransport(handler),
        )

        assert [body["stop"] for body in seen] == [["</think>"], ["<|im_end|>"]]
        assert record["manifest"]["sampling"]["execution_profile_id"] == "generic_think_tags_8192_v1"
        assert record["manifest"]["prompt_renderer"]["answer_stop"] == ["<|im_end|>"]
        assert record["budget_audit"]["status"] == "exact"
        assert record["items"][0]["response_text"] == "Answer: A"
        assert record["items"][0]["generated_tokens"] == {
            "total": 1025,
            "reasoning": 1024,
            "final": 1,
            "source": "server_usage",
        }

    asyncio.run(scenario())


def _raw_completion(
    text: str,
    finish_reason: str,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> JsonObject:
    return {
        "choices": [{"text": text, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
