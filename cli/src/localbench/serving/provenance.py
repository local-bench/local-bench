from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject
from localbench.serving.model_artifact import ModelArtifact

DETERMINISM_POLICY_ID = "gpu-greedy-single-slot-v1"
_PINNED_LEVEL = "orchestrated-pinned-artifacts-v1"
_PROCESS_LEVEL = "orchestrated-process-v1"


@dataclass(frozen=True, slots=True)
class ServingEvidence:
    runtime: str
    argv: list[str]
    cwd: str
    env_allowlist: dict[str, str]
    host: str
    port: int
    api_key_sha256: str
    artifact: ModelArtifact
    executable_sha256: str | None
    dll_or_so_hashes: dict[str, str]
    version_stdout: str | None
    source_repo: str
    source_commit: str | None
    source_tag: str | None
    build_flags: str | None
    help_text_sha256: str | None
    ctx_len_configured: int
    parallel_slots: int
    continuous_batching: bool
    kv_cache_quant: str
    flash_attention: str
    rope_scaling: str
    reasoning: str
    reasoning_budget: int | None
    reasoning_format: str
    health_200_at: str
    models_response_sha256: str
    props_response_sha256: str
    reported_model: str
    smoke_chat_sha256: str
    owned_process_tree: list[str]
    teardown_terminated: bool
    exit_code: int | None
    gpu_pids_after: list[int]
    server_fingerprint: str
    resume_identity: str
    model_id: str
    serve_log_path: str
    device_name: str | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    dtype: str | None = None
    quantization: str | None = None
    tokenize_sha256: str | None = None
    applied_chat_template_sha256: str | None = None
    engine_version: str | None = None
    dependency_lock_sha256: str | None = None
    mamba_ssm_cache_dtype: str | None = None
    model_config_mamba_ssm_dtype: str | None = None
    numeric_deviations: tuple[str, ...] = ()
    deterministic_kernel_evidence: tuple[str, ...] = ()
    deterministic_kernel_enabled: bool = False
    live_batch_invariant: str | None = None
    memory_allocations: JsonObject | None = None
    computed_memory_fit: JsonObject | None = None
    runtime_identity_sha256: str | None = None
    determinism_canary_passed: bool = False
    resolved_server_config: JsonObject | None = None
    installed_package_tree_sha256: str | None = None
    run_seed: int = 1234


@dataclass(frozen=True, slots=True)
class ServingRunContext:
    block: JsonObject
    determinism_policy: JsonObject
    server_fingerprint: str
    trust_tier: str
    verification_level: str
    blocking_reasons: tuple[str, ...]
    publishable: bool


def determinism_policy(*, runtime: str, seed: int) -> JsonObject:
    server: JsonObject = {
        "parallel_slots": 1,
        "continuous_batching": False,
    }
    if runtime == "vllm":
        server.update(
            {
                "vllm_max_num_seqs": 1,
                "vllm_batch_invariant": True,
            }
        )
    elif runtime == "sglang":
        server["sglang_deterministic_inference"] = True
    elif runtime == "llama.cpp":
        server["llama_cont_batching"] = False
    return {
        "policy_id": DETERMINISM_POLICY_ID,
        "claim": "best-effort same-stack reproducibility; not bitwise cross-stack determinism",
        "client": {"temperature": 0, "top_k": 1, "seed": seed, "concurrency": 1},
        "server": server,
        "scope": [
            "same model artifact hash",
            "same runtime binary/container digest",
            "same GPU architecture",
            "same driver/runtime family",
            "same serve flags",
            "same localbench suite hash",
        ],
        "known_limits": [
            "GPU floating-point non-associativity",
            "kernel/library changes",
            "driver changes",
            "batching/scheduler changes",
            "timeout/VRAM pressure effects",
        ],
    }


def serving_context(evidence: ServingEvidence) -> ServingRunContext:
    blocking = _blocking_reasons(evidence)
    verification_level = _PINNED_LEVEL if blocking == [] else _PROCESS_LEVEL
    return ServingRunContext(
        block=_serving_block(evidence, verification_level),
        determinism_policy=determinism_policy(
            runtime=evidence.runtime, seed=evidence.run_seed
        ),
        server_fingerprint=evidence.server_fingerprint,
        trust_tier=verification_level,
        verification_level=verification_level,
        blocking_reasons=tuple(blocking),
        publishable=blocking == [],
    )


def apply_serving_context(record: JsonObject, context: ServingRunContext) -> JsonObject:
    updated = json.loads(json.dumps(record, ensure_ascii=False))
    if not isinstance(updated, dict):
        updated = {}
    manifest = _object(updated.setdefault("manifest", {}))
    sampling = _object(manifest.setdefault("sampling", {}))
    integrity = _object(manifest.setdefault("integrity", {}))
    sampling["determinism_policy"] = context.determinism_policy
    integrity["blocking_reasons"] = _dedupe(
        [
            *_string_list(integrity.get("blocking_reasons")),
            *_repo_blocking_reasons(manifest),
            *context.blocking_reasons,
        ],
    )
    integrity["publishable"] = integrity["blocking_reasons"] == []
    updated["manifest"] = manifest
    updated["serving"] = context.block
    runtime = str(context.block.get("runtime", "unknown")).replace(".", "_")
    updated["serving_mode"] = f"orchestrated_{runtime}"
    return updated


def _serving_block(evidence: ServingEvidence, verification_level: str) -> JsonObject:
    return {
        "runtime": evidence.runtime,
        "verification_level": verification_level,
        "trust_tier": verification_level,
        "launch": {
            "argv": sanitize_launch_argv(evidence.argv),
            "cwd_sha256": _text_sha256(evidence.cwd),
            "path_identities": {
                "server": {
                    "basename": _path_basename(evidence.argv[0])
                    if evidence.argv
                    else "",
                    "sha256": evidence.executable_sha256,
                },
                "model": {
                    "basename": evidence.artifact.model_file.name,
                    "sha256": evidence.artifact.file_sha256,
                },
            },
            "env_allowlist": evidence.env_allowlist,
            "host": evidence.host,
            "port": evidence.port,
            "api_key_sha256": evidence.api_key_sha256,
        },
        "artifact": {
            "kind": "native-binary",
            "container_image_digest": None,
            "executable_sha256": evidence.executable_sha256,
            "dll_or_so_hashes": evidence.dll_or_so_hashes,
            "version_stdout": evidence.version_stdout,
            "source_repo": evidence.source_repo,
            "source_commit": evidence.source_commit,
            "source_tag": evidence.source_tag,
            "build_flags": evidence.build_flags,
            "help_text_sha256": evidence.help_text_sha256,
            "server_reported_package_version": evidence.engine_version,
            "venv_dependency_lock_sha256": evidence.dependency_lock_sha256,
            "runtime_identity_sha256": evidence.runtime_identity_sha256,
            "installed_package_tree_sha256": evidence.installed_package_tree_sha256,
        },
        "resolved_runtime": {
            "ctx_len_configured": evidence.ctx_len_configured,
            "parallel_slots": evidence.parallel_slots,
            "continuous_batching": evidence.continuous_batching,
            "kv_cache_quant": evidence.kv_cache_quant,
            "mamba_ssm_cache_dtype": evidence.mamba_ssm_cache_dtype,
            "model_config_mamba_ssm_dtype": evidence.model_config_mamba_ssm_dtype,
            "numeric_deviations": list(evidence.numeric_deviations),
            "flash_attention": evidence.flash_attention,
            "rope_scaling": evidence.rope_scaling,
            "reasoning": {
                "mode": evidence.reasoning,
                "budget": evidence.reasoning_budget,
                "format": evidence.reasoning_format,
            },
            "chat_template_digest": evidence.artifact.chat_template_digest,
            "dtype": evidence.dtype,
            "quantization": evidence.quantization,
            "device_name": evidence.device_name,
            "driver_version": evidence.driver_version,
            "cuda_version": evidence.cuda_version,
            "server_reported_config": evidence.resolved_server_config or {},
        },
        "readiness_evidence": {
            "health_200_at": evidence.health_200_at,
            "models_response_sha256": evidence.models_response_sha256,
            "props_response_sha256": evidence.props_response_sha256,
            "reported_model": evidence.reported_model,
            "smoke_chat_sha256": evidence.smoke_chat_sha256,
            "tokenize_sha256": evidence.tokenize_sha256,
            "applied_chat_template_sha256": evidence.applied_chat_template_sha256,
        },
        "teardown_evidence": {
            "owned_process_tree": evidence.owned_process_tree,
            "terminated": evidence.teardown_terminated,
            "exit_code": evidence.exit_code,
            "gpu_pids_after": evidence.gpu_pids_after,
        },
        "model_snapshot": {
            "requested_repo": evidence.artifact.requested_repo,
            "requested_revision": evidence.artifact.requested_revision,
            "snapshot_merkle_sha256": evidence.artifact.snapshot_merkle_sha256,
            "files": list(evidence.artifact.snapshot_files),
        },
        "serve_log_sha256": _path_sha256(evidence.serve_log_path),
        "determinism": {
            "engine_log_evidence": list(evidence.deterministic_kernel_evidence),
            "engine_log_semantic_verdict": evidence.deterministic_kernel_enabled,
            "live_process_environment": {
                "VLLM_BATCH_INVARIANT": evidence.live_batch_invariant,
            },
            "two_start_canary_passed": evidence.determinism_canary_passed,
        },
        "startup_memory_report": {
            "computed_fit": evidence.computed_memory_fit or {},
            "observed_allocations": evidence.memory_allocations or {},
        },
        "server_fingerprint": evidence.server_fingerprint,
        "resume_identity": evidence.resume_identity,
    }


def _blocking_reasons(evidence: ServingEvidence) -> list[str]:
    reasons: list[str] = []
    if evidence.artifact.file_sha256 == "":
        reasons.append("model.immutable_hash_missing")
    if evidence.executable_sha256 in {None, ""}:
        reasons.append("runtime.binary_digest_missing")
    if evidence.version_stdout in {None, ""}:
        reasons.append("runtime.version_missing")
    if evidence.parallel_slots != 1:
        reasons.append("runtime.parallel_slots_not_one")
    if evidence.continuous_batching:
        reasons.append("runtime.continuous_batching_enabled")
    if evidence.reported_model != evidence.model_id:
        reasons.append("endpoint.reported_model_mismatch")
    if "auto" in evidence.argv:
        reasons.append("runtime.auto_knob_unresolved")
    if not evidence.teardown_terminated or evidence.gpu_pids_after != []:
        reasons.append("serving.teardown_uncertain")
    if evidence.runtime in {"vllm", "sglang"} and _path_sha256(
        evidence.serve_log_path
    ) in {None, ""}:
        reasons.append("serving.log_missing")
    if evidence.runtime in {"vllm", "sglang"}:
        if (
            evidence.artifact.snapshot_merkle_sha256 in {None, ""}
            or not evidence.artifact.snapshot_files
        ):
            reasons.append("model.snapshot_identity_missing")
        if evidence.artifact.requested_repo in {None, ""}:
            reasons.append("model.snapshot_repo_missing")
        revision = evidence.artifact.requested_revision
        if not isinstance(revision, str) or len(revision) != 40:
            reasons.append("model.snapshot_revision_missing")
        if evidence.device_name in {None, ""} or evidence.driver_version in {None, ""}:
            reasons.append("runtime.device_identity_missing")
        if evidence.dtype in {None, ""} or evidence.quantization in {None, ""}:
            reasons.append("runtime.engine_config_missing")
        if evidence.engine_version in {None, ""}:
            reasons.append("runtime.server_version_missing")
        if evidence.dependency_lock_sha256 in {None, ""}:
            reasons.append("runtime.dependency_lock_missing")
        if evidence.runtime_identity_sha256 in {None, ""}:
            reasons.append("runtime.identity_missing")
        if evidence.applied_chat_template_sha256 in {None, ""}:
            reasons.append("runtime.chat_template_unverified")
        if not evidence.determinism_canary_passed:
            reasons.append("runtime.two_start_canary_missing")
        if (
            evidence.computed_memory_fit is None
            or evidence.computed_memory_fit.get("fits") is not True
        ):
            reasons.append("runtime.memory_fit_unverified")
        allocations = evidence.memory_allocations or {}
        if "kv_cache" not in allocations:
            reasons.append("runtime.memory_report_unverified")
    if evidence.runtime == "vllm":
        if evidence.env_allowlist.get("VLLM_BATCH_INVARIANT") != "1":
            reasons.append("runtime.batch_invariance_missing")
        if not evidence.deterministic_kernel_enabled:
            reasons.append("runtime.deterministic_kernel_unverified")
        if evidence.live_batch_invariant != "1":
            reasons.append("runtime.live_batch_invariance_unverified")
    if evidence.runtime == "sglang":
        if evidence.installed_package_tree_sha256 in {None, ""}:
            reasons.append("runtime.installed_package_tree_identity_missing")
        resolved = evidence.resolved_server_config or {}
        if resolved.get("version") != "0.5.13":
            reasons.append("runtime.server_version_unverified")
        if resolved.get("enable_deterministic_inference") is not True:
            reasons.append("runtime.deterministic_inference_unverified")
        if resolved.get("attention_backend") not in {"flashinfer", "fa3", "triton"}:
            reasons.append("runtime.deterministic_attention_backend_unverified")
        if resolved.get("max_running_requests") != 1:
            reasons.append("runtime.max_running_requests_not_one")
    return reasons


def api_key_sha256(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def sanitize_launch_argv(argv: list[str]) -> list[str]:
    """Replace absolute local argv paths with non-identifying basenames."""
    sanitized: list[str] = []
    for token in argv:
        prefix, separator, value = token.partition("=")
        if separator and _is_absolute_local_path(value):
            sanitized.append(f"{prefix}={_path_basename(value)}")
        elif _is_absolute_local_path(token):
            sanitized.append(_path_basename(token))
        else:
            sanitized.append(token)
    return sanitized


def _is_absolute_local_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return normalized.startswith("/") or (
        len(normalized) >= 3 and normalized[0].isalpha() and normalized[1:3] == ":/"
    )


def _path_basename(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _path_sha256(path_value: str) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_blocking_reasons(manifest: JsonObject) -> list[str]:
    if "provenance" not in manifest:
        return []
    provenance = _object(manifest.get("provenance"))
    reasons: list[str] = []
    if provenance.get("dirty_tree") is True:
        reasons.append("localbench.dirty_tree")
    if provenance.get("dependency_lock_hash") in {None, ""}:
        reasons.append("localbench.dependency_lock_missing")
    return reasons


def _object(value) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
