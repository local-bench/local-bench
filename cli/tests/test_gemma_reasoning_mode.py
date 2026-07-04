"""Static and wiring tests for Gemma4 native reasoning mode."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from localbench._types import JsonValue
from localbench.budget_forcing import QWEN_FORCING, answer_budget_for, render_qwen3_chat_prompt
from localbench.prompt_rendering import HfChatPromptRenderer
from localbench.reasoning_registry import GEMMA4_LEAK_REGEXES


def _item(think_budget: int | None = 8192, max_tokens: int = 16384) -> dict:
    item: dict = {
        "id": "item-1",
        "messages": [{"role": "user", "content": "Pick C"}],
        "sampling_params": {"temperature": 0},
        "max_tokens": max_tokens,
    }
    if think_budget is not None:
        item["think_budget"] = think_budget
    return item


@pytest.mark.parametrize("bad_cap", [None, "16384"])
def test_answer_budget_fails_closed_when_max_tokens_is_missing_or_non_int(
    bad_cap: str | None,
) -> None:
    item = _item(think_budget=8192, max_tokens=16384)
    if bad_cap is None:
        item.pop("max_tokens")
    else:
        item["max_tokens"] = bad_cap

    with pytest.raises(ValueError, match="max_tokens"):
        answer_budget_for(item, 8192)


def test_qwen_forcing_format_is_byte_equivalent_to_legacy_two_pass_wire_contract() -> None:
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    prompt = render_qwen3_chat_prompt(messages)

    assert prompt == (
        "<|im_start|>system\nS<|im_end|>\n"
        "<|im_start|>user\nU<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    assert QWEN_FORCING.close == "</think>"
    assert QWEN_FORCING.forced_close == "\n</think>\n\n"
    assert QWEN_FORCING.answer_stop == ("<|im_end|>",)
    assert f"{prompt}<think>\nlegacy reasoning{QWEN_FORCING.forced_close}" == (
        "<|im_start|>system\nS<|im_end|>\n"
        "<|im_start|>user\nU<|im_end|>\n"
        "<|im_start|>assistant\n"
        "<think>\nlegacy reasoning\n</think>\n\n"
    )


def test_gemma4_static_render_fixture_shape_and_activation_kwargs() -> None:
    """Gemma4 static fixture sha256: e48317a2cde3f91372655fa270f5ef38c71be650525c691263cb5ed22f681405."""

    class RecordingTokenizer:
        def __init__(self) -> None:
            self.tokenizer = _load_gemma4_tokenizer()
            self.calls: list[dict[str, JsonValue]] = []

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
                    "messages": [dict(message) for message in conversation],
                    "tokenize": tokenize,
                    "add_generation_prompt": add_generation_prompt,
                    "kwargs": dict(kwargs),
                },
            )
            return self.tokenizer.apply_chat_template(
                conversation,
                tokenize=tokenize,
                add_generation_prompt=add_generation_prompt,
                **kwargs,
            )

    tokenizer = RecordingTokenizer()
    renderer = HfChatPromptRenderer(tokenizer=tokenizer, activation="gemma4")

    rendered = renderer.render([{"role": "user", "content": "Pick C"}])

    assert tokenizer.calls[0]["kwargs"] == {"enable_thinking": True}
    assert "<|turn>" in rendered
    assert "<turn|>" in rendered
    assert rendered.count("<bos>") == 1
    assert "<|channel>thought\n<channel|>" not in rendered
    assert GEMMA4_LEAK_REGEXES == (
        r"<\|channel>",
        r"<channel\|>",
        r"<\|think\|>",
        r"<turn\|>",
    )
    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == (
        "e48317a2cde3f91372655fa270f5ef38c71be650525c691263cb5ed22f681405"
    )


def _load_gemma4_tokenizer():
    from transformers import AutoTokenizer

    model_id = "unsloth/gemma-4-31B-it"
    revision = "a1c85d1c2db7dcd15c41ad4082955240a9465743"
    try:
        return AutoTokenizer.from_pretrained(model_id, local_files_only=True, revision=revision)
    except OSError:
        snapshot = (
            Path.home()
            / ".cache"
            / "huggingface"
            / "hub"
            / "models--unsloth--gemma-4-31B-it"
            / "snapshots"
            / revision
        )
        return AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
