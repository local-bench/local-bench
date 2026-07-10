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


@dataclass(frozen=True, slots=True)
class ServingRunContext:
    block: JsonObject
    determinism_policy: JsonObject
    server_fingerprint: str
    trust_tier: str
    verification_level: str
    blocking_reasons: tuple[str, ...]
    publishable: bool


def determinism_policy(*, seed: int = 1234) -> JsonObject:
    return {
        "policy_id": DETERMINISM_POLICY_ID,
        "claim": "best-effort same-stack reproducibility; not bitwise cross-stack determinism",
        "client": {"temperature": 0, "top_k": 1, "seed": seed, "concurrency": 1},
        "server": {
            "parallel_slots": 1,
            "continuous_batching": False,
            "vllm_max_num_seqs": 1,
            "vllm_batch_invariant": True,
            "llama_cont_batching": False,
        },
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
        determinism_policy=determinism_policy(),
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
    updated["serving_mode"] = "orchestrated_llama_cpp"
    return updated


def _serving_block(evidence: ServingEvidence, verification_level: str) -> JsonObject:
    return {
        "runtime": evidence.runtime,
        "verification_level": verification_level,
        "trust_tier": verification_level,
        "launch": {
            "argv": evidence.argv,
            "cwd": evidence.cwd,
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
        },
        "resolved_runtime": {
            "ctx_len_configured": evidence.ctx_len_configured,
            "parallel_slots": evidence.parallel_slots,
            "continuous_batching": evidence.continuous_batching,
            "kv_cache_quant": evidence.kv_cache_quant,
            "flash_attention": evidence.flash_attention,
            "rope_scaling": evidence.rope_scaling,
            "reasoning": {
                "mode": evidence.reasoning,
                "budget": evidence.reasoning_budget,
                "format": evidence.reasoning_format,
            },
            "chat_template_digest": evidence.artifact.chat_template_digest,
        },
        "readiness_evidence": {
            "health_200_at": evidence.health_200_at,
            "models_response_sha256": evidence.models_response_sha256,
            "props_response_sha256": evidence.props_response_sha256,
            "reported_model": evidence.reported_model,
            "smoke_chat_sha256": evidence.smoke_chat_sha256,
        },
        "teardown_evidence": {
            "owned_process_tree": evidence.owned_process_tree,
            "terminated": evidence.teardown_terminated,
            "exit_code": evidence.exit_code,
            "gpu_pids_after": evidence.gpu_pids_after,
        },
        "model_snapshot": {
            "snapshot_merkle_sha256": evidence.artifact.snapshot_merkle_sha256,
            "files": list(evidence.artifact.snapshot_files),
        },
        "serve_log_sha256": _path_sha256(evidence.serve_log_path),
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
    if evidence.serve_log_path == "":
        reasons.append("serving.log_missing")
    return reasons


def api_key_sha256(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


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
