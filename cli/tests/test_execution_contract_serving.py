from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.execution_contract import (
    ResolvedExecutionContract,
    execution_contract_record,
)
from localbench.serving.assembly import (
    bench_config,
    resolve_serving_execution_profile,
)
from localbench.serving.fingerprint import resume_identity
from localbench.serving.model_artifact import ModelArtifact
from localbench.serving.options import ServeBenchOptions

_MODEL_SHA: Final = "1" * 64
_TEMPLATE_SHA: Final = "2" * 64
_EFFECTIVE_SHA: Final = "3" * 64


def _contract() -> ResolvedExecutionContract:
    return ResolvedExecutionContract(
        profile_id="generic_think_tags_8192_v1",
        selection_policy_id="gguf-effective-template-v1",
        selection_reason="gguf_generic_think_confirmed",
        template_source="gguf-default",
        raw_template_sha256=_TEMPLATE_SHA,
        effective_template_sha256=_EFFECTIVE_SHA,
        chat_template_kwargs={"enable_thinking": True},
        answer_stops=("<|im_end|>",),
        reasoning_mode="generic_think",
        reasoning_budget=8192,
        model_file_sha256=_MODEL_SHA,
        runtime_probe={"passed": True},
    )


def test_serving_resolves_one_contract_after_artifact_resolution(tmp_path: Path) -> None:
    # Given: a repo-only GGUF artifact whose embedded template supports thinking.
    metadata: JsonObject = {
        "tokenizer.chat_template": "{% if thinking %}<think>{% endif %}<|im_end|>",
        "tokenizer.ggml.eos_token_id": 0,
        "tokenizer.ggml.tokens": ["<|im_end|>"],
    }
    metadata_path = tmp_path / "gguf_metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    artifact = ModelArtifact(
        model_file=tmp_path / "model.gguf",
        file_sha256=_MODEL_SHA,
        file_size_bytes=1,
        gguf_metadata_sha256="4" * 64,
        tokenizer_digest="5" * 64,
        chat_template_digest=_TEMPLATE_SHA,
        gguf_metadata_path=metadata_path,
        model_family="qwen",
        quant_label="Q5_K_M",
    )
    options = ServeBenchOptions(
        runtime="llama.cpp",
        model_file=artifact.model_file,
        model_ref=None,
        model_id="demo",
        server_bin=tmp_path / "llama-server.exe",
        ctx=32768,
        determinism="strict",
        tier="quick",
        bench="all",
        lane="bounded-final-v1",
        profile="auto",
        seed=1234,
        out=tmp_path / "run",
        gguf_repo_only=True,
    )

    # When: serving resolves after the artifact and builds the inner run config.
    runtime = resolve_serving_execution_profile(options, artifact)
    configured = bench_config(
        options,
        tmp_path / "localbench-run.json",
        "secret",
        49152,
        resolved_profile=runtime,
    )

    # Then: the exact immutable runtime is threaded without profile re-derivation.
    assert runtime is not None
    assert runtime.contract.model_file_sha256 == _MODEL_SHA
    assert configured.profile == "generic_think_tags_8192_v1"
    assert configured.resolved_bounded_profile is runtime


def test_serving_resume_identity_includes_execution_contract() -> None:
    # Given: identical server inputs and two score-affecting execution contracts.
    common = {
        "model_file_sha256": _MODEL_SHA,
        "executable_sha256": "4" * 64,
        "argv": ["llama-server", "--port", "49152"],
        "env_allowlist": {"CUDA_VISIBLE_DEVICES": "0"},
        "ctx": 32768,
        "kv_cache_quant": "k=f16,v=f16",
        "parallel_slots": 1,
        "flash_attention": "on",
        "chat_template_digest": _TEMPLATE_SHA,
    }

    # When: resume identities bind the corresponding structured contracts.
    generic = resume_identity(
        **common,
        execution_contract=execution_contract_record(_contract()),
    )
    answer_only = resume_identity(
        **common,
        execution_contract=execution_contract_record(
            replace(
                _contract(),
                profile_id="answer_only_v1",
                reasoning_mode="disabled",
                reasoning_budget=None,
            ),
        ),
    )

    # Then: identical launch inputs cannot resume across profile contracts.
    assert generic != answer_only
