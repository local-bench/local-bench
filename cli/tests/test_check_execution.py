from __future__ import annotations

import hashlib
from pathlib import Path

from localbench._types import JsonObject
from localbench.check.budget import generation_parameters, normalize_generation
from localbench.check.execution import collect_lce_identity


def test_lce_identity_hashes_the_exact_binaries_and_captures_props(tmp_path: Path) -> None:
    for name, content in (
        ("llama-server.exe", b"server"),
        ("llama.dll", b"llama"),
        ("ggml-cuda.dll", b"cuda"),
    ):
        _ = (tmp_path / name).write_bytes(content)
    props: JsonObject = {"default_generation_settings": {"temp": 0}, "total_slots": 1}

    identity = collect_lce_identity(tmp_path, backend="CUDA", props=props, driver="999.1")

    assert identity["edition"] == "LCE-1"
    assert identity["build"] == "b10076"
    assert identity["commit"] == "305ba51"
    assert identity["cuda_version"] == "13.3"
    assert identity["flags"] == ["-ctk", "f16", "-ctv", "f16", "--fit", "off", "-lv", "4"]
    binaries = identity["binaries"]
    assert isinstance(binaries, dict)
    assert binaries["llama-server.exe"] == hashlib.sha256(b"server").hexdigest()
    assert identity["effective_server_config"] == props


def test_generation_parameters_are_explicit_and_use_locked_module_budgets() -> None:
    assert generation_parameters("coding") == {
        "answer_budget_tokens": 2048,
        "headroom_tokens": 256,
        "max_tokens": 6400,
        "seed": 1234,
        "temperature": 0,
        "think_budget_tokens": 4096,
    }
    assert generation_parameters("tools-stateful")["max_tokens"] == 4864


def test_budget_normalization_force_closes_without_rerun_and_scores_length_as_is() -> None:
    forced = normalize_generation(
        text="<think>unfinished",
        generated_token_ids=list(range(4096)),
        finish_reason="length",
        think_open="<think>",
        think_close="</think>",
    )

    forced_text = forced["text"]
    assert isinstance(forced_text, str) and forced_text.endswith("</think>")
    assert forced["forced_close"] is True
    assert forced["protocol_flag"] == "think-budget-exhausted"
    assert forced["finish_reason"] == "length"
    assert forced["rerun"] is False

    malformed = normalize_generation(
        text="answer without markers",
        generated_token_ids=[1, 2],
        finish_reason="stop",
        think_open="<think>",
        think_close="</think>",
    )
    assert malformed["protocol_flag"] == "think-markers-absent"
    assert malformed["text"] == "answer without markers"
