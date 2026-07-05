from __future__ import annotations

import subprocess
import secrets
from pathlib import Path

from localbench._types import JsonObject
from localbench._suite import read_json_object
from localbench.orchestrate import run_localbench
from localbench.persistence import atomic_write_json
from localbench.run_plan import resolve_run_benches
from localbench.suite_resolver import resolve_suite_dir
from localbench.serving.assembly import (
    bench_config,
    llama_cpp_reasoning_for_lane,
    pending_teardown,
    precheck_resume_identity,
    redacted_argv,
    resolve_artifact,
    run_dir,
    server_bin,
    serving_evidence,
    validate_capped_thinking_context,
)
from localbench.serving.bench import VllmAdapter, build_orchestrate_config
from localbench.serving.fingerprint import resume_identity, server_fingerprint
from localbench.serving.llama_cpp import (
    LlamaCppLaunchConfig,
    collect_build_identity,
    strict_llama_cpp_argv,
    validate_strict_argv_supported,
)
from localbench.serving.options import ServeBenchOptions
from localbench.serving.process import JobController, LaunchedServer, allocate_port, launch_llama_cpp
from localbench.serving.provenance import (
    apply_serving_context,
    serving_context,
)
from localbench.serving.readiness import verify_llama_cpp_readiness
from localbench.serving.teardown import TeardownEvidence, teardown_owned_server
from localbench.scoring.agentic_exec.wsl_bridge import (
    WslPreflightResult,
    default_wsl_repo_path,
    preflight_wsl_agentic,
    wsl_sandbox_factory,
)
from localbench.submissions.foundation import normalize_result_bundle


async def run_orchestrated_bench(options: ServeBenchOptions) -> JsonObject:
    if options.runtime == "vllm":
        VllmAdapter().resolve_model()
    if options.runtime != "llama.cpp":
        raise RuntimeError(f"unsupported runtime: {options.runtime}")
    if options.determinism != "strict":
        raise RuntimeError("--determinism throughput is deferred and non-publishable")
    reasoning_config = llama_cpp_reasoning_for_lane(options.lane)
    validate_capped_thinking_context(options)
    root = run_dir(options)
    output_path = root / "localbench-run.json"
    artifact = resolve_artifact(options, root)
    binary = server_bin(options)
    build = collect_build_identity(binary)
    port = allocate_port()
    api_key = secrets.token_urlsafe(32)
    launch_config = LlamaCppLaunchConfig(
        server_bin=binary,
        model_file=artifact.model_file,
        model_id=options.model_id,
        host="127.0.0.1",
        port=port,
        api_key=api_key,
        ctx=options.ctx,
        seed=options.seed,
        threads=options.threads,
        threads_batch=options.threads_batch,
        run_dir=root,
        reasoning=reasoning_config.reasoning,
        reasoning_budget=reasoning_config.reasoning_budget,
        reasoning_format=reasoning_config.reasoning_format,
    )
    argv = strict_llama_cpp_argv(launch_config)
    validate_strict_argv_supported(argv, build.help_text)
    env_allowlist = {"CUDA_VISIBLE_DEVICES": "0"}
    safe_argv = redacted_argv(argv)
    fingerprint = server_fingerprint(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.executable_sha256,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant="k=f16,v=f16",
        parallel_slots=1,
        flash_attention=launch_config.flash_attn,
        chat_template_digest=artifact.chat_template_digest or "",
    )
    identity = resume_identity(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.executable_sha256,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant="k=f16,v=f16",
        parallel_slots=1,
        flash_attention=launch_config.flash_attn,
        chat_template_digest=artifact.chat_template_digest or "",
    )
    precheck_resume_identity(
        options.resume,
        identity,
        chat_template_digest=artifact.chat_template_digest or "",
        env_allowlist=env_allowlist,
        kv_cache_quant="k=f16,v=f16",
        parallel_slots=1,
        flash_attention=launch_config.flash_attn,
    )
    agentic_preflight = _preflight_agentic_if_needed(options, root)
    launched: LaunchedServer | None = None
    teardown: TeardownEvidence | None = None
    try:
        launched = launch_llama_cpp(argv, cwd=binary.parent, log_path=root / "serve.log")
        readiness = await verify_llama_cpp_readiness(
            base_url=f"http://127.0.0.1:{port}",
            model_id=options.model_id,
            model_file=artifact.model_file,
            api_key=api_key,
            seed=options.seed,
        )
        evidence = serving_evidence(
            options=options,
            artifact=artifact,
            build=build,
            readiness=readiness,
            teardown=pending_teardown(launched.process.pid),
            launch_config=launch_config,
            argv=safe_argv,
            env_allowlist=env_allowlist,
            api_key=api_key,
            port=port,
            fingerprint=fingerprint,
            identity=identity,
            root=root,
        )
        agentic_sandbox_factory = None
        agentic_model_factory = None
        agentic_task_ids = None
        agentic_provenance_extra = None
        if agentic_preflight is not None:
            from localbench.scoring.agentic_exec.funnel import chat_client_factory  # noqa: PLC0415

            repo_root = _repo_root()
            repo_root_wsl = default_wsl_repo_path(repo_root)
            log_dir = root / "agentic" / "wsl-worker-logs"
            agentic_sandbox_factory = wsl_sandbox_factory(
                repo_root_wsl,
                options.wsl_venv_python,
                options.appworld_root,
                log_dir=log_dir,
            )
            agentic_model_factory = chat_client_factory(
                f"http://127.0.0.1:{port}/v1",
                options.model_id,
                api_key=api_key,
                chat_template_kwargs=_agentic_chat_template_kwargs(options.lane),
            )
            agentic_task_ids = list(agentic_preflight.task_ids)
            agentic_provenance_extra = agentic_preflight.provenance()
        await run_localbench(
            build_orchestrate_config(bench_config(options, output_path, api_key, port), evidence),
            agentic_sandbox_factory=agentic_sandbox_factory,
            agentic_model_factory=agentic_model_factory,
            agentic_task_ids=agentic_task_ids,
            agentic_provenance_extra=agentic_provenance_extra,
        )
    finally:
        if launched is not None:
            teardown = teardown_owned_server(
                process=launched.process,
                controller=JobController(launched.job, launched.job_handle),
                owned_pids=[launched.process.pid],
            )
            launched.close_log()
    if teardown is None:
        raise RuntimeError("server teardown evidence was not collected")
    record = read_json_object(output_path)
    completed_evidence = serving_evidence(
        options=options,
        artifact=artifact,
        build=build,
        readiness=readiness,
        teardown=teardown,
        launch_config=launch_config,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        api_key=api_key,
        port=port,
        fingerprint=fingerprint,
        identity=identity,
        root=root,
    )
    updated = normalize_result_bundle(
        apply_serving_context(record, serving_context(completed_evidence)),
        suite_dir=options.suite_dir,
    )
    atomic_write_json(updated, output_path)
    return updated


def _preflight_agentic_if_needed(
    options: ServeBenchOptions,
    root: Path,
) -> WslPreflightResult | None:
    if not _needs_wsl_agentic(options):
        return None
    repo_root = _repo_root()
    return preflight_wsl_agentic(
        repo_root_wsl_path=default_wsl_repo_path(repo_root),
        venv_python=options.wsl_venv_python,
        appworld_root=options.appworld_root,
        log_dir=root / "agentic" / "wsl-worker-logs",
        expected_git_commit=_git_head(repo_root),
        max_items=options.max_items,
    )


def _needs_wsl_agentic(options: ServeBenchOptions) -> bool:
    if options.runtime != "llama.cpp":
        return False
    suite_ref = resolve_suite_dir(
        suite_id=options.suite,
        suite_dir=options.suite_dir,
        accept_suite_terms=False,
        source=options.suite_source,
        cache_root=options.cache_dir,
    )
    suite = read_json_object(suite_ref.path / "suite.json")
    return "appworld_c" in resolve_run_benches(options.bench, suite)


def _agentic_chat_template_kwargs(lane: str) -> dict[str, object]:
    if lane in {"answer-only", "bounded-final-v1"}:
        return {"enable_thinking": False}
    return {"enable_thinking": True}


def _repo_root() -> Path:
    start = Path(__file__).resolve()
    for parent in start.parents:
        if (parent / ".git").exists():
            return parent
    return start.parents[4]


def _git_head(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()
