from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from localbench.providers import provider_for_name
from localbench.runner import run_benchmark


MESSAGES = [
    {"role": "system", "content": "Answer briefly."},
    {"role": "user", "content": "Pick C."},
]
DECODING = {"temperature": 0, "top_p": 1, "max_tokens": 16}


def test_local_profile_when_building_payload_matches_openai_chat_shape() -> None:
    # Given the default local provider and suite-rendered decoding.
    provider = provider_for_name("local")

    # When building a request payload.
    payload = provider.build_payload("demo-model", MESSAGES, DECODING, "answer-only")

    # Then the current OpenAI-compatible local request shape is preserved.
    assert payload == {
        "model": "demo-model",
        "messages": MESSAGES,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 16,
    }
    assert provider.endpoint_url("http://local/v1/") == "http://local/v1/chat/completions"
    assert provider.headers("sk-test") == {
        "content-type": "application/json",
        "authorization": "Bearer sk-test",
    }
    assert provider.notes() == []


@pytest.mark.parametrize("provider_name", ["local", "openai-chat"])
def test_non_reasoning_profiles_when_effort_is_set_ignore_it(
    provider_name: str,
) -> None:
    # Given a non-reasoning OpenAI-compatible provider.
    provider = provider_for_name(provider_name)

    # When building a request payload with an explicit reasoning effort.
    payload = provider.build_payload(
        "demo-model",
        MESSAGES,
        DECODING,
        "answer-only",
        effort="high",
    )

    # Then the current request shape is unchanged and no effort note is recorded.
    assert payload == {
        "model": "demo-model",
        "messages": MESSAGES,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 16,
    }
    assert provider.notes(effort="high", decodings=[DECODING]) == []


def test_openai_reasoning_profile_when_building_payload_uses_reasoning_params() -> None:
    # Given the GPT-5/o-series OpenAI reasoning provider.
    provider = provider_for_name("openai-reasoning")

    # When building a request payload.
    payload = provider.build_payload("gpt-5.1", MESSAGES, DECODING, "api-uncapped")

    # Then rejected classic sampling params are omitted and max tokens are renamed.
    assert payload == {
        "model": "gpt-5.1",
        "messages": MESSAGES,
        "max_completion_tokens": 16,
    }
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert provider.notes() == [
        "greedy not enforceable; provider-default sampling",
    ]


def test_openai_reasoning_profile_when_effort_is_set_sends_it_verbatim() -> None:
    # Given the GPT-5/o-series OpenAI reasoning provider.
    provider = provider_for_name("openai-reasoning")

    # When building a request payload with xhigh effort.
    payload = provider.build_payload(
        "gpt-5.1",
        MESSAGES,
        DECODING,
        "api-uncapped",
        effort="xhigh",
    )

    # Then the requested value is sent exactly as given and recorded in notes.
    assert payload == {
        "model": "gpt-5.1",
        "messages": MESSAGES,
        "max_completion_tokens": 16,
        "reasoning_effort": "xhigh",
    }
    assert provider.notes(effort="xhigh", decodings=[DECODING]) == [
        "greedy not enforceable; provider-default sampling",
        "reasoning_effort=xhigh sent as OpenAI reasoning_effort",
    ]


def test_openai_reasoning_profile_when_parsing_response_keeps_reasoning_tokens() -> None:
    # Given an OpenAI reasoning chat-completion response with hidden reasoning usage.
    provider = provider_for_name("openai-reasoning")

    # When parsing the response.
    parsed = provider.parse_response(
        {
            "choices": [
                {
                    "message": {"content": "Answer: C"},
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 6,
                "total_tokens": 16,
                "completion_tokens_details": {"reasoning_tokens": 4},
            },
        },
    )

    # Then standard usage and reasoning-token usage are retained.
    assert parsed.response_text == "Answer: C"
    assert parsed.finish_reason == "stop"
    assert parsed.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 6,
        "total_tokens": 16,
        "reasoning_tokens": 4,
    }


def test_openai_chat_profile_when_content_is_empty_and_truncated_records_empty_text() -> None:
    # Given a classic OpenAI-compatible provider and a truncation response with no content.
    provider = provider_for_name("openai-chat")

    # When parsing the response.
    parsed = provider.parse_response(
        {
            "choices": [
                {
                    "message": {"content": None},
                    "finish_reason": "length",
                },
            ],
        },
    )

    # Then the empty completion is recorded, not treated as malformed.
    assert parsed.response_text == ""
    assert parsed.reasoning_text is None
    assert parsed.finish_reason == "length"


@pytest.mark.parametrize(
    "provider_name",
    ["local", "openai-chat", "openai-reasoning", "gemini"],
)
def test_openai_compatible_profiles_when_empty_truncation_parse_empty_text(
    provider_name: str,
) -> None:
    # Given an OpenAI-compatible provider response truncated before final content.
    provider = provider_for_name(provider_name)

    # When parsing the response.
    parsed = provider.parse_response(
        {
            "choices": [
                {
                    "message": {"content": None},
                    "finish_reason": "length",
                },
            ],
        },
    )

    # Then every OpenAI-compatible profile records an empty answer consistently.
    assert parsed.response_text == ""
    assert parsed.reasoning_text is None
    assert parsed.finish_reason == "length"


def test_anthropic_profile_when_building_payload_uses_messages_shape() -> None:
    # Given the Anthropic native provider and a capped-thinking lane.
    provider = provider_for_name("anthropic")

    # When building a request payload.
    payload = provider.build_payload(
        "claude-sonnet-anchor",
        MESSAGES,
        {**DECODING, "thinking_budget": 8},
        "capped-thinking",
    )

    # Then system text is top-level, user/assistant turns stay in messages, and thinking is enabled.
    assert payload == {
        "model": "claude-sonnet-anchor",
        "system": "Answer briefly.",
        "messages": [{"role": "user", "content": "Pick C."}],
        "max_tokens": 16,
        "temperature": 0,
        "top_p": 1,
        "thinking": {"type": "enabled", "budget_tokens": 8},
    }
    assert provider.endpoint_url("https://api.anthropic.com") == (
        "https://api.anthropic.com/v1/messages"
    )
    assert provider.headers("sk-ant-test") == {
        "content-type": "application/json",
        "x-api-key": "sk-ant-test",
        "anthropic-version": "2023-06-01",
    }


@pytest.mark.parametrize(
    ("effort", "expected_thinking"),
    [
        ("minimal", None),
        ("low", {"type": "enabled", "budget_tokens": 4096}),
        ("medium", {"type": "enabled", "budget_tokens": 8192}),
        ("high", {"type": "enabled", "budget_tokens": 16384}),
        ("xhigh", {"type": "enabled", "budget_tokens": 32768}),
    ],
)
def test_anthropic_profile_when_effort_is_set_maps_to_thinking_budget(
    effort: str,
    expected_thinking: dict[str, str | int] | None,
) -> None:
    # Given the Anthropic native provider and enough output budget for each effort.
    provider = provider_for_name("anthropic")
    decoding = {**DECODING, "max_tokens": 40000}

    # When building a request payload with a requested reasoning effort.
    payload = provider.build_payload(
        "claude-sonnet-anchor",
        MESSAGES,
        decoding,
        "api-uncapped",
        effort=effort,
    )

    # Then effort controls the Anthropic extended-thinking block.
    if expected_thinking is None:
        assert "thinking" not in payload
        assert provider.notes(effort=effort, decodings=[decoding]) == [
            "reasoning_effort=minimal mapped to Anthropic thinking off",
        ]
    else:
        assert payload["thinking"] == expected_thinking
        assert provider.notes(effort=effort, decodings=[decoding]) == [
            (
                f"reasoning_effort={effort} mapped to Anthropic "
                f"thinking budget_tokens={expected_thinking['budget_tokens']}"
            ),
        ]


def test_anthropic_profile_when_effort_budget_exceeds_max_tokens_clamps_below_request_cap() -> None:
    # Given the Anthropic native provider and a request cap below the requested effort budget.
    provider = provider_for_name("anthropic")
    decoding = {**DECODING, "max_tokens": 10}

    # When building a request payload with xhigh reasoning effort.
    payload = provider.build_payload(
        "claude-sonnet-anchor",
        MESSAGES,
        decoding,
        "api-uncapped",
        effort="xhigh",
    )

    # Then the thinking budget is clamped below max_tokens and the note records it.
    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 9}
    assert provider.notes(effort="xhigh", decodings=[decoding]) == [
        (
            "reasoning_effort=xhigh mapped to Anthropic "
            "thinking budget_tokens=9 (clamped below max_tokens=10)"
        ),
    ]


def test_provider_profiles_when_effort_is_none_match_default_payloads() -> None:
    # Given representative provider profiles.
    providers = [
        ("local", DECODING, "answer-only"),
        ("openai-chat", DECODING, "answer-only"),
        ("openai-reasoning", DECODING, "api-uncapped"),
        ("gemini", DECODING, "answer-only"),
        ("anthropic", {**DECODING, "thinking_budget": 8}, "capped-thinking"),
    ]

    for provider_name, decoding, lane in providers:
        provider = provider_for_name(provider_name)

        # When comparing omitted effort to explicit None.
        default_payload = provider.build_payload(
            "demo-model",
            MESSAGES,
            decoding,
            lane,
        )
        none_effort_payload = provider.build_payload(
            "demo-model",
            MESSAGES,
            decoding,
            lane,
            effort=None,
        )

        # Then None is a no-op for the default path.
        assert none_effort_payload == default_payload


def test_anthropic_profile_when_parsing_response_maps_thinking_blocks() -> None:
    # Given an Anthropic Messages API response with thinking and text blocks.
    provider = provider_for_name("anthropic")

    # When parsing the response.
    parsed = provider.parse_response(
        {
            "content": [
                {"type": "thinking", "thinking": "Check each option."},
                {"type": "text", "text": "Answer: B"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 5},
        },
    )

    # Then text, reasoning, stop reason, and usage are mapped into the shared result.
    assert parsed.response_text == "Answer: B"
    assert parsed.reasoning_text == "Check each option."
    assert parsed.finish_reason == "stop"
    assert parsed.usage == {
        "prompt_tokens": 12,
        "completion_tokens": 5,
        "total_tokens": 17,
    }


def test_anthropic_profile_when_truncated_without_text_preserves_thinking() -> None:
    # Given an Anthropic response cut off while producing thinking blocks.
    provider = provider_for_name("anthropic")

    # When parsing the response.
    parsed = provider.parse_response(
        {
            "content": [{"type": "thinking", "thinking": "Still working..."}],
            "stop_reason": "max_tokens",
        },
    )

    # Then the transcript is kept and the finish reason maps to length.
    assert parsed.response_text == "Still working..."
    assert parsed.reasoning_text == "Still working..."
    assert parsed.finish_reason == "length"


def test_gemini_profile_when_building_payload_uses_openai_compat_endpoint() -> None:
    # Given the Gemini OpenAI-compatible provider.
    provider = provider_for_name("gemini")

    # When building the URL, headers, and payload.
    payload = provider.build_payload("gemini-2.5-flash", MESSAGES, DECODING, "answer-only")

    # Then Gemini keeps OpenAI-style chat params under Google's OpenAI-compatible base.
    assert payload == {
        "model": "gemini-2.5-flash",
        "messages": MESSAGES,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 16,
    }
    assert provider.endpoint_url(
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert provider.headers("sk-gemini-test") == {
        "content-type": "application/json",
        "authorization": "Bearer sk-gemini-test",
    }


def test_gemini_profile_when_effort_is_set_passes_it_through_openai_compat_body() -> None:
    # Given the Gemini OpenAI-compatible provider.
    provider = provider_for_name("gemini")

    # When building the payload with an explicit reasoning effort.
    payload = provider.build_payload(
        "gemini-2.5-pro",
        MESSAGES,
        DECODING,
        "api-uncapped",
        effort="high",
    )

    # Then Gemini receives the OpenAI-compatible passthrough field.
    assert payload == {
        "model": "gemini-2.5-pro",
        "messages": MESSAGES,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 16,
        "reasoning_effort": "high",
    }
    assert provider.notes(effort="high", decodings=[DECODING]) == [
        "reasoning_effort=high passed through Gemini OpenAI-compatible body",
    ]


def test_run_benchmark_when_provider_is_anthropic_uses_provider_adapter() -> None:
    async def scenario() -> None:
        # Given a benchmark run using the Anthropic native provider.
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            assert request.url == "https://api.anthropic.com/v1/messages"
            assert request.headers["x-api-key"] == "sk-test"
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Answer: C"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                },
            )

        # When running one item.
        record = await run_benchmark(
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            model="claude-anchor",
            items=[
                {
                    "id": "item-1",
                    "messages": MESSAGES,
                    "sampling_params": {"temperature": 0},
                    "max_tokens": 16,
                },
            ],
            provider=provider_for_name("anthropic"),
            transport=httpx.MockTransport(handler),
        )

        # Then the provider-formatted payload is sent and parsed.
        assert captured == [
            {
                "model": "claude-anchor",
                "system": "Answer briefly.",
                "messages": [{"role": "user", "content": "Pick C."}],
                "max_tokens": 16,
                "temperature": 0,
            },
        ]
        assert record["results"][0]["response_text"] == "Answer: C"
        assert record["results"][0]["usage"] == {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
        }

    asyncio.run(scenario())
