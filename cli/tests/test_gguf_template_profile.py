from __future__ import annotations

import hashlib
from typing import Final

import pytest

from localbench._types import JsonObject
from localbench.gguf_template import (
    GGUF_GENERIC_THINK_CONFIRMED,
    GGUF_NONTHINKING_CONFIRMED,
    LLAMA_BUILTIN_CHATML_NONTHINKING,
    TEMPLATE_METADATA_MALFORMED,
    THINKING_STOP_UNRESOLVED,
    UNSUPPORTED_GEMMA_CHANNEL,
    load_gguf_template_facade,
    static_profile_candidate,
)

_IM_END: Final = "<|im_end|>"
_REAL_QWOPUS_TEMPLATE_TAIL: Final = """\
{%- if message.role == "user" %}
    {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>\n' }}
{%- elif message.role == "assistant" %}
    {%- if '</think>' in content %}
        {%- set reasoning_content = content.split('</think>')[0].split('<think>')[-1] %}
    {%- endif %}
    {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>\n' }}
{%- endif %}
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {%- if enable_thinking is defined and enable_thinking is false %}
        {{- '<think>\n\n</think>\n\n' }}
    {%- else %}
        {{- '<think>\n' }}
    {%- endif %}
{%- endif %}
"""


def _metadata(
    template: str,
    *,
    eos_token_id: int | bool = 0,
    tokens: list[str | int] | None = None,
) -> JsonObject:
    return {
        "tokenizer.chat_template": template,
        "tokenizer.ggml.eos_token_id": eos_token_id,
        "tokenizer.ggml.tokens": [_IM_END] if tokens is None else tokens,
    }


def test_static_candidate_confirms_trimmed_real_qwopus_template() -> None:
    # Given: the score-invalidated Qwopus artifact's real template tail and EOS token.
    metadata = _metadata(_REAL_QWOPUS_TEMPLATE_TAIL)

    # When: the embedded GGUF template is inspected before runtime probing.
    candidate = static_profile_candidate(metadata)

    # Then: static evidence proposes bounded generic thinking with full template identity.
    assert candidate.state == "thinking"
    assert candidate.reason_code == GGUF_GENERIC_THINK_CONFIRMED
    assert candidate.template_source == "gguf-default"
    assert candidate.template_sha256 == hashlib.sha256(
        _REAL_QWOPUS_TEMPLATE_TAIL.encode("utf-8"),
    ).hexdigest()
    assert candidate.introspection is not None
    assert candidate.introspection.answer_stop == (_IM_END,)
    assert candidate.introspection.chat_template_kwargs == {"enable_thinking": True}


def test_static_candidate_aborts_when_thinking_template_only_references_eos_variable() -> None:
    # Given: thinking syntax whose assistant terminator is not recoverable as a literal.
    metadata = _metadata(
        "{% if enable_thinking %}<think>{% endif %}{{ eos_token }}",
    )

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: absence of a safe answer stop stays unresolved instead of degrading.
    assert candidate.state == "unresolved"
    assert candidate.reason_code == THINKING_STOP_UNRESOLVED


def test_static_candidate_documents_textual_dead_branch_semantics() -> None:
    # Given: think tags exist only in a Jinja comment while the EOS token is literal.
    metadata = _metadata("{# dead branch: <think></think> #}<|im_end|>")

    # When: the intentionally textual static matcher runs.
    candidate = static_profile_candidate(metadata)

    # Then: it proposes thinking so the authoritative runtime probe can refute it.
    assert candidate.state == "thinking"
    assert candidate.reason_code == GGUF_GENERIC_THINK_CONFIRMED


def test_static_candidate_rejects_tool_use_only_template_as_authority() -> None:
    # Given: GGUF metadata contains only a named tools template.
    metadata: JsonObject = {
        "tokenizer.chat_template.tool_use": "<think><|im_end|>",
        "tokenizer.ggml.eos_token_id": 0,
        "tokenizer.ggml.tokens": [_IM_END],
    }

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: the named variant is retained as evidence but cannot select a profile.
    assert candidate.state == "unresolved"
    assert candidate.reason_code == TEMPLATE_METADATA_MALFORMED
    assert candidate.template_source == "gguf-tool-use-only"
    assert candidate.template_sha256 == hashlib.sha256(
        b"<think><|im_end|>",
    ).hexdigest()


def test_static_candidate_leaves_absent_template_for_builtin_chatml_probe() -> None:
    # Given: the GGUF has no default or named chat template.
    metadata: JsonObject = {}

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: only the runtime may confirm llama.cpp's builtin ChatML fallback.
    assert candidate.state == "unresolved"
    assert candidate.reason_code == LLAMA_BUILTIN_CHATML_NONTHINKING
    assert candidate.template_source == "absent"
    assert candidate.template_sha256 is None
    assert candidate.introspection is None


def test_static_candidate_rejects_truncated_jinja_template() -> None:
    # Given: a syntactically truncated default template.
    metadata = _metadata("{% if enable_thinking %}<think><|im_end|>")

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: malformed template metadata cannot become publishable evidence.
    assert candidate.state == "unresolved"
    assert candidate.reason_code == TEMPLATE_METADATA_MALFORMED
    assert candidate.introspection is None


def test_static_candidate_confirms_granite_thinking_kwarg() -> None:
    # Given: a valid template whose native control is Granite's `thinking` kwarg.
    metadata = _metadata(
        "{% if thinking %}<think>{% endif %}<|im_end|>",
    )

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: the exact activation kwarg is preserved for the contract.
    assert candidate.state == "thinking"
    assert candidate.reason_code == GGUF_GENERIC_THINK_CONFIRMED
    assert candidate.introspection is not None
    assert candidate.introspection.chat_template_kwargs == {"thinking": True}


def test_static_candidate_fails_closed_for_gemma_channel() -> None:
    # Given: a valid Gemma channel template, unsupported in this release.
    metadata = _metadata(
        "{% if enable_thinking %}<|channel>thought{% endif %}<|im_end|>",
    )

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: the release refuses to reinterpret channel reasoning as generic tags.
    assert candidate.state == "unresolved"
    assert candidate.reason_code == UNSUPPORTED_GEMMA_CHANNEL


@pytest.mark.parametrize(
    ("eos_token_id", "tokens"),
    [
        (True, [_IM_END]),
        (-1, [_IM_END]),
        (2, [_IM_END]),
        (0, [7]),
    ],
)
def test_static_candidate_rejects_invalid_eos_token_metadata(
    eos_token_id: int | bool,
    tokens: list[str | int],
) -> None:
    # Given: an invalid token id or non-string token at the selected position.
    metadata = _metadata(
        "<think><|im_end|>",
        eos_token_id=eos_token_id,
        tokens=tokens,
    )

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: bool, negative, out-of-range, and non-string token metadata fail closed.
    assert candidate.state == "unresolved"
    assert candidate.reason_code == TEMPLATE_METADATA_MALFORMED


def test_facade_deduplicates_eos_and_eot_tokens() -> None:
    # Given: EOS and EOT ids point to the same non-empty terminator.
    metadata = _metadata("<think><|im_end|>")
    metadata["tokenizer.ggml.eot_token_id"] = 0

    # When: the GGUF facade resolves token ids to strings.
    facade, source = load_gguf_template_facade(metadata)

    # Then: duplicate terminators are represented once for downstream introspection.
    assert source == "gguf-default"
    assert facade is not None
    assert facade.eos_token == _IM_END
    assert facade.eot_token is None


def test_static_candidate_confirms_plain_template_with_literal_stop() -> None:
    # Given: a valid non-thinking template with a literal assistant terminator.
    metadata = _metadata("<|im_start|>assistant\n<|im_end|>")

    # When: the static candidate is derived.
    candidate = static_profile_candidate(metadata)

    # Then: static evidence proposes the non-thinking profile for probe verification.
    assert candidate.state == "nonthinking"
    assert candidate.reason_code == GGUF_NONTHINKING_CONFIRMED
