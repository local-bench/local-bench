from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from localbench.perf import perf_summary
from localbench.scoring.scorecard import scorecard_identity
from localbench.serving.model_artifact import snapshot_artifact
from localbench.serving.provenance import ServingEvidence, apply_serving_context, serving_context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    work = args.out.parent
    snapshot = work / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "model.safetensors").write_bytes(b"ground-truth-vllm-fixture")
    (snapshot / "config.json").write_text(
        json.dumps({"model_type": "qwen3_moe", "mamba_ssm_dtype": "float32"}),
        encoding="utf-8",
    )
    (snapshot / "quantization_config.json").write_text(
        json.dumps({"quant_method": "nvfp4"}),
        encoding="utf-8",
    )
    (snapshot / "chat_template.jinja").write_text("{{ messages }}", encoding="utf-8")
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    artifact = replace(
        snapshot_artifact(snapshot, run_dir=work / "artifact"),
        requested_repo="unsloth/Qwen3.6-35B-A3B-NVFP4-Fast",
        requested_revision="a" * 40,
    )
    serve_log = work / "vllm.log"
    serve_log.write_text("VLLM_BATCH_INVARIANT=1 deterministic kernels enabled", encoding="utf-8")
    digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    evidence = ServingEvidence(
        runtime="vllm",
        argv=["/opt/vllm/bin/vllm", "serve", str(snapshot), "--max-num-seqs", "1"],
        cwd=str(work),
        env_allowlist={"VLLM_BATCH_INVARIANT": "1"},
        host="127.0.0.1",
        port=8000,
        api_key_sha256=digest("fixture-key"),
        artifact=artifact,
        executable_sha256=digest("vllm-executable"),
        dll_or_so_hashes={"libvllm.so": digest("libvllm")},
        version_stdout="0.24.0",
        source_repo="https://github.com/vllm-project/vllm",
        source_commit="b" * 40,
        source_tag="v0.24.0",
        build_flags=None,
        help_text_sha256=digest("vllm-help"),
        ctx_len_configured=32768,
        parallel_slots=1,
        continuous_batching=False,
        kv_cache_quant="bfloat16",
        flash_attention="enabled",
        rope_scaling="model-default",
        reasoning="bounded-final-v2",
        reasoning_budget=None,
        reasoning_format="auto",
        health_200_at="2026-07-11T00:00:00Z",
        models_response_sha256=digest("models-response"),
        props_response_sha256=digest("props-response"),
        reported_model="fixture-vllm-model",
        smoke_chat_sha256=digest("smoke-chat"),
        owned_process_tree=["fixture-vllm-process"],
        teardown_terminated=True,
        exit_code=0,
        gpu_pids_after=[],
        server_fingerprint=digest("server-fingerprint"),
        resume_identity=digest("resume-identity"),
        model_id="fixture-vllm-model",
        serve_log_path=str(serve_log),
        device_name="NVIDIA RTX PRO 6000 Blackwell",
        driver_version="590.12",
        cuda_version="13.0",
        dtype="bfloat16",
        quantization="compressed-tensors",
        tokenize_sha256=digest("tokenize-response"),
        applied_chat_template_sha256=artifact.chat_template_digest,
        engine_version="0.24.0",
        dependency_lock_sha256=digest("dependency-lock"),
        mamba_ssm_cache_dtype="float32",
        model_config_mamba_ssm_dtype=artifact.mamba_ssm_dtype,
        deterministic_kernel_evidence=("VLLM_BATCH_INVARIANT deterministic execution",),
        deterministic_kernel_enabled=True,
        live_batch_invariant="1",
        memory_allocations={"kv_cache": 1024},
        computed_memory_fit={"fits": True},
        runtime_identity_sha256=digest("runtime-identity"),
        determinism_canary_passed=True,
    )

    record = json.loads(args.base.read_text(encoding="utf-8"))
    manifest = record["manifest"]
    # A publishable maintainer receipt is emitted from a clean checkout. The real
    # apply_serving_context writer below re-evaluates this provenance field.
    manifest.setdefault("provenance", {})["dirty_tree"] = False
    manifest["suite"]["lane"] = "bounded-final-v2"
    manifest["suite"]["tier"] = "standard"
    profile_id = manifest.get("scorecard", {}).get("execution_profile_id")
    manifest["scorecard"] = scorecard_identity(profile_id, lane_spec_id="bounded-final-v2")
    manifest["runtime"] = {
        "name": evidence.runtime,
        "version": evidence.engine_version,
        "kv_cache_quant": evidence.kv_cache_quant,
        "ctx_len_configured": evidence.ctx_len_configured,
        "parallel_slots": evidence.parallel_slots,
    }
    manifest["model"] = {
        **manifest["model"],
        "file_name": artifact.model_file.name,
        "file_sha256": artifact.file_sha256,
        "file_size_bytes": artifact.file_size_bytes,
        "format": artifact.model_format,
        "quant_label": artifact.quant_label,
    }
    for item in record["items"]:
        item.pop("server_timings", None)
    record["perf"] = perf_summary(record["items"])
    record = apply_serving_context(record, serving_context(evidence))
    args.out.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
