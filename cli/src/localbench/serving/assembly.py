from __future__ import annotations

import os
from pathlib import Path
from typing import assert_never

from localbench._suite import read_json_object
from localbench._types import JsonObject
from localbench.orchestrate import LaneChoice
from localbench.serving.bench import BenchRunConfig
from localbench.serving.llama_cpp import (
    BuildIdentity,
    CAPPED_THINKING_REASONING_BUDGET,
    LLAMA_CPP_REASONING_FORMAT,
    LlamaCppLaunchConfig,
    LlamaCppReasoningConfig,
)
from localbench.serving.model_artifact import (
    ModelArtifact,
    resolve_model_file_artifact,
    resolve_model_reference,
)
from localbench.serving.options import ServeBenchOptions
from localbench.serving.provenance import ServingEvidence, api_key_sha256
from localbench.serving.readiness import ReadinessEvidence
from localbench.serving.teardown import TeardownEvidence


def run_dir(options: ServeBenchOptions) -> Path:
    if options.resume is not None:
        return options.resume
    if options.out is not None:
        return options.out
    return Path("runs") / "bench" / options.model_id


def resolve_artifact(options: ServeBenchOptions, root: Path) -> ModelArtifact:
    if options.model_file is not None and options.model_ref is not None:
        raise RuntimeError("pass exactly one of --model-file or --model-ref")
    if options.model_file is not None:
        return resolve_model_file_artifact(options.model_file, run_dir=root)
    if options.model_ref is None:
        raise RuntimeError("pass --model-file or --model-ref")
    cache_dir = options.cache_dir or root / "hf-cache"
    return resolve_model_reference(options.model_ref, cache_dir=cache_dir, run_dir=root)


def server_bin(options: ServeBenchOptions) -> Path:
    if options.server_bin is not None:
        return options.server_bin.resolve()
    env_path = os.environ.get("LOCALBENCH_LLAMA_SERVER")
    if env_path is None or env_path == "":
        raise RuntimeError("pass --server-bin or set LOCALBENCH_LLAMA_SERVER")
    return Path(env_path).resolve()


def bench_config(options: ServeBenchOptions, output_path: Path, api_key: str, port: int) -> BenchRunConfig:
    return BenchRunConfig(
        endpoint=f"http://127.0.0.1:{port}/v1",
        api_key=api_key,
        model_id=options.model_id,
        suite=options.suite,
        bench=options.bench,
        tier=options.tier,
        lane=options.lane,
        seed=options.seed,
        suite_dir=options.suite_dir,
        suite_source=options.suite_source,
        out=output_path,
        resume=options.resume,
    )


def llama_cpp_reasoning_for_lane(lane: LaneChoice) -> LlamaCppReasoningConfig:
    match lane:
        case "answer-only":
            return LlamaCppReasoningConfig(
                reasoning="off",
                reasoning_budget=None,
                reasoning_format=LLAMA_CPP_REASONING_FORMAT,
            )
        case "capped-thinking":
            return LlamaCppReasoningConfig(
                reasoning="on",
                reasoning_budget=CAPPED_THINKING_REASONING_BUDGET,
                reasoning_format=LLAMA_CPP_REASONING_FORMAT,
            )
        case "api-uncapped":
            raise RuntimeError("api-uncapped is not supported for local llama.cpp serving")
        case unreachable:
            assert_never(unreachable)


def serving_evidence(
    *,
    options: ServeBenchOptions,
    artifact: ModelArtifact,
    build: BuildIdentity,
    readiness: ReadinessEvidence,
    teardown: TeardownEvidence,
    launch_config: LlamaCppLaunchConfig,
    argv: list[str],
    env_allowlist: dict[str, str],
    api_key: str,
    port: int,
    fingerprint: str,
    root: Path,
) -> ServingEvidence:
    return ServingEvidence(
        runtime="llama.cpp",
        argv=argv,
        cwd=str(Path.cwd()),
        env_allowlist=env_allowlist,
        host="127.0.0.1",
        port=port,
        api_key_sha256=api_key_sha256(api_key),
        artifact=artifact,
        executable_sha256=build.executable_sha256,
        dll_or_so_hashes=build.dll_or_so_hashes,
        version_stdout=build.version_stdout,
        source_repo=build.source_repo,
        source_commit=build.source_commit,
        source_tag=build.source_tag,
        build_flags=build.build_flags,
        help_text_sha256=build.help_text_sha256,
        ctx_len_configured=launch_config.ctx,
        parallel_slots=readiness.total_slots,
        continuous_batching=False,
        kv_cache_quant="k=f16,v=f16",
        flash_attention=launch_config.flash_attn,
        rope_scaling="model-default",
        reasoning=launch_config.reasoning,
        reasoning_budget=launch_config.reasoning_budget,
        reasoning_format=launch_config.reasoning_format,
        health_200_at=readiness.health_200_at,
        models_response_sha256=readiness.models_response_sha256,
        props_response_sha256=readiness.props_response_sha256,
        reported_model=readiness.reported_model,
        smoke_chat_sha256=readiness.smoke_chat_sha256,
        owned_process_tree=teardown.owned_process_tree,
        teardown_terminated=teardown.terminated,
        exit_code=teardown.exit_code,
        gpu_pids_after=teardown.gpu_pids_after,
        server_fingerprint=fingerprint,
        model_id=options.model_id,
        serve_log_path=str(root / "serve.log"),
    )


def pending_teardown(pid: int) -> TeardownEvidence:
    return TeardownEvidence(
        owned_process_tree=[str(pid)],
        terminated=False,
        exit_code=None,
        gpu_pids_after=[],
        teardown_uncertain=True,
    )


def precheck_resume_fingerprint(resume: Path | None, fingerprint: str) -> None:
    if resume is None:
        return
    campaign = read_json_object(resume / "campaign.json")
    serve = campaign.get("serve_fingerprint")
    actual = serve.get("server_fingerprint") if isinstance(serve, dict) else None
    if actual != fingerprint:
        raise RuntimeError("unsafe resume refused: server_fingerprint changed")


def redacted_argv(argv: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for token in argv:
        if hide_next:
            redacted.append("***REDACTED***")
            hide_next = False
            continue
        redacted.append(token)
        if token == "--api-key":
            hide_next = True
    return redacted
