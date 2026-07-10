from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.bounded_final_profiles import (
    BoundedFinalProfileRequest,
    resolve_bounded_final_profile,
)
from localbench.serving import assembly
from localbench.serving.bench import build_orchestrate_config
from localbench.serving.options import ServeBenchOptions
from serving_helpers import serving_evidence

PINNED_REVISION = "c1899de28999fdb6c871a5a1c94338267a79f43f"


class _TemplateTokenizer:
    def __init__(self) -> None:
        self.chat_template = (
            "{% for message in messages %}<|im_start|>{{ message['role'] }}\n"
            "{{ message['content'] }}<|im_end|>{% endfor %}"
            "{% if enable_thinking %}<think>{% endif %}"
        )
        self.eos_token = "<|im_end|>"
        self.additional_special_tokens: tuple[str, ...] = ()
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
        return "<|im_start|>assistant\n"


def test_profile_resolution_passes_requested_hf_revision_to_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_load(
        hf_model_id: str,
        activation: str | None = None,
        revision: str | None = None,
    ) -> _TemplateTokenizer:
        calls.append((hf_model_id, activation, revision))
        return _TemplateTokenizer()

    monkeypatch.setattr(
        "localbench.bounded_final_profiles.load_hf_chat_template_tokenizer",
        fake_load,
    )

    resolved = resolve_bounded_final_profile(
        BoundedFinalProfileRequest(
            profile="auto",
            hf_model_id="Qwen/Qwen3-0.6B",
            hf_revision=PINNED_REVISION,
        ),
    )

    assert resolved.entry.id == "generic_think_tags_8192_v1"
    assert calls == [("Qwen/Qwen3-0.6B", None, PINNED_REVISION)]


def test_serving_bench_config_threads_hf_revision_to_inner_orchestrate_config(
    tmp_path: Path,
) -> None:
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=tmp_path / "model.gguf",
        model_ref=None,
        model_id="gemma",
        server_bin=tmp_path / "llama-server.exe",
        ctx=32768,
        determinism="strict",
        tier="standard",
        bench="ifbench",
        lane="bounded-final-v2",
        profile="answer_only_v1",
        seed=1234,
        out=tmp_path / "run",
        reasoning_activation="gemma4",
        hf_model_id="unsloth/gemma-4-12b-it",
        hf_revision=PINNED_REVISION,
    )
    evidence = serving_evidence(tmp_path, teardown_terminated=True)

    bench_run = assembly.bench_config(
        options,
        tmp_path / "localbench-run.json",
        "secret",
        49152,
    )
    inner = build_orchestrate_config(bench_run, evidence)

    assert bench_run.hf_revision == PINNED_REVISION
    assert inner.hf_revision == PINNED_REVISION
