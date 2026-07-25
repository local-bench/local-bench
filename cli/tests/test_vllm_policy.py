from __future__ import annotations

from localbench.serving.vllm_policy import (
    VLLM_BATCH_INVARIANT_POLICY_ID,
    VLLM_GDN_POLICY_ID,
    autotune_manifest_sha256,
    extract_autotune_selections,
    is_gdn_architecture,
    parse_resolved_backends,
    policy_env_pins,
    resolve_model_text_config,
    select_vllm_policy,
)


def test_text_config_overlay_nested_wins() -> None:
    config = resolve_model_text_config(
        {
            "model_type": "qwen3_vl",
            "torch_dtype": "float32",
            "text_config": {"torch_dtype": "bfloat16", "layer_types": ["full_attention"]},
        }
    )
    assert config["torch_dtype"] == "bfloat16"
    assert config["model_type"] == "qwen3_vl"
    assert config["layer_types"] == ["full_attention"]


def test_gdn_detection_requires_text_config_overlay() -> None:
    # The real unsloth Qwen3.6 NVFP4 wrapper config keeps layer_types only
    # under text_config; a naive top-level read would misclassify the model
    # as batch-invariant capable and the engine would refuse to start.
    wrapper = {
        "architectures": ["Qwen3VLForConditionalGeneration"],
        "text_config": {
            "layer_types": ["linear_attention"] * 48 + ["full_attention"] * 16,
        },
    }
    assert is_gdn_architecture(resolve_model_text_config(wrapper))
    assert select_vllm_policy(resolve_model_text_config(wrapper)) == VLLM_GDN_POLICY_ID


def test_full_attention_model_selects_batch_invariant_policy() -> None:
    config = {"layer_types": ["full_attention"] * 32}
    assert select_vllm_policy(resolve_model_text_config(config)) == (
        VLLM_BATCH_INVARIANT_POLICY_ID
    )
    assert config_missing_layer_types_selects_batch_invariant()


def config_missing_layer_types_selects_batch_invariant() -> bool:
    return (
        select_vllm_policy(resolve_model_text_config({"num_hidden_layers": 32}))
        == VLLM_BATCH_INVARIANT_POLICY_ID
    )


def test_policy_env_pins_are_disjoint_on_the_batch_invariant_marker() -> None:
    assert policy_env_pins(VLLM_BATCH_INVARIANT_POLICY_ID)["VLLM_BATCH_INVARIANT"] == "1"
    assert "VLLM_BATCH_INVARIANT" not in policy_env_pins(VLLM_GDN_POLICY_ID)
    assert policy_env_pins(VLLM_GDN_POLICY_ID)["TRITON_PRINT_AUTOTUNING"] == "1"


# Multi-line record format qualified live at gate 0 (vLLM 0.25.1, RTX 5090).
_AUTOTUNE_RECORD = (
    "(EngineCore pid=186692) Triton autotuning for function chunk_fwd_kernel_o,\n"
    "(EngineCore pid=186692) with key as (48, 128, 128, 64, 'torch.bfloat16'),\n"
    "(EngineCore pid=186692) finished after {seconds}s,\n"
    "(EngineCore pid=186692) best config selected: BK: {bk}, BV: 64, "
    "num_warps: 4, num_ctas: 1, num_stages: 3, maxnreg: None;\n"
)


def test_autotune_manifest_normalizes_timings_out() -> None:
    log_a = _AUTOTUNE_RECORD.format(seconds="9.19", bk=64)
    log_b = _AUTOTUNE_RECORD.format(seconds="0.42", bk=64)
    selections_a = extract_autotune_selections(log_a)
    selections_b = extract_autotune_selections(log_b)
    assert len(selections_a) == 1
    assert selections_a[0][0] == "chunk_fwd_kernel_o"
    assert "torch.bfloat16" in selections_a[0][1]
    assert selections_a == selections_b
    assert autotune_manifest_sha256(selections_a) == autotune_manifest_sha256(selections_b)
    assert autotune_manifest_sha256(()) is None


def test_autotune_manifest_differs_when_a_config_changes() -> None:
    base = _AUTOTUNE_RECORD.format(seconds="1.0", bk=64)
    changed = _AUTOTUNE_RECORD.format(seconds="1.0", bk=128)
    assert autotune_manifest_sha256(
        extract_autotune_selections(base)
    ) != autotune_manifest_sha256(extract_autotune_selections(changed))


# When --attention-backend is pinned, 0.25.1 emits no selector line; the
# affirmative evidence is the API server's non-default-args echo (verbatim
# from the gate-0 log).
_PINNED_ARGS_LINE = (
    "(APIServer pid=186592) INFO 07-26 08:24:36 [api_utils.py:273] non-default "
    "args: {'return_tokens_as_token_ids': True, 'enforce_eager': True, "
    "'attention_backend': 'TRITON_ATTN', 'linear_backend': 'cutlass', "
    "'gdn_prefill_backend': 'triton'}\n"
)


def test_resolved_backends_fail_closed_until_all_facts_affirm() -> None:
    partial = parse_resolved_backends(
        "INFO [__init__.py:974] Using CutlassNvFp4LinearKernel for NVFP4 GEMM\n"
        + _PINNED_ARGS_LINE
    )
    assert partial.nvfp4_linear_kernel == "CutlassNvFp4LinearKernel"
    assert partial.attention_backend == "TRITON_ATTN"
    assert partial.eager_mode is True
    assert not partial.satisfied()  # GDN prefill line still missing

    complete = parse_resolved_backends(
        "INFO Using CutlassNvFp4LinearKernel for NVFP4 GEMM\n"
        + _PINNED_ARGS_LINE
        + "INFO [qwen_gdn_linear_attn.py:228] Using Triton/FLA GDN prefill "
        "kernel (requested=triton, head_k_dim=128).\n"
    )
    assert complete.gdn_prefill_backend == "Triton/FLA"
    assert complete.satisfied()
    assert complete.as_json()["satisfied"] is True


def test_resolved_backends_accept_auto_selector_line_too() -> None:
    auto_style = parse_resolved_backends(
        "INFO Using TRITON_ATTN attention backend out of potential backends\n"
        "INFO Initializing ... enforce_eager=True, kv_cache_dtype=bfloat16\n"
    )
    assert auto_style.attention_backend == "TRITON_ATTN"
    assert auto_style.eager_mode is True


def test_resolved_backends_reject_wrong_kernel() -> None:
    wrong = parse_resolved_backends(
        "INFO Using FlashInferCutlassNvFp4LinearKernel for NVFP4 GEMM\n"
        + _PINNED_ARGS_LINE
        + "INFO Using Triton/FLA GDN prefill kernel (requested=triton).\n"
    )
    assert wrong.nvfp4_linear_kernel == "FlashInferCutlassNvFp4LinearKernel"
    assert not wrong.satisfied()


def test_jit_inference_event_extraction() -> None:
    from localbench.serving.vllm_policy import extract_jit_inference_events

    log = (
        "WARNING [jit_monitor.py:123] Triton kernel JIT compilation during "
        "inference: _triton_mrope_forward. This causes a latency spike; "
        "consider extending warmup to cover this shape/config.\n"
        "INFO unrelated line\n"
        "WARNING Triton kernel JIT compilation during inference: solve_tril.\n"
    )
    assert extract_jit_inference_events(log) == ("_triton_mrope_forward", "solve_tril")
    assert extract_jit_inference_events("") == ()
