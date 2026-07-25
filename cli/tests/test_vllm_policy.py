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


def test_autotune_manifest_normalizes_timings_out() -> None:
    log_a = (
        "Triton autotuning for function chunk_fwd_kernel_o finished after 1.23s; "
        "best config selected: BK: 64, BV: 64, num_warps: 4, num_stages: 2\n"
        "Triton autotuning for function solve_tril finished after 0.44s; "
        "best config selected: num_warps: 8, num_stages: 3\n"
    )
    log_b = (
        "Triton autotuning for function solve_tril finished after 9.99s; "
        "best config selected: num_warps: 8, num_stages: 3\n"
        "Triton autotuning for function chunk_fwd_kernel_o finished after 77.7s; "
        "best config selected: BK: 64, BV: 64, num_warps: 4, num_stages: 2\n"
    )
    selections_a = extract_autotune_selections(log_a)
    selections_b = extract_autotune_selections(log_b)
    assert selections_a == selections_b
    assert autotune_manifest_sha256(selections_a) == autotune_manifest_sha256(selections_b)
    assert autotune_manifest_sha256(()) is None


def test_autotune_manifest_differs_when_a_config_changes() -> None:
    base = (
        "Triton autotuning for function chunk_fwd_kernel_o finished after 1s; "
        "best config selected: BK: 64, num_warps: 4\n"
    )
    changed = (
        "Triton autotuning for function chunk_fwd_kernel_o finished after 1s; "
        "best config selected: BK: 128, num_warps: 4\n"
    )
    assert autotune_manifest_sha256(
        extract_autotune_selections(base)
    ) != autotune_manifest_sha256(extract_autotune_selections(changed))


def test_resolved_backends_fail_closed_until_all_facts_affirm() -> None:
    partial = parse_resolved_backends(
        "INFO [__init__.py:974] Using CutlassNvFp4LinearKernel for NVFP4 GEMM\n"
        "INFO [cuda.py:476] Using TRITON_ATTN attention backend out of potential backends\n"
    )
    assert partial.nvfp4_linear_kernel == "CutlassNvFp4LinearKernel"
    assert partial.attention_backend == "TRITON_ATTN"
    assert not partial.satisfied()

    complete = parse_resolved_backends(
        "INFO Using CutlassNvFp4LinearKernel for NVFP4 GEMM\n"
        "INFO Using TRITON_ATTN attention backend out of potential backends\n"
        "INFO Using Triton/FLA GDN prefill kernel for hybrid layers\n"
        "INFO VllmConfig(model_config=..., enforce_eager=True, ...)\n"
    )
    assert complete.satisfied()
    assert complete.as_json()["satisfied"] is True


def test_resolved_backends_reject_wrong_kernel() -> None:
    wrong = parse_resolved_backends(
        "INFO Using FlashInferCutlassNvFp4LinearKernel for NVFP4 GEMM\n"
        "INFO Using TRITON_ATTN attention backend\n"
        "INFO Using Triton/FLA GDN prefill kernel\n"
        "INFO enforce_eager=True\n"
    )
    assert wrong.nvfp4_linear_kernel == "FlashInferCutlassNvFp4LinearKernel"
    assert not wrong.satisfied()
