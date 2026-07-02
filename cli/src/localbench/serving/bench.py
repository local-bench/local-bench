from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from localbench._types import JsonObject
from localbench.orchestrate import LaneChoice, OrchestrateConfig, TierChoice
from localbench.serving.provenance import DETERMINISM_POLICY_ID, ServingEvidence


@dataclass(frozen=True, slots=True)
class BenchRunConfig:
    endpoint: str
    api_key: str
    model_id: str
    suite: str
    bench: str
    tier: TierChoice
    lane: LaneChoice
    seed: int
    suite_dir: Path | None
    suite_source: Path | None
    out: Path
    resume: Path | None
    max_items: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeAdapter:
    runtime: Literal["llama.cpp", "vllm"]


class VllmAdapter:
    runtime: Literal["vllm"] = "vllm"

    def resolve_model(self) -> None:
        raise NotImplementedError("vLLM lane deferred -- see spec section 9")


def build_orchestrate_config(config: BenchRunConfig, evidence: ServingEvidence) -> OrchestrateConfig:
    return OrchestrateConfig(
        endpoint=config.endpoint,
        model=config.model_id,
        suite=config.suite,
        bench=config.bench,
        tier=config.tier,
        concurrency=1,
        out=config.out,
        api_key=config.api_key,
        suite_dir=config.suite_dir,
        suite_source=config.suite_source,
        lane=config.lane,
        provider="local",
        resume=config.resume,
        max_items=config.max_items,
        publishable=True,
        sampler_temperature=0.0,
        sampler_top_k=1,
        sampler_seed=config.seed,
        determinism_policy=DETERMINISM_POLICY_ID,
        model_file=evidence.artifact.model_file,
        model_family=evidence.artifact.model_family,
        quant_label=evidence.artifact.quant_label,
        model_format=evidence.artifact.model_format,
        runtime_name="llama.cpp",
        runtime_version=_runtime_version(evidence),
        kv_cache_quant=evidence.kv_cache_quant,
        ctx_len_configured=evidence.ctx_len_configured,
        parallel_slots=evidence.parallel_slots,
        build_flags=evidence.build_flags,
        runtime_backend="cuda",
        cuda_version=None,
        server_fingerprint=evidence.server_fingerprint,
        serve_fingerprint=_serve_fingerprint(evidence),
    )


def _runtime_version(evidence: ServingEvidence) -> str | None:
    if evidence.source_tag is None and evidence.source_commit is None:
        return evidence.version_stdout
    return "/".join(value for value in (evidence.source_tag, evidence.source_commit) if value is not None)


def _serve_fingerprint(evidence: ServingEvidence) -> JsonObject:
    return {
        "serve_mode": "llama.cpp",
        "server_fingerprint": evidence.server_fingerprint,
        "server_binary_hash": evidence.executable_sha256,
        "server_build": evidence.version_stdout,
        "server_command_redacted": _redacted_argv(evidence.argv),
        "model_artifact_hash": evidence.artifact.file_sha256,
        "sampler_flags": {"temperature": 0, "top_k": 1},
        "context_length": evidence.ctx_len_configured,
        "gpu_layers": 999,
        "reasoning": {
            "mode": evidence.reasoning,
            "budget": evidence.reasoning_budget,
            "format": evidence.reasoning_format,
        },
        "seed_policy": f"seed={evidence.server_fingerprint}",
    }


def _redacted_argv(argv: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_secret = False
    for token in argv:
        if skip_secret:
            redacted.append("***REDACTED***")
            skip_secret = False
            continue
        redacted.append(token)
        if token == "--api-key":
            skip_secret = True
    return redacted
