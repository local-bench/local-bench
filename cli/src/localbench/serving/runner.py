from __future__ import annotations

import hashlib
import secrets
import subprocess
import sys
import uuid
import json
from dataclasses import dataclass, replace
from pathlib import Path

import httpx

from localbench._types import JsonObject
from localbench.appliance.provisioner import ApplianceProvisioner, ProvisioningError
from localbench.appliance.runtime_identity import (
    AgenticRuntimeIdentityError,
    agentic_runtime_identity_sha256,
)
from localbench._suite import read_json_object
from localbench.execution_contract import (
    execution_contract_notice,
    execution_contract_record,
    is_deep_budget_profile,
)
from localbench.orchestrate import run_localbench
from localbench.persistence import atomic_write_json
from localbench.runtime_probe import (
    RuntimeProbeMismatchError,
    verify_llama_cpp_runtime_profile,
)
from localbench.runtime_capacity_probe import verify_llama_cpp_capacity
from localbench.run_plan import resolve_run_benches
from localbench.suite_resolver import STATIC_EXEC_SUITE_ID, resolve_suite_dir
from localbench.serving.assembly import (
    bench_config,
    effective_serving_profile,
    llama_cpp_reasoning_for_lane,
    pending_teardown,
    precheck_resume_identity,
    redacted_argv,
    resolve_artifact,
    resolve_serving_execution_profile,
    run_dir,
    server_bin,
    serving_evidence,
    thread_vllm_model_identity,
    validate_capped_thinking_context,
    validate_profile_server_context,
)
from localbench.serving.agentic_support import (
    AgenticSetupError,
    agentic_chat_template_kwargs,
)
from localbench.serving.agentic_resume import (
    agentic_runtime_revalidator,
    build_agentic_resume_seed_from_runtime,
)
from localbench.serving.bench import build_orchestrate_config
from localbench.serving.fingerprint import resume_identity, server_fingerprint
from localbench.serving.llama_cpp import (
    LlamaCppLaunchConfig,
    collect_build_identity,
    reconcile_agent_isolation,
    strict_llama_cpp_argv,
    validate_strict_argv_supported,
)
from localbench.serving.model_artifact import ModelArtifact, sha256_file
from localbench.serving.options import ServeBenchOptions
from localbench.serving.process import (
    JobController,
    LaunchedServer,
    allocate_port,
    launch_llama_cpp,
)
from localbench.serving.provenance import (
    ServingEvidence,
    apply_serving_context,
    api_key_sha256,
    serving_context,
)
from localbench.serving.readiness import ReadinessEvidence, verify_llama_cpp_readiness
from localbench.serving.teardown import TeardownEvidence, teardown_owned_server
from localbench.scoring.agentic_exec.wsl_bridge import (
    WslPreflightResult,
    preflight_wsl_agentic,
    wsl_sandbox_factory,
)
from localbench.scoring.agentic_exec.sandbox import SandboxError, WorkerSetupError
from localbench.scoring.agentic_exec.task_journal import JournalError
from localbench.scoring.agentic_exec.wsl_process import resolve_worker_config
from localbench.submissions.foundation import normalize_result_bundle
from localbench.serving.vllm import (
    LaunchedVllmServer,
    VllmAdapter,
    VllmBuildIdentity,
    VllmLaunchConfig,
    VllmMemoryFit,
    compute_vllm_memory_fit,
    quantization_config,
    parse_vllm_startup_log,
    read_live_process_environment_map,
    refresh_vllm_process_ownership,
    remove_vllm_cache_dirs,
    validate_vllm_argv,
    vllm_serve_argv,
    wsl_path,
)
from localbench.serving.vllm_policy import (
    GDN_VLLM_VERSION_ALLOWLIST,
    VLLM_BATCH_INVARIANT_POLICY_ID,
    VLLM_GDN_POLICY_ID,
    autotune_manifest_sha256,
    extract_autotune_selections,
    extract_jit_inference_events,
    load_model_text_config,
    parse_resolved_backends,
    policy_env_pins,
    policy_flash_attention_label,
    select_vllm_policy,
)
from localbench.serving.sglang import (
    SglangAdapter,
    SglangBuildIdentity,
    SglangLaunchConfig,
    SglangMemoryFit,
    SGLANG_PINNED_COMMIT,
    compute_sglang_memory_fit,
    quantization_config as sglang_quantization_config,
    refresh_sglang_process_ownership,
    sglang_serve_argv,
    validate_sglang_argv,
)


async def run_orchestrated_bench(options: ServeBenchOptions) -> JsonObject:
    if options.runtime == "vllm":
        return await _run_orchestrated_vllm_bench(options)
    if options.runtime == "sglang":
        return await _run_orchestrated_sglang_bench(options)
    if options.runtime != "llama.cpp":
        raise RuntimeError(f"unsupported runtime: {options.runtime}")
    if options.determinism != "strict":
        raise RuntimeError("--determinism throughput is deferred and non-publishable")
    if options.lane == "api-uncapped":
        llama_cpp_reasoning_for_lane(options.lane)
    root = run_dir(options)
    output_path = root / "localbench-run.json"
    # Advanced --model-ref runs must prove the agentic setup before resolving/downloading
    # the model. One-shot runs inject a freshly repeated post-download preflight here.
    agentic_preflight = options.agentic_preflight or preflight_agentic_if_needed(
        options, root
    )
    artifact = resolve_artifact(options, root)
    port = allocate_port()
    api_key = secrets.token_urlsafe(32)
    base_url = f"http://127.0.0.1:{port}"
    resolved_profile = resolve_serving_execution_profile(
        options,
        artifact,
        llama_apply_template_base_url=base_url,
        llama_api_key=api_key,
    )
    effective_profile = effective_serving_profile(options, resolved_profile)
    if resolved_profile is not None:
        validate_profile_server_context(options.ctx, resolved_profile.contract)
    reasoning_config = llama_cpp_reasoning_for_lane(
        options.lane,
        None if resolved_profile is None else resolved_profile.contract,
    )
    validate_capped_thinking_context(options, effective_profile)
    binary = server_bin(options)
    build = collect_build_identity(binary)
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
    argv = reconcile_agent_isolation(argv, build.help_text)
    validate_strict_argv_supported(argv, build.help_text)
    if (
        options.gguf_repo_only
        and sha256_file(artifact.model_file) != artifact.file_sha256
    ):
        raise RuntimeProbeMismatchError(
            "resolved GGUF artifact changed immediately before llama.cpp launch"
        )
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
    launched: LaunchedServer | None = None
    teardown: TeardownEvidence | None = None
    try:
        launched = launch_llama_cpp(
            argv, cwd=binary.parent, log_path=root / "serve.log"
        )
        readiness = await verify_llama_cpp_readiness(
            base_url=base_url,
            model_id=options.model_id,
            model_file=artifact.model_file,
            api_key=api_key,
            seed=options.seed,
        )
        if (
            resolved_profile is not None
            and is_deep_budget_profile(resolved_profile.contract.profile_id)
        ):
            budget = resolved_profile.contract.budget
            if budget is None:
                raise RuntimeError("deep execution profile omitted its capacity budget")
            await verify_llama_cpp_capacity(
                base_url=base_url,
                api_key=api_key,
                required_context_tokens=budget.server_context_tokens,
                run_dir=root,
                serve_log_path=root / "serve.log",
                serve_log_start_byte=launched.log_start_byte,
                server_identity=launched.identity,
                launch_argv=argv,
            )
        if options.gguf_repo_only and resolved_profile is not None:
            resolved_profile = await verify_llama_cpp_runtime_profile(
                base_url=base_url,
                model_id=options.model_id,
                api_key=api_key,
                runtime=resolved_profile,
                llama_build={
                    "executable_sha256": build.executable_sha256,
                    "version_stdout": build.version_stdout,
                    "source_repo": build.source_repo,
                    "source_commit": build.source_commit,
                    "source_tag": build.source_tag,
                    "build_flags": build.build_flags,
                    "help_text_sha256": build.help_text_sha256,
                },
                run_dir=root,
            )
            effective_profile = effective_serving_profile(options, resolved_profile)
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
            execution_contract=(
                None
                if resolved_profile is None
                else execution_contract_record(resolved_profile.contract)
            ),
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
        agentic_canonical_task_ids = None
        agentic_provenance_extra = None
        agentic_resume_seed = None
        runtime_revalidator = None
        if agentic_preflight is not None:
            from localbench.scoring.agentic_exec.funnel import chat_client_factory  # noqa: PLC0415

            agentic_sandbox_factory = wsl_sandbox_factory(
                agentic_preflight.worker_config,
                expected_identity=agentic_preflight.identity,
            )
            agentic_model_factory = chat_client_factory(
                f"http://127.0.0.1:{port}/v1",
                options.model_id,
                api_key=api_key,
                chat_template_kwargs=agentic_chat_template_kwargs(
                    options.lane,
                    None if resolved_profile is None else resolved_profile.contract,
                ),
            )
            agentic_task_ids = list(agentic_preflight.task_ids)
            agentic_canonical_task_ids = list(
                agentic_preflight.canonical_task_ids or agentic_preflight.task_ids
            )
            agentic_provenance_extra = agentic_preflight.provenance()
            agentic_resume_seed = build_agentic_resume_seed_from_runtime(
                preflight=agentic_preflight,
                evidence=evidence,
                lane=options.lane,
                profile=effective_profile,
            )
            runtime_revalidator = agentic_runtime_revalidator(
                endpoint=f"http://127.0.0.1:{port}/v1",
                model_id=options.model_id,
                api_key=api_key,
            )
        try:
            if resolved_profile is not None:
                print(
                    f"notice     {execution_contract_notice(resolved_profile.contract)}"
                )
            await run_localbench(
                build_orchestrate_config(
                    bench_config(
                        options,
                        output_path,
                        api_key,
                        port,
                        resolved_profile=resolved_profile,
                    ),
                    evidence,
                ),
                agentic_sandbox_factory=agentic_sandbox_factory,
                agentic_model_factory=agentic_model_factory,
                agentic_task_ids=agentic_task_ids,
                agentic_canonical_task_ids=agentic_canonical_task_ids,
                agentic_provenance_extra=agentic_provenance_extra,
                agentic_resume_seed=agentic_resume_seed,
                agentic_runtime_revalidator=runtime_revalidator,
            )
        except (JournalError, WorkerSetupError) as error:
            raise AgenticSetupError(
                detail=str(error),
                model_download_started=True,
                benchmark_started=True,
            ) from error
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


async def _run_orchestrated_vllm_bench(options: ServeBenchOptions) -> JsonObject:
    if options.determinism != "strict":
        raise RuntimeError("--determinism throughput is deferred and non-publishable")
    if options.model_file is not None or options.model_ref is None:
        raise RuntimeError("vLLM requires --model-ref and does not accept --model-file")
    if options.wsl_distro in {None, ""}:
        raise RuntimeError("vLLM requires --wsl-distro")
    options = thread_vllm_model_identity(options)
    distro = options.wsl_distro
    vllm_bin = _vllm_binary(options)
    root = run_dir(options)
    output_path = root / "localbench-run.json"
    agentic_preflight = options.agentic_preflight or preflight_agentic_if_needed(
        options, root
    )
    adapter = VllmAdapter()
    artifact = adapter.resolve_model(
        options.model_ref,
        cache_dir=options.cache_dir or root / "hf-cache",
        run_dir=root,
    )
    resolved_profile = resolve_serving_execution_profile(options, artifact)
    effective_profile = effective_serving_profile(options, resolved_profile)
    if (
        options.lane == "bounded-final-v2"
        and options.profile == "auto"
        and effective_profile != "generic_think_tags_8192_v1"
    ):
        raise VllmExecutionProfileMismatchError(
            resolved=effective_profile,
            expected="generic_think_tags_8192_v1",
        )
    options = replace(
        options,
        profile=effective_profile,
        ctx=_vllm_max_model_len(options, effective_profile),
    )
    validate_capped_thinking_context(options, effective_profile)
    quantization = quantization_config(artifact)
    model_path = wsl_path(artifact.model_file, distro=distro)
    template_path = artifact.model_file / "chat_template.jinja"
    if not template_path.is_file() or artifact.chat_template_digest is None:
        raise RuntimeError("vLLM snapshot must contain chat_template.jinja")
    chat_template = wsl_path(template_path, distro=distro)
    build = adapter.build_identity(distro=distro, vllm_bin=vllm_bin)
    policy_id = select_vllm_policy(load_model_text_config(artifact.model_file))
    if (
        policy_id == VLLM_GDN_POLICY_ID
        and build.package_version not in GDN_VLLM_VERSION_ALLOWLIST
    ):
        raise RuntimeError(
            "vLLM GDN determinism policy is qualified only for vLLM "
            f"{sorted(GDN_VLLM_VERSION_ALLOWLIST)}; found {build.package_version!r}. "
            "GDN/linear-attention models cannot run batch-invariant, and the "
            "structural-single-slot evidence contract (backend pins + log "
            "matchers) is version-qualified."
        )
    port = allocate_port()
    api_key = secrets.token_urlsafe(32)
    launch_config = VllmLaunchConfig(
        distro=distro,
        vllm_bin=vllm_bin,
        model_path=model_path,
        model_id=options.model_id,
        host="127.0.0.1",
        port=port,
        api_key=api_key,
        ctx=options.ctx,
        seed=options.seed,
        dtype=options.vllm_dtype,
        kv_cache_dtype=options.vllm_dtype,
        mamba_ssm_cache_dtype=artifact.mamba_ssm_dtype or "float32",
        quantization=quantization,
        gpu_memory_utilization="0.92",
        chat_template=chat_template,
        run_token=uuid.uuid4().hex,
        expected_executable=build.expected_executable,
        policy_id=policy_id,
    )
    argv = vllm_serve_argv(launch_config)
    validate_vllm_argv(argv, build.help_text, policy_id=policy_id)
    memory_fit = compute_vllm_memory_fit(
        artifact,
        max_model_len=options.ctx,
        total_vram_bytes=build.total_vram_bytes,
        gpu_memory_utilization=launch_config.gpu_memory_utilization,
    )
    env_allowlist = policy_env_pins(policy_id)
    flash_attention_label = policy_flash_attention_label(policy_id)
    safe_argv = redacted_argv(argv)
    fingerprint = server_fingerprint(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.runtime_identity_sha256,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant=options.vllm_dtype,
        parallel_slots=1,
        flash_attention=flash_attention_label,
        chat_template_digest=artifact.chat_template_digest,
    )
    identity = resume_identity(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.runtime_identity_sha256,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant=options.vllm_dtype,
        parallel_slots=1,
        flash_attention=flash_attention_label,
        chat_template_digest=artifact.chat_template_digest,
        execution_contract=(
            None
            if resolved_profile is None
            else execution_contract_record(resolved_profile.contract)
        ),
    )
    precheck_resume_identity(
        options.resume,
        identity,
        chat_template_digest=artifact.chat_template_digest,
        env_allowlist=env_allowlist,
        kv_cache_quant=options.vllm_dtype,
        parallel_slots=1,
        flash_attention=flash_attention_label,
    )
    determinism_canary_passed = False
    canary_outcome: _VllmCanaryOutcome | None = None
    if options.determinism_canary:
        canary_outcome = await _run_vllm_determinism_canary(
            adapter,
            launch_config,
            pinned_chat_template_sha256=artifact.chat_template_digest,
            root=root,
        )
        determinism_canary_passed = True
    launched = None
    teardown: TeardownEvidence | None = None
    try:
        if canary_outcome is not None:
            # Canary start B stays alive and IS the scoring server — the
            # process that produced the qualification evidence is the process
            # that produces the scored row.
            launched = canary_outcome.launched
            readiness = canary_outcome.readiness
        else:
            # Same resume-append hazard as the canary path (F1): the evidence
            # parsers and serve_log_sha256 must see only this process's log.
            stale_serve_log = root / "serve.log"
            if stale_serve_log.is_file():
                stale_serve_log.unlink()
            launched = adapter.launch(launch_config, log_path=root / "serve.log")
            try:
                readiness = await adapter.readiness(
                    base_url=f"http://127.0.0.1:{port}",
                    model_id=options.model_id,
                    pinned_chat_template_sha256=artifact.chat_template_digest,
                    api_key=api_key,
                    seed=options.seed,
                )
            except BaseException as error:
                _raise_memory_fit_error_if_present(root / "serve.log", error)
                raise
        if readiness.build_info != build.package_version:
            raise RuntimeError(
                "vLLM endpoint version does not match the pinned venv package: "
                f"server={readiness.build_info!r}, venv={build.package_version!r}"
            )
        startup_log = parse_vllm_startup_log(root / "serve.log")
        if startup_log.fit_failure is not None:
            raise RuntimeError(
                f"vLLM startup memory fit failed: {startup_log.fit_failure}"
            )
        live_env = read_live_process_environment_map(
            launched, tuple(sorted(env_allowlist))
        )
        resolved_backends = None
        if policy_id == VLLM_GDN_POLICY_ID:
            serve_log_path = root / "serve.log"
            serve_log_text = (
                serve_log_path.read_text(encoding="utf-8", errors="replace")
                if serve_log_path.is_file()
                else ""
            )
            resolved_backends = parse_resolved_backends(serve_log_text).as_json()
        refresh_vllm_process_ownership(launched)
        evidence = _vllm_serving_evidence(
            options=options,
            artifact=artifact,
            build=build,
            readiness=readiness,
            teardown=pending_teardown(launched.server_pid),
            launch_config=launch_config,
            argv=safe_argv,
            env_allowlist=env_allowlist,
            api_key=api_key,
            port=port,
            fingerprint=fingerprint,
            identity=identity,
            root=root,
            memory_fit=memory_fit,
            live_env=live_env,
            determinism_canary_passed=determinism_canary_passed,
            policy_id=policy_id,
            flash_attention_label=flash_attention_label,
            resolved_backends=resolved_backends,
            canary_evidence=(
                canary_outcome.evidence if canary_outcome is not None else None
            ),
        )
        agentic_sandbox_factory = None
        agentic_model_factory = None
        agentic_task_ids = None
        agentic_canonical_task_ids = None
        agentic_provenance_extra = None
        agentic_resume_seed = None
        runtime_revalidator = None
        if agentic_preflight is not None:
            from localbench.scoring.agentic_exec.funnel import chat_client_factory  # noqa: PLC0415

            agentic_sandbox_factory = wsl_sandbox_factory(
                agentic_preflight.worker_config,
                expected_identity=agentic_preflight.identity,
            )
            agentic_model_factory = chat_client_factory(
                f"http://127.0.0.1:{port}/v1",
                options.model_id,
                api_key=api_key,
                chat_template_kwargs=agentic_chat_template_kwargs(
                    options.lane,
                    None if resolved_profile is None else resolved_profile.contract,
                ),
            )
            agentic_task_ids = list(agentic_preflight.task_ids)
            agentic_canonical_task_ids = list(
                agentic_preflight.canonical_task_ids or agentic_preflight.task_ids
            )
            agentic_provenance_extra = agentic_preflight.provenance()
            agentic_resume_seed = build_agentic_resume_seed_from_runtime(
                preflight=agentic_preflight,
                evidence=evidence,
                lane=options.lane,
                profile=effective_profile,
            )
            runtime_revalidator = agentic_runtime_revalidator(
                endpoint=f"http://127.0.0.1:{port}/v1",
                model_id=options.model_id,
                api_key=api_key,
            )
        try:
            if resolved_profile is not None:
                print(
                    f"notice     {execution_contract_notice(resolved_profile.contract)}"
                )
            await run_localbench(
                build_orchestrate_config(
                    bench_config(
                        options,
                        output_path,
                        api_key,
                        port,
                        resolved_profile=resolved_profile,
                    ),
                    evidence,
                ),
                agentic_sandbox_factory=agentic_sandbox_factory,
                agentic_model_factory=agentic_model_factory,
                agentic_task_ids=agentic_task_ids,
                agentic_canonical_task_ids=agentic_canonical_task_ids,
                agentic_provenance_extra=agentic_provenance_extra,
                agentic_resume_seed=agentic_resume_seed,
                agentic_runtime_revalidator=runtime_revalidator,
            )
        except (JournalError, WorkerSetupError) as error:
            raise AgenticSetupError(
                detail=str(error),
                model_download_started=True,
                benchmark_started=True,
            ) from error
        if canary_outcome is not None:
            # Post-score sentinels against the still-live scoring server: the
            # benchmark workload itself must not have mutated the server's
            # numerics. A mismatch is recorded as evidence (and blocks
            # publishability) rather than raised — the scored data is kept.
            canary_outcome.evidence["post_score_passed"] = (
                await _run_vllm_post_score_sentinels(canary_outcome, launch_config)
            )
    finally:
        if launched is not None:
            try:
                teardown = adapter.teardown(launched)
            finally:
                launched.close_log()
    if teardown is None:
        raise RuntimeError("server teardown evidence was not collected")
    record = read_json_object(output_path)
    completed_evidence = _vllm_serving_evidence(
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
        memory_fit=memory_fit,
        live_env=live_env,
        determinism_canary_passed=determinism_canary_passed,
        policy_id=policy_id,
        flash_attention_label=flash_attention_label,
        resolved_backends=resolved_backends,
        canary_evidence=(
            canary_outcome.evidence if canary_outcome is not None else None
        ),
    )
    updated = normalize_result_bundle(
        apply_serving_context(record, serving_context(completed_evidence)),
        suite_dir=options.suite_dir,
    )
    atomic_write_json(updated, output_path)
    return updated


async def _run_orchestrated_sglang_bench(options: ServeBenchOptions) -> JsonObject:
    if options.determinism != "strict":
        raise RuntimeError("--determinism throughput is deferred and non-publishable")
    if options.model_file is not None or options.model_ref is None:
        raise RuntimeError(
            "SGLang requires --model-ref and does not accept --model-file"
        )
    if options.wsl_distro in {None, ""}:
        raise RuntimeError("SGLang requires --wsl-distro")
    options = thread_vllm_model_identity(options)
    distro = options.wsl_distro
    python_bin = _sglang_python(options)
    root = run_dir(options)
    output_path = root / "localbench-run.json"
    agentic_preflight = options.agentic_preflight or preflight_agentic_if_needed(
        options, root
    )
    adapter = SglangAdapter()
    artifact = adapter.resolve_model(
        options.model_ref,
        cache_dir=options.cache_dir or root / "hf-cache",
        run_dir=root,
    )
    resolved_profile = resolve_serving_execution_profile(options, artifact)
    effective_profile = effective_serving_profile(options, resolved_profile)
    if (
        options.lane == "bounded-final-v2"
        and options.profile == "auto"
        and effective_profile != "generic_think_tags_8192_v1"
    ):
        raise SglangExecutionProfileMismatchError(
            resolved=effective_profile,
            expected="generic_think_tags_8192_v1",
        )
    options = replace(
        options,
        profile=effective_profile,
        ctx=_sglang_max_model_len(options, effective_profile),
    )
    validate_capped_thinking_context(options, effective_profile)
    quantization = sglang_quantization_config(artifact)
    model_path = wsl_path(artifact.model_file, distro=distro)
    template_path = artifact.model_file / "chat_template.jinja"
    if not template_path.is_file() or artifact.chat_template_digest is None:
        raise RuntimeError("SGLang snapshot must contain chat_template.jinja")
    chat_template = wsl_path(template_path, distro=distro)
    build = adapter.build_identity(distro=distro, python_bin=python_bin)
    port = allocate_port()
    api_key = secrets.token_urlsafe(32)
    launch_config = SglangLaunchConfig(
        distro=distro,
        python_bin=python_bin,
        model_path=model_path,
        model_id=options.model_id,
        host="127.0.0.1",
        port=port,
        api_key=api_key,
        ctx=options.ctx,
        seed=options.seed,
        dtype=options.sglang_dtype,
        kv_cache_dtype=options.sglang_dtype,
        mamba_ssm_dtype=artifact.mamba_ssm_dtype or "float32",
        quantization=quantization,
        # Qwen3.6 has vision hidden_size=1152 and no num_hidden_layers, so v0.5.13
        # uses 24: complexity=1.265625, dynamic=0.9734375, and VLM factor=
        # 0.95*0.9734375=0.924765625. Thus requested 0.80 resolves to 0.7398125.
        mem_fraction_static="0.80",
        chat_template=chat_template,
        run_token=uuid.uuid4().hex,
        expected_executable=build.expected_executable,
    )
    argv = sglang_serve_argv(launch_config)
    validate_sglang_argv(argv, build.help_text)
    memory_fit = compute_sglang_memory_fit(
        artifact,
        max_model_len=options.ctx,
        total_vram_bytes=build.total_vram_bytes,
        mem_fraction_static=launch_config.mem_fraction_static,
    )
    env_allowlist = {"CUDA_VISIBLE_DEVICES": "0"}
    safe_argv = redacted_argv(argv)
    fingerprint = server_fingerprint(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.runtime_identity_sha256,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant=options.sglang_dtype,
        parallel_slots=1,
        flash_attention="triton-batch-invariant",
        chat_template_digest=artifact.chat_template_digest,
    )
    identity = resume_identity(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.runtime_identity_sha256,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant=options.sglang_dtype,
        parallel_slots=1,
        flash_attention="triton-batch-invariant",
        chat_template_digest=artifact.chat_template_digest,
        execution_contract=(
            None
            if resolved_profile is None
            else execution_contract_record(resolved_profile.contract)
        ),
    )
    precheck_resume_identity(
        options.resume,
        identity,
        chat_template_digest=artifact.chat_template_digest,
        env_allowlist=env_allowlist,
        kv_cache_quant=options.sglang_dtype,
        parallel_slots=1,
        flash_attention="triton-batch-invariant",
    )
    determinism_canary_passed = False
    if options.determinism_canary:
        await _run_sglang_determinism_canary(
            adapter,
            launch_config,
            expected_mem_fraction_static=memory_fit.mem_fraction_static,
            pinned_chat_template_sha256=artifact.chat_template_digest,
            local_snapshot_path=artifact.model_file,
            root=root,
        )
        determinism_canary_passed = True
    launched = None
    teardown: TeardownEvidence | None = None
    try:
        launched = adapter.launch(launch_config, log_path=root / "serve.log")
        try:
            readiness = await adapter.readiness(
                base_url=f"http://127.0.0.1:{port}",
                model_id=options.model_id,
                model_path=model_path,
                chat_template=chat_template,
                pinned_chat_template_sha256=artifact.chat_template_digest,
                api_key=api_key,
                seed=options.seed,
                ctx=options.ctx,
                dtype=options.sglang_dtype,
                kv_cache_dtype=options.sglang_dtype,
                mamba_ssm_dtype=launch_config.mamba_ssm_dtype,
                quantization=quantization,
                expected_mem_fraction_static=memory_fit.mem_fraction_static,
                local_snapshot_path=artifact.model_file,
            )
        except BaseException:
            raise
        if readiness.build_info != build.package_version:
            raise RuntimeError(
                "SGLang endpoint version does not match the pinned venv package: "
                f"server={readiness.build_info!r}, venv={build.package_version!r}"
            )
        refresh_sglang_process_ownership(launched)
        evidence = _sglang_serving_evidence(
            options=options,
            artifact=artifact,
            build=build,
            readiness=readiness,
            teardown=pending_teardown(launched.server_pid),
            launch_config=launch_config,
            argv=safe_argv,
            env_allowlist=env_allowlist,
            api_key=api_key,
            port=port,
            fingerprint=fingerprint,
            identity=identity,
            root=root,
            memory_fit=memory_fit,
            determinism_canary_passed=determinism_canary_passed,
        )
        agentic_sandbox_factory = None
        agentic_model_factory = None
        agentic_task_ids = None
        agentic_canonical_task_ids = None
        agentic_provenance_extra = None
        agentic_resume_seed = None
        runtime_revalidator = None
        if agentic_preflight is not None:
            from localbench.scoring.agentic_exec.funnel import chat_client_factory  # noqa: PLC0415

            agentic_sandbox_factory = wsl_sandbox_factory(
                agentic_preflight.worker_config,
                expected_identity=agentic_preflight.identity,
            )
            agentic_model_factory = chat_client_factory(
                f"http://127.0.0.1:{port}/v1",
                options.model_id,
                api_key=api_key,
                chat_template_kwargs=agentic_chat_template_kwargs(
                    options.lane,
                    None if resolved_profile is None else resolved_profile.contract,
                ),
            )
            agentic_task_ids = list(agentic_preflight.task_ids)
            agentic_canonical_task_ids = list(
                agentic_preflight.canonical_task_ids or agentic_preflight.task_ids
            )
            agentic_provenance_extra = agentic_preflight.provenance()
            agentic_resume_seed = build_agentic_resume_seed_from_runtime(
                preflight=agentic_preflight,
                evidence=evidence,
                lane=options.lane,
                profile=effective_profile,
            )
            runtime_revalidator = agentic_runtime_revalidator(
                endpoint=f"http://127.0.0.1:{port}/v1",
                model_id=options.model_id,
                api_key=api_key,
            )
        try:
            if resolved_profile is not None:
                print(
                    f"notice     {execution_contract_notice(resolved_profile.contract)}"
                )
            await run_localbench(
                build_orchestrate_config(
                    bench_config(
                        options,
                        output_path,
                        api_key,
                        port,
                        resolved_profile=resolved_profile,
                    ),
                    evidence,
                ),
                agentic_sandbox_factory=agentic_sandbox_factory,
                agentic_model_factory=agentic_model_factory,
                agentic_task_ids=agentic_task_ids,
                agentic_canonical_task_ids=agentic_canonical_task_ids,
                agentic_provenance_extra=agentic_provenance_extra,
                agentic_resume_seed=agentic_resume_seed,
                agentic_runtime_revalidator=runtime_revalidator,
            )
        except (JournalError, WorkerSetupError) as error:
            raise AgenticSetupError(
                detail=str(error),
                model_download_started=True,
                benchmark_started=True,
            ) from error
    finally:
        if launched is not None:
            try:
                teardown = adapter.teardown(launched)
            finally:
                launched.close_log()
    if teardown is None:
        raise RuntimeError("server teardown evidence was not collected")
    record = read_json_object(output_path)
    completed_evidence = _sglang_serving_evidence(
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
        memory_fit=memory_fit,
        determinism_canary_passed=determinism_canary_passed,
    )
    updated = normalize_result_bundle(
        apply_serving_context(record, serving_context(completed_evidence)),
        suite_dir=options.suite_dir,
    )
    atomic_write_json(updated, output_path)
    return updated


def _vllm_binary(options: ServeBenchOptions) -> str:
    if options.vllm_bin not in {None, ""}:
        value = options.vllm_bin
    elif options.vllm_venv not in {None, ""}:
        value = f"{options.vllm_venv.rstrip('/')}/bin/vllm"
    else:
        raise RuntimeError("vLLM requires --vllm-bin or --vllm-venv")
    if not value.startswith("/"):
        raise RuntimeError(
            "vLLM binary and virtualenv paths must be absolute WSL paths"
        )
    return value


@dataclass(frozen=True, slots=True)
class VllmExecutionProfileMismatchError(RuntimeError):
    resolved: str
    expected: str

    def __str__(self) -> str:
        return (
            "vLLM bounded-final-v2 execution profile mismatch: "
            f"resolved={self.resolved!r}, expected={self.expected!r}"
        )


def _vllm_max_model_len(options: ServeBenchOptions, profile: str) -> int:
    if options.ctx is not None and options.vllm_max_model_len is not None:
        if options.ctx != options.vllm_max_model_len:
            raise RuntimeError(
                "--ctx and --vllm-max-model-len must match when both are supplied"
            )
    override = (
        options.vllm_max_model_len
        if options.vllm_max_model_len is not None
        else options.ctx
    )
    if override is not None:
        if override <= 0:
            raise RuntimeError("vLLM max model length must be positive")
        return override
    if profile in {
        "generic_think_tags_8192_v1",
        "gemma4_channel_8192_v1",
        "answer_only_v1",
    }:
        return 8192
    raise RuntimeError(
        f"no vLLM context requirement is defined for execution profile {profile!r}"
    )


def _sglang_python(options: ServeBenchOptions) -> str:
    if options.sglang_python not in {None, ""}:
        value = options.sglang_python
    elif options.sglang_venv not in {None, ""}:
        value = f"{options.sglang_venv.rstrip('/')}/bin/python"
    else:
        raise RuntimeError("SGLang requires --sglang-python or --sglang-venv")
    if not value.startswith("/"):
        raise RuntimeError(
            "SGLang Python and virtualenv paths must be absolute WSL paths"
        )
    return value


@dataclass(frozen=True, slots=True)
class SglangExecutionProfileMismatchError(RuntimeError):
    resolved: str
    expected: str

    def __str__(self) -> str:
        return (
            "SGLang bounded-final-v2 execution profile mismatch: "
            f"resolved={self.resolved!r}, expected={self.expected!r}"
        )


def _sglang_max_model_len(options: ServeBenchOptions, profile: str) -> int:
    if options.ctx is not None and options.sglang_max_model_len is not None:
        if options.ctx != options.sglang_max_model_len:
            raise RuntimeError(
                "--ctx and --sglang-max-model-len must match when both are supplied"
            )
    override = (
        options.sglang_max_model_len
        if options.sglang_max_model_len is not None
        else options.ctx
    )
    if override is not None:
        if override <= 0:
            raise RuntimeError("SGLang max model length must be positive")
        return override
    if profile in {
        "generic_think_tags_8192_v1",
        "gemma4_channel_8192_v1",
        "answer_only_v1",
    }:
        return 8192
    raise RuntimeError(
        f"no SGLang context requirement is defined for execution profile {profile!r}"
    )


# Deliberately varied vocabulary for canary filler text: an all-one-token
# prompt would exercise a numerically narrow trajectory (oracle pitfall).
_CANARY_WORDS = (
    "time", "light", "river", "stone", "cloud", "music", "paper", "garden",
    "window", "market", "mountain", "signal", "harbor", "copper", "meadow",
    "lantern", "orbit", "canvas", "timber", "velvet", "anchor", "bridge",
    "cellar", "damson", "ember", "fathom", "gable", "hollow",
)

# (label, target rendered input tokens after chat-template application).
# 64/65 straddle the GDN chunk boundary; 26624 is the lane/profile ctx floor;
# "lmax" is computed from the configured ctx at runtime.
_CANARY_TARGETS: tuple[tuple[str, int], ...] = (
    ("s128", 128),
    ("l64", 64),
    ("l65", 65),
    ("l8k", 8192),
    ("l16k", 16384),
    ("l26k", 26624),
)
_CANARY_MAX_TOKENS = 64
_CANARY_LMAX_MARGIN = 96  # headroom under ctx for generation + template drift


@dataclass(frozen=True, slots=True)
class _VllmCanaryProbe:
    label: str
    target_tokens: int
    rendered_tokens: int
    content: str


@dataclass(slots=True)
class _VllmCanaryOutcome:
    launched: LaunchedVllmServer
    readiness: ReadinessEvidence
    evidence: JsonObject
    probes: dict[str, _VllmCanaryProbe]
    baseline: dict[str, JsonObject]
    serve_log: Path


def _canary_filler(word_count: int, salt: int) -> str:
    words = []
    index = salt % len(_CANARY_WORDS)
    step = 7 + (salt % 5)
    for _ in range(max(1, word_count)):
        words.append(_CANARY_WORDS[index])
        index = (index + step) % len(_CANARY_WORDS)
    return " ".join(words)


def _canary_messages(content: str) -> list[JsonObject]:
    return [{"role": "user", "content": content}]


async def _rendered_token_count(
    client: httpx.AsyncClient, model_id: str, content: str
) -> int:
    response = await client.post(
        "/tokenize",
        json={
            "model": model_id,
            "messages": _canary_messages(content),
            "add_generation_prompt": True,
        },
    )
    response.raise_for_status()
    payload = response.json()
    count = payload.get("count")
    if not isinstance(count, int) or count <= 0:
        raise RuntimeError("vLLM /tokenize did not return a positive token count")
    return count


async def _build_canary_probes(
    client: httpx.AsyncClient, *, model_id: str, ctx: int
) -> tuple[list[_VllmCanaryProbe], list[JsonObject]]:
    targets = [*_CANARY_TARGETS, ("lmax", ctx - _CANARY_LMAX_MARGIN)]
    probes: list[_VllmCanaryProbe] = []
    skipped: list[JsonObject] = []
    for salt, (label, target) in enumerate(targets):
        if target >= ctx:
            skipped.append({"label": label, "reason": "target_exceeds_ctx"})
            continue
        floor = await _rendered_token_count(client, model_id, _canary_filler(1, salt))
        if floor > target:
            skipped.append(
                {
                    "label": label,
                    "reason": "target_below_template_floor",
                    "template_floor": floor,
                }
            )
            continue
        words = max(1, int((target - floor) * 0.9))
        probe: _VllmCanaryProbe | None = None
        best_content: str | None = None
        best_count = 0
        for _ in range(80):
            content = _canary_filler(words, salt)
            count = await _rendered_token_count(client, model_id, content)
            if count == target:
                probe = _VllmCanaryProbe(
                    label=label,
                    target_tokens=target,
                    rendered_tokens=count,
                    content=content,
                )
                break
            if best_content is None or abs(count - target) < abs(best_count - target):
                best_content = content
                best_count = count
            words = max(1, words + (target - count))
        if probe is None and best_content is not None and abs(best_count - target) <= 2:
            # Token merges can make rendered length jump over the exact
            # target (observed live: s128 unreachable on the Qwen3.6
            # template). Within-tolerance is sound: the evidence is
            # cross-start equality of IDENTICAL content; rendered_tokens
            # records the actual length.
            probe = _VllmCanaryProbe(
                label=label,
                target_tokens=target,
                rendered_tokens=best_count,
                content=best_content,
            )
        if probe is None:
            raise RuntimeError(
                f"vLLM canary probe {label} could not reach {target} (+/-2) "
                "rendered tokens"
            )
        probes.append(probe)
    if not probes:
        raise RuntimeError("vLLM canary matrix is empty — no probe target was reachable")
    return probes, skipped


def _canary_request_order(probes: list[_VllmCanaryProbe]) -> list[tuple[str, str]]:
    """(position_key, probe_label) pairs: short repeat, ascending lengths,
    then a short A/B/A state-isolation check and a long repeat."""
    by_label = {probe.label: probe for probe in probes}
    order: list[tuple[str, str]] = []
    if "s128" in by_label:
        order.append(("s128#1", "s128"))
        order.append(("s128#2", "s128"))
    for probe in probes:
        if probe.label != "s128":
            order.append((f"{probe.label}#1", probe.label))
    if "s128" in by_label:
        order.append(("s128#isolation", "s128"))
    last_long = next(
        (probe.label for probe in reversed(probes) if probe.label != "s128"), None
    )
    if last_long is not None:
        order.append((f"{last_long}#repeat", last_long))
    return order


async def _canary_observation(
    client: httpx.AsyncClient,
    *,
    model_id: str,
    seed: int,
    probe: _VllmCanaryProbe,
) -> JsonObject:
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": model_id,
            "messages": _canary_messages(probe.content),
            "max_tokens": _CANARY_MAX_TOKENS,
            "temperature": 0,
            "top_k": 1,
            "seed": seed,
            "logprobs": True,
            "top_logprobs": 2,
        },
    )
    response.raise_for_status()
    payload = response.json()
    choice = payload["choices"][0]
    logprob_content = ((choice.get("logprobs") or {}).get("content")) or []
    if not isinstance(logprob_content, list) or not logprob_content:
        raise RuntimeError(
            f"vLLM canary probe {probe.label} returned no token logprob evidence; "
            "token-level equality cannot be established"
        )
    if any(entry.get("token") is None for entry in logprob_content):
        raise RuntimeError(
            f"vLLM canary probe {probe.label} returned logprob entries without "
            "token identities; token-level equality cannot be established"
        )
    tokens = [str(entry["token"]) for entry in logprob_content]
    gaps: list[float] = []
    for entry in logprob_content:
        top = entry.get("top_logprobs") or []
        if len(top) >= 2:
            try:
                gaps.append(float(top[0]["logprob"]) - float(top[1]["logprob"]))
            except (KeyError, TypeError, ValueError):
                continue
    message = choice.get("message") or {}
    content = message.get("content")
    content_text = content if isinstance(content, str) else ""
    return {
        "tokens": tokens,
        "finish_reason": choice.get("finish_reason"),
        "content_sha256": hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
        "completion_tokens": len(tokens),
        "min_top1_top2_logprob_gap": min(gaps) if gaps else None,
    }


def _observation_equal(left: JsonObject, right: JsonObject) -> bool:
    return (
        left.get("tokens") == right.get("tokens")
        and left.get("finish_reason") == right.get("finish_reason")
        and left.get("content_sha256") == right.get("content_sha256")
    )


def _canary_log_selections(log_path: Path) -> tuple[tuple[str, str], ...]:
    if not log_path.is_file():
        return ()
    return extract_autotune_selections(
        log_path.read_text(encoding="utf-8", errors="replace")
    )


async def _run_canary_sequence(
    config: VllmLaunchConfig,
    probes: dict[str, _VllmCanaryProbe],
    order: list[tuple[str, str]],
) -> dict[str, JsonObject]:
    observations: dict[str, JsonObject] = {}
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{config.port}",
        headers={"Authorization": f"Bearer {config.api_key}"},
        timeout=600.0,
    ) as client:
        for position, label in order:
            observations[position] = await _canary_observation(
                client,
                model_id=config.model_id,
                seed=config.seed,
                probe=probes[label],
            )
    return observations


def _combine_gate(left: bool | None, right: bool | None) -> bool | None:
    if left is False or right is False:
        return False
    if left is None or right is None:
        return None
    return True


def _sequence_gates(observations: dict[str, JsonObject]) -> JsonObject:
    def _pair(a: str, b: str) -> bool | None:
        if a not in observations or b not in observations:
            return None
        return _observation_equal(observations[a], observations[b])

    repeat_long = [
        position for position in observations if position.endswith("#repeat")
    ]
    long_repeat_ok: bool | None = None
    if repeat_long:
        base = repeat_long[0].split("#", 1)[0] + "#1"
        long_repeat_ok = _pair(base, repeat_long[0])
    within = _pair("s128#1", "s128#2")
    if within is not None and long_repeat_ok is not None:
        within = within and long_repeat_ok
    elif within is None:
        within = long_repeat_ok
    return {
        "within_lifetime_repeat_passed": within,
        "state_isolation_passed": _pair("s128#1", "s128#isolation"),
    }


async def _run_vllm_determinism_canary(
    adapter: VllmAdapter,
    config: VllmLaunchConfig,
    *,
    pinned_chat_template_sha256: str,
    root: Path,
) -> _VllmCanaryOutcome:
    """Two-start qualification: start A qualifies and tears down; start B runs
    the identical sequence, must match A token-for-token, and then STAYS
    ALIVE as the scoring server.

    Under the GDN policy the two starts share one per-canary JIT/autotune
    cache: start A benchmarks from empty caches and persists the Triton
    autotune winners (TRITON_CACHE_AUTOTUNING=1); start B replays them from
    disk. Winner selection is wall-clock-benchmark based, so requiring two
    independent cold starts to re-derive identical winners was a timing
    lottery (observed live 2026-07-26: four FLA kernels diverged). The
    manifest captured at start A is the published, pinned kernel-selection
    input; cross-start byte equality then tests numerics under that pin."""
    gdn = config.policy_id == VLLM_GDN_POLICY_ID
    cache_token = uuid.uuid4().hex if gdn else None

    # launch_vllm opens logs in append mode and these paths are stable inside
    # the run dir: on --resume, stale content would poison the autotune
    # manifests, resolved-backend parse, fit-failure scan, and the published
    # serve_log_sha256 (review finding F1). The canary re-runs in full every
    # invocation, so its evidence must start from empty logs.
    for stale in (root / "determinism-canary-start-1.log", root / "serve.log"):
        if stale.is_file():
            stale.unlink()

    async def _readiness(port: int) -> ReadinessEvidence:
        return await adapter.readiness(
            base_url=f"http://127.0.0.1:{port}",
            model_id=config.model_id,
            pinned_chat_template_sha256=pinned_chat_template_sha256,
            api_key=config.api_key,
            seed=config.seed,
        )

    def _abort_cache_cleanup() -> None:
        # Abort path only: on success the shared per-canary cache dirs stay
        # until the scoring server's final teardown removes them. rm -rf is
        # idempotent, so a redundant call is harmless.
        if cache_token is not None:
            remove_vllm_cache_dirs(config.distro, cache_token)

    # --- Start A: qualification process; persists the autotune winners ---
    start_a_log = root / "determinism-canary-start-1.log"
    launched_a = adapter.launch(
        replace(config, run_token=uuid.uuid4().hex, cache_token=cache_token),
        log_path=start_a_log,
    )
    completed_a = False
    try:
        await _readiness(config.port)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{config.port}",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=120.0,
        ) as client:
            probe_list, skipped = await _build_canary_probes(
                client, model_id=config.model_id, ctx=config.ctx
            )
        probes = {probe.label: probe for probe in probe_list}
        order = _canary_request_order(probe_list)
        observations_a = await _run_canary_sequence(config, probes, order)
        completed_a = True
    finally:
        try:
            # On success, keep the shared cache dirs: start B replays start
            # A's persisted autotune winners from them.
            teardown_a = adapter.teardown(launched_a, remove_caches=not completed_a)
        finally:
            launched_a.close_log()
    try:
        _require_clean_canary_teardown("vLLM", 1, teardown_a)
    except BaseException:
        _abort_cache_cleanup()
        raise
    gates_a = _sequence_gates(observations_a)
    selections_a = _canary_log_selections(start_a_log)
    manifest_a = autotune_manifest_sha256(selections_a)
    # Published so a third party can verify the pinned manifest against the
    # start-1 log rather than trusting the attested sha alone (review F5).
    start_a_log_sha256 = (
        hashlib.sha256(start_a_log.read_bytes()).hexdigest()
        if start_a_log.is_file()
        else None
    )

    # --- Start B: qualified scoring process (bounded retry: one relaunch) ---
    # Every failure exit below shares one abort obligation: remove the
    # per-canary cache dirs (review F2 — a start-B launch failure previously
    # orphaned start A's populated caches). The success return is unaffected:
    # the live scoring server still owns the dirs and its final teardown
    # removes them.
    serve_log = root / "serve.log"
    retry_count = 0
    last_failure = ""
    try:
        for attempt in (1, 2):
            if attempt == 2 and serve_log.is_file():
                # replace(), not rename(): rename raises on Windows when the
                # destination exists (a previously-burned retry).
                serve_log.replace(root / "determinism-canary-start-2-attempt-1.log")
            launched_b = adapter.launch(
                replace(config, run_token=uuid.uuid4().hex, cache_token=cache_token),
                log_path=serve_log,
            )
            try:
                readiness_b = await _readiness(config.port)
                observations_b = await _run_canary_sequence(config, probes, order)
            except BaseException:
                try:
                    adapter.teardown(launched_b)
                finally:
                    launched_b.close_log()
                raise
            gates_b = _sequence_gates(observations_b)
            cross_start = all(
                _observation_equal(observations_a[position], observations_b[position])
                for position, _ in order
            )
            serve_text = (
                serve_log.read_text(encoding="utf-8", errors="replace")
                if serve_log.is_file()
                else ""
            )
            selections_b = extract_autotune_selections(serve_text)
            manifest_b = autotune_manifest_sha256(selections_b)
            # A raw record the parser failed to reassemble would otherwise
            # shrink the subset silently (review F4). One record per line
            # per tuning key: Triton's in-memory cache prevents duplicate
            # prints within a process lifetime, so a count mismatch only
            # ever fails closed.
            raw_records_b = serve_text.count("Triton autotuning for ")
            manifest_match: bool | None = None
            if gdn:
                # Start B replays start A's persisted winners from the shared
                # disk cache, so it normally prints NO autotune records (empty
                # manifest — that is the expected replay signature). Any record
                # it does print (a re-benchmarked kernel, e.g. one whose configs
                # the Triton disk cache cannot serialize) must be one start A
                # also derived: a record outside start A's manifest means the
                # scoring process selected a kernel configuration qualification
                # never saw.
                manifest_match = (
                    manifest_a is not None
                    and set(selections_b) <= set(selections_a)
                    and raw_records_b == len(selections_b)
                )
            qualified = (
                cross_start
                and gates_b.get("within_lifetime_repeat_passed") is not False
                and gates_b.get("state_isolation_passed") is not False
                and (manifest_match is not False)
            )
            if qualified:
                min_gaps = [
                    observation.get("min_top1_top2_logprob_gap")
                    for observation in (*observations_a.values(), *observations_b.values())
                ]
                numeric_gaps = [gap for gap in min_gaps if isinstance(gap, (int, float))]
                jit_at_qualification = len(extract_jit_inference_events(serve_text))
                evidence: JsonObject = {
                    "policy_id": config.policy_id,
                    "matrix": [
                        {
                            "label": probe.label,
                            "target_tokens": probe.target_tokens,
                            "rendered_tokens": probe.rendered_tokens,
                            "input_sha256": hashlib.sha256(
                                probe.content.encode("utf-8")
                            ).hexdigest(),
                        }
                        for probe in probe_list
                    ],
                    "skipped": skipped,
                    "request_order": [position for position, _ in order],
                    "max_tokens_per_probe": _CANARY_MAX_TOKENS,
                    "cross_start_passed": True,
                    # Tri-state, never coerced: None means the probes a gate
                    # needs were skipped (e.g. template floor above the short
                    # target). Publishing True for a gate that never ran would
                    # fabricate evidence; provenance blocks on anything not True.
                    "within_lifetime_repeat_passed": _combine_gate(
                        gates_a.get("within_lifetime_repeat_passed"),
                        gates_b.get("within_lifetime_repeat_passed"),
                    ),
                    "state_isolation_passed": _combine_gate(
                        gates_a.get("state_isolation_passed"),
                        gates_b.get("state_isolation_passed"),
                    ),
                    # Start A's manifest is the published, pinned
                    # kernel-selection input. Start B replays it from the
                    # shared disk cache, so a None start-B sha with zero
                    # records is the expected replay signature, not missing
                    # evidence.
                    "autotune_manifest_start_a_sha256": manifest_a,
                    "autotune_manifest_start_b_sha256": manifest_b,
                    "autotune_start_b_records": len(selections_b),
                    "autotune_manifest_match": manifest_match,
                    "canary_start_1_log_sha256": start_a_log_sha256,
                    "retry_count": retry_count,
                    "min_top1_top2_logprob_gap": (
                        min(numeric_gaps) if numeric_gaps else None
                    ),
                    "jit_inference_events_at_qualification": jit_at_qualification,
                    "jit_inference_events_during_scoring": None,
                    "post_score_passed": None,
                    "scored_process_is_canary_start_b": True,
                }
                return _VllmCanaryOutcome(
                    launched=launched_b,
                    readiness=readiness_b,
                    evidence=evidence,
                    probes=probes,
                    baseline={
                        label: observations_b[f"{label}#1"]
                        for label in probes
                        if f"{label}#1" in observations_b
                    },
                    serve_log=serve_log,
                )
            last_failure = (
                f"cross_start={cross_start}, gates_a={gates_a}, gates_b={gates_b}, "
                f"autotune_manifest_match={manifest_match}, "
                f"autotune_start_b_records={len(selections_b)}, "
                f"autotune_raw_records_start_b={raw_records_b}"
            )
            try:
                # Keep the caches across the bounded retry: the relaunch must
                # replay the same pinned manifest, not re-tune.
                teardown_b = adapter.teardown(launched_b, remove_caches=False)
            finally:
                launched_b.close_log()
            _require_clean_canary_teardown("vLLM", 2, teardown_b)
            if gdn and manifest_match is False:
                # Non-retryable (review F1): attempt 1's re-benchmark
                # PERSISTED its divergent winner into the shared disk cache,
                # so a relaunch would replay that winner, print zero records,
                # and pass the subset gate vacuously — the retry would
                # launder the exact mismatch this gate exists to catch.
                raise RuntimeError(
                    "vLLM determinism canary failed: start B derived an "
                    "autotune selection outside start A's pinned manifest "
                    "(non-retryable): " + last_failure
                )
            retry_count += 1
        raise RuntimeError(
            "vLLM determinism canary failed after a bounded relaunch retry: "
            + last_failure
        )
    except BaseException:
        _abort_cache_cleanup()
        raise


async def _run_vllm_post_score_sentinels(
    outcome: _VllmCanaryOutcome, config: VllmLaunchConfig
) -> bool:
    sentinel_labels = [
        label for label in ("s128", "lmax") if label in outcome.baseline
    ]
    if not sentinel_labels:
        return False
    passed = True
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{config.port}",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=600.0,
        ) as client:
            for label in sentinel_labels:
                observation = await _canary_observation(
                    client,
                    model_id=config.model_id,
                    seed=config.seed,
                    probe=outcome.probes[label],
                )
                if not _observation_equal(observation, outcome.baseline[label]):
                    passed = False
                    break
    except Exception:
        passed = False
    # Post-warmup JIT accounting: the canary matrix qualified the shapes; any
    # NEW Triton JIT compile during the scored phase (bench + sentinels) is
    # evidence the scoring process ran kernels the qualification never saw.
    baseline = outcome.evidence.get("jit_inference_events_at_qualification")
    if isinstance(baseline, int) and outcome.serve_log.is_file():
        total = len(
            extract_jit_inference_events(
                outcome.serve_log.read_text(encoding="utf-8", errors="replace")
            )
        )
        outcome.evidence["jit_inference_events_during_scoring"] = total - baseline
    return passed


async def _run_sglang_determinism_canary(
    adapter: SglangAdapter,
    config: SglangLaunchConfig,
    *,
    expected_mem_fraction_static: float,
    pinned_chat_template_sha256: str,
    local_snapshot_path: Path,
    root: Path,
) -> None:
    outputs: list[bytes] = []
    prompts = ("Reply with exactly: alpha", "What is 2+2? Reply with one digit.")
    for start in (1, 2):
        launched = adapter.launch(
            replace(config, run_token=uuid.uuid4().hex),
            log_path=root / f"determinism-canary-start-{start}.log",
        )
        try:
            await adapter.readiness(
                base_url=f"http://127.0.0.1:{config.port}",
                model_id=config.model_id,
                model_path=config.model_path,
                chat_template=config.chat_template,
                pinned_chat_template_sha256=pinned_chat_template_sha256,
                api_key=config.api_key,
                seed=config.seed,
                ctx=config.ctx,
                dtype=config.dtype,
                kv_cache_dtype=config.kv_cache_dtype,
                mamba_ssm_dtype=config.mamba_ssm_dtype,
                quantization=config.quantization,
                expected_mem_fraction_static=expected_mem_fraction_static,
                local_snapshot_path=local_snapshot_path,
            )
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{config.port}/v1",
                headers={"Authorization": f"Bearer {config.api_key}"},
                timeout=60.0,
            ) as client:
                rendered: list[str] = []
                for prompt in prompts:
                    response = await client.post(
                        "/chat/completions",
                        json={
                            "model": config.model_id,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 16,
                            "temperature": 0,
                            "top_k": 1,
                            "seed": config.seed,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    rendered.append(str(payload["choices"][0]["message"]["content"]))
                outputs.append(
                    json.dumps(
                        rendered, ensure_ascii=False, separators=(",", ":")
                    ).encode()
                )
        finally:
            try:
                canary_teardown = adapter.teardown(launched)
            finally:
                launched.close_log()
        _require_clean_canary_teardown("SGLang", start, canary_teardown)
    if len(outputs) != 2 or outputs[0] != outputs[1]:
        raise RuntimeError(
            "SGLang determinism canary failed: outputs differ across two server starts"
        )


def _raise_memory_fit_error_if_present(log_path: Path, cause: BaseException) -> None:
    failed_startup = parse_vllm_startup_log(log_path)
    if failed_startup.fit_failure is not None:
        raise RuntimeError(
            f"vLLM startup memory fit failed: {failed_startup.fit_failure}"
        ) from cause


def _require_clean_canary_teardown(
    runtime: str, start: int, evidence: TeardownEvidence
) -> None:
    if (
        not evidence.terminated
        or evidence.teardown_uncertain
        or evidence.gpu_pids_after
    ):
        raise RuntimeError(
            f"{runtime} determinism canary failed: start {start} teardown was uncertain"
        )


def _vllm_serving_evidence(
    *,
    options: ServeBenchOptions,
    artifact: ModelArtifact,
    build: VllmBuildIdentity,
    readiness: ReadinessEvidence,
    teardown: TeardownEvidence,
    launch_config: VllmLaunchConfig,
    argv: list[str],
    env_allowlist: dict[str, str],
    api_key: str,
    port: int,
    fingerprint: str,
    identity: str,
    root: Path,
    memory_fit: VllmMemoryFit,
    live_env: dict[str, str | None],
    determinism_canary_passed: bool,
    policy_id: str,
    flash_attention_label: str,
    resolved_backends: JsonObject | None,
    canary_evidence: JsonObject | None,
) -> ServingEvidence:
    startup_log = parse_vllm_startup_log(root / "serve.log")
    memory_allocations = dict(startup_log.memory_allocations)
    memory_allocations["weights"] = {
        "value": memory_fit.weights_bytes,
        "unit": "bytes",
        "source": "snapshot_files",
    }
    return ServingEvidence(
        runtime="vllm",
        argv=argv,
        cwd=str(Path.cwd()),
        env_allowlist=env_allowlist,
        host="127.0.0.1",
        port=port,
        api_key_sha256=api_key_sha256(api_key),
        artifact=artifact,
        executable_sha256=build.executable_sha256,
        dll_or_so_hashes={},
        version_stdout=readiness.build_info,
        source_repo="vllm-project/vllm",
        source_commit=None,
        source_tag=None,
        build_flags=(
            f"dtype={launch_config.dtype} kv_cache_dtype={launch_config.kv_cache_dtype} "
            f"mamba_ssm_cache_dtype={launch_config.mamba_ssm_cache_dtype} "
            f"quantization={launch_config.quantization} max_num_seqs=1 "
            f"determinism_policy={policy_id}"
            + (
                " batch_invariant=1"
                if policy_id == VLLM_BATCH_INVARIANT_POLICY_ID
                else " cudagraphs=FULL_AND_PIECEWISE"
            )
        ),
        help_text_sha256=build.help_text_sha256,
        ctx_len_configured=launch_config.ctx,
        parallel_slots=1,
        continuous_batching=False,
        kv_cache_quant=launch_config.kv_cache_dtype,
        flash_attention=flash_attention_label,
        rope_scaling="model-default",
        reasoning="client-controlled",
        reasoning_budget=None,
        reasoning_format="snapshot-chat-template",
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
        resume_identity=identity,
        model_id=options.model_id,
        serve_log_path=str(root / "serve.log"),
        device_name=build.device_name,
        driver_version=build.driver_version,
        cuda_version=build.cuda_version,
        dtype=launch_config.dtype,
        quantization=launch_config.quantization,
        tokenize_sha256=readiness.tokenize_sha256,
        applied_chat_template_sha256=readiness.apply_template_sha256,
        engine_version=readiness.build_info,
        dependency_lock_sha256=build.dependency_lock_sha256,
        mamba_ssm_cache_dtype=launch_config.mamba_ssm_cache_dtype,
        model_config_mamba_ssm_dtype=artifact.mamba_ssm_dtype,
        numeric_deviations=tuple(
            deviation
            for deviation in (
                "kv_cache_dtype=bfloat16 differs from llama.cpp f16"
                if launch_config.kv_cache_dtype == "bfloat16"
                else None,
                (
                    f"mamba_ssm_cache_dtype={launch_config.mamba_ssm_cache_dtype} "
                    f"differs from model config {artifact.mamba_ssm_dtype}"
                    if artifact.mamba_ssm_dtype is not None
                    and launch_config.mamba_ssm_cache_dtype != artifact.mamba_ssm_dtype
                    else None
                ),
            )
            if deviation is not None
        ),
        deterministic_kernel_evidence=startup_log.deterministic_kernel_evidence,
        deterministic_kernel_enabled=startup_log.deterministic_kernel_enabled,
        live_batch_invariant=live_env.get("VLLM_BATCH_INVARIANT"),
        memory_allocations=memory_allocations,
        computed_memory_fit=memory_fit.provenance(),
        runtime_identity_sha256=build.runtime_identity_sha256,
        determinism_canary_passed=determinism_canary_passed,
        run_seed=options.seed,
        determinism_policy_id=policy_id,
        live_env=dict(live_env),
        resolved_backends=resolved_backends,
        canary_evidence=canary_evidence,
    )


def _sglang_serving_evidence(
    *,
    options: ServeBenchOptions,
    artifact: ModelArtifact,
    build: SglangBuildIdentity,
    readiness: ReadinessEvidence,
    teardown: TeardownEvidence,
    launch_config: SglangLaunchConfig,
    argv: list[str],
    env_allowlist: dict[str, str],
    api_key: str,
    port: int,
    fingerprint: str,
    identity: str,
    root: Path,
    memory_fit: SglangMemoryFit,
    determinism_canary_passed: bool,
) -> ServingEvidence:
    resolved = readiness.resolved_runtime or {}
    memory_allocations: JsonObject = {
        "kv_cache": {
            "value": resolved.get("max_total_num_tokens"),
            "unit": "tokens",
            "source": "/server_info.max_total_num_tokens",
        },
        "weights": {
            "value": memory_fit.weights_bytes,
            "unit": "bytes",
            "source": "snapshot_files",
        },
    }
    return ServingEvidence(
        runtime="sglang",
        argv=argv,
        cwd=str(Path.cwd()),
        env_allowlist=env_allowlist,
        host="127.0.0.1",
        port=port,
        api_key_sha256=api_key_sha256(api_key),
        artifact=artifact,
        executable_sha256=build.executable_sha256,
        dll_or_so_hashes={},
        version_stdout=readiness.build_info,
        source_repo="sgl-project/sglang",
        source_commit=SGLANG_PINNED_COMMIT,
        source_tag="v0.5.13",
        build_flags=(
            f"dtype={launch_config.dtype} kv_cache_dtype={launch_config.kv_cache_dtype} "
            f"mamba_ssm_dtype={launch_config.mamba_ssm_dtype} "
            f"quantization={launch_config.quantization} max_running_requests=1 "
            "attention_backend=triton deterministic_inference=1"
        ),
        help_text_sha256=build.help_text_sha256,
        ctx_len_configured=launch_config.ctx,
        parallel_slots=1,
        continuous_batching=False,
        kv_cache_quant=launch_config.kv_cache_dtype,
        flash_attention="triton-batch-invariant",
        rope_scaling="model-default",
        reasoning="client-controlled",
        reasoning_budget=None,
        reasoning_format="snapshot-chat-template",
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
        resume_identity=identity,
        model_id=options.model_id,
        serve_log_path=str(root / "serve.log"),
        device_name=build.device_name,
        driver_version=build.driver_version,
        cuda_version=build.cuda_version,
        dtype=launch_config.dtype,
        quantization=launch_config.quantization,
        tokenize_sha256=readiness.tokenize_sha256,
        applied_chat_template_sha256=readiness.apply_template_sha256,
        engine_version=readiness.build_info,
        dependency_lock_sha256=build.dependency_lock_sha256,
        mamba_ssm_cache_dtype=launch_config.mamba_ssm_dtype,
        model_config_mamba_ssm_dtype=artifact.mamba_ssm_dtype,
        numeric_deviations=tuple(
            deviation
            for deviation in (
                "kv_cache_dtype=bfloat16 differs from llama.cpp f16"
                if launch_config.kv_cache_dtype == "bfloat16"
                else None,
                (
                    f"mamba_ssm_dtype={launch_config.mamba_ssm_dtype} "
                    f"differs from model config {artifact.mamba_ssm_dtype}"
                    if artifact.mamba_ssm_dtype is not None
                    and launch_config.mamba_ssm_dtype != artifact.mamba_ssm_dtype
                    else None
                ),
            )
            if deviation is not None
        ),
        memory_allocations=memory_allocations,
        computed_memory_fit=memory_fit.provenance(),
        runtime_identity_sha256=build.runtime_identity_sha256,
        installed_package_tree_sha256=build.package_tree_sha256,
        determinism_canary_passed=determinism_canary_passed,
        resolved_server_config=readiness.resolved_runtime,
        run_seed=options.seed,
    )


def preflight_agentic_if_needed(
    options: ServeBenchOptions,
    root: Path,
) -> WslPreflightResult | None:
    if not needs_wsl_agentic(options):
        return None
    try:
        appliance_identity: JsonObject | None = None
        appliance_identity_digest: str | None = None
        managed_appliance = sys.platform == "win32" or (
            sys.platform.startswith("linux")
            and options.wsl_venv_python is None
            and options.appworld_root is None
        )
        if managed_appliance:
            appliance_result = ApplianceProvisioner().ensure_active()
            identity_value = appliance_result.get("agentic_runtime_identity")
            digest_value = appliance_result.get("agentic_runtime_identity_sha256")
            if not isinstance(identity_value, dict) or not isinstance(digest_value, str):
                raise ProvisioningError(
                    "runtime_identity_missing",
                    "managed appliance handshake omitted C4 identity",
                    "Reprovision the managed runtime",
                )
            appliance_identity = identity_value
            appliance_identity_digest = digest_value
        config = resolve_worker_config(
            platform_name=sys.platform,
            direct_python=options.wsl_venv_python,
            appworld_root=options.appworld_root,
            log_dir=root / "agentic" / "wsl-worker-logs",
        )
        preflight = preflight_wsl_agentic(
            config=config,
            max_items=options.max_items,
        )
        if appliance_identity is None or appliance_identity_digest is None:
            return preflight
        worker_version = preflight.identity.get("localbench_distribution_version")
        if isinstance(worker_version, str) and worker_version:
            appliance_identity = {
                **appliance_identity,
                "localbench_distribution_version": worker_version,
            }
            appliance_identity_digest = agentic_runtime_identity_sha256(
                appliance_identity
            )
        return replace(
            preflight,
            agentic_runtime_identity=appliance_identity,
            agentic_runtime_identity_sha256=appliance_identity_digest,
        )
    except AgenticSetupError:
        raise
    except AgenticRuntimeIdentityError as error:
        raise AgenticSetupError(detail=str(error)) from None
    except (
        SandboxError,
        ProvisioningError,
        OSError,
        subprocess.TimeoutExpired,
        IndexError,
    ) as error:
        raise AgenticSetupError(detail=str(error)) from error


def needs_wsl_agentic(options: ServeBenchOptions) -> bool:
    if options.runtime not in {"llama.cpp", "vllm", "sglang"}:
        return False
    if options.suite == STATIC_EXEC_SUITE_ID:
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
