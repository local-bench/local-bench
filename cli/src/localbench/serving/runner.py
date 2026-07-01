from __future__ import annotations

import secrets

from localbench._types import JsonObject
from localbench._suite import read_json_object
from localbench.orchestrate import run_localbench
from localbench.persistence import atomic_write_json
from localbench.serving.assembly import (
    bench_config,
    pending_teardown,
    precheck_resume_fingerprint,
    redacted_argv,
    resolve_artifact,
    run_dir,
    server_bin,
    serving_evidence,
)
from localbench.serving.bench import VllmAdapter, build_orchestrate_config
from localbench.serving.fingerprint import server_fingerprint
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


async def run_orchestrated_bench(options: ServeBenchOptions) -> JsonObject:
    if options.runtime == "vllm":
        VllmAdapter().resolve_model()
    if options.runtime != "llama.cpp":
        raise RuntimeError(f"unsupported runtime: {options.runtime}")
    if options.determinism != "strict":
        raise RuntimeError("--determinism throughput is deferred and non-publishable")
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
    )
    argv = strict_llama_cpp_argv(launch_config)
    validate_strict_argv_supported(argv, build.help_text)
    env_allowlist = {"CUDA_VISIBLE_DEVICES": "0"}
    fingerprint = server_fingerprint(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.executable_sha256,
        argv=redacted_argv(argv),
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant="k=f16,v=f16",
        parallel_slots=1,
        flash_attention=launch_config.flash_attn,
        chat_template_digest=artifact.chat_template_digest or "",
    )
    precheck_resume_fingerprint(options.resume, fingerprint)
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
            argv=redacted_argv(argv),
            env_allowlist=env_allowlist,
            api_key=api_key,
            port=port,
            fingerprint=fingerprint,
            root=root,
        )
        await run_localbench(build_orchestrate_config(bench_config(options, output_path, api_key, port), evidence))
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
        argv=redacted_argv(argv),
        env_allowlist=env_allowlist,
        api_key=api_key,
        port=port,
        fingerprint=fingerprint,
        root=root,
    )
    updated = apply_serving_context(record, serving_context(completed_evidence))
    atomic_write_json(updated, output_path)
    return updated
