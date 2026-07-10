from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from localbench._types import JsonObject
from localbench.bounded_final_profiles import BoundedFinalProfileChoice
from localbench.orchestrate import (
    LaneChoice,
    OrchestrateConfig,
    ReasoningActivationChoice,
    TierChoice,
)
from localbench.serving.provenance import (
    DETERMINISM_POLICY_ID,
    ServingEvidence,
    sanitize_launch_argv,
)
from localbench.serving.model_artifact import ModelArtifact
from localbench.serving.readiness import ReadinessEvidence
from localbench.serving.teardown import TeardownEvidence
from localbench.progress import ProgressReporter


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
    profile: BoundedFinalProfileChoice = "auto"
    max_items: int | None = None
    retry_errored: bool = False
    reasoning_activation: ReasoningActivationChoice | None = None
    hf_model_id: str | None = None
    hf_revision: str | None = None
    gguf_repo_only: bool = False
    progress_reporter: ProgressReporter | None = None


class RuntimeAdapter(Protocol):
    runtime: Literal["llama.cpp", "vllm"]

    def resolve_model(self, ref: str, *, cache_dir: Path, run_dir: Path) -> ModelArtifact: ...

    def build_identity(self, **kwargs: object) -> object: ...

    def launch(self, config: object, *, log_path: Path) -> object: ...

    async def readiness(self, **kwargs: object) -> ReadinessEvidence: ...

    def teardown(self, server: object) -> TeardownEvidence: ...


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
        profile=config.profile,
        provider="local",
        hf_model_id=config.hf_model_id,
        gguf_repo_only=config.gguf_repo_only,
        reasoning_activation=config.reasoning_activation or "qwen3",
        resume=config.resume,
        retry_errored=config.retry_errored,
        hf_revision=config.hf_revision,
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
        tokenizer_digest=evidence.artifact.tokenizer_digest,
        tokenizer_digest_source=_model_digest_source(evidence, evidence.artifact.tokenizer_digest),
        chat_template_digest=evidence.artifact.chat_template_digest,
        chat_template_digest_source=_model_digest_source(evidence, evidence.artifact.chat_template_digest),
        runtime_name=evidence.runtime,
        runtime_version=_runtime_version(evidence),
        kv_cache_quant=evidence.kv_cache_quant,
        ctx_len_configured=evidence.ctx_len_configured,
        parallel_slots=evidence.parallel_slots,
        build_flags=evidence.build_flags,
        runtime_backend="cuda",
        cuda_version=evidence.cuda_version,
        server_fingerprint=evidence.server_fingerprint,
        resume_identity=evidence.resume_identity,
        serve_fingerprint=_serve_fingerprint(evidence),
        progress_reporter=config.progress_reporter,
    )


def _runtime_version(evidence: ServingEvidence) -> str | None:
    if evidence.source_tag is None and evidence.source_commit is None:
        return evidence.version_stdout
    return "/".join(value for value in (evidence.source_tag, evidence.source_commit) if value is not None)


def _serve_fingerprint(evidence: ServingEvidence) -> JsonObject:
    return {
        "serve_mode": evidence.runtime,
        "server_fingerprint": evidence.server_fingerprint,
        "resume_identity": evidence.resume_identity,
        "server_binary_hash": evidence.executable_sha256,
        "server_build": evidence.version_stdout,
        "server_command_redacted": sanitize_launch_argv(_redacted_argv(evidence.argv)),
        "model_artifact_hash": evidence.artifact.file_sha256,
        "sampler_flags": {"temperature": 0, "top_k": 1},
        "context_length": evidence.ctx_len_configured,
        "gpu_layers": 999 if evidence.runtime == "llama.cpp" else None,
        "reasoning": {
            "mode": evidence.reasoning,
            "budget": evidence.reasoning_budget,
            "format": evidence.reasoning_format,
        },
        "seed_policy": f"seed={evidence.server_fingerprint}",
    }


def _model_digest_source(evidence: ServingEvidence, digest: str | None) -> str | None:
    if digest is None:
        return None
    return "snapshot.files" if evidence.artifact.snapshot_merkle_sha256 is not None else "gguf.embedded"


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
