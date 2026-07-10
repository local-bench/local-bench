from __future__ import annotations

import secrets
import subprocess
import uuid
import json
from dataclasses import dataclass, replace
from pathlib import Path

import httpx

from localbench._types import JsonObject
from localbench._suite import read_json_object
from localbench.orchestrate import run_localbench
from localbench.persistence import atomic_write_json
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
    run_dir,
    server_bin,
    serving_evidence,
    thread_vllm_model_identity,
    validate_capped_thinking_context,
)
from localbench.serving.agentic_support import (
    AgenticSetupError,
    agentic_chat_template_kwargs,
    configured_agentic_paths,
)
from localbench.serving.bench import build_orchestrate_config
from localbench.serving.fingerprint import resume_identity, server_fingerprint
from localbench.serving.llama_cpp import (
    LlamaCppLaunchConfig,
    collect_build_identity,
    strict_llama_cpp_argv,
    validate_strict_argv_supported,
)
from localbench.serving.model_artifact import ModelArtifact
from localbench.serving.options import ServeBenchOptions
from localbench.serving.process import JobController, LaunchedServer, allocate_port, launch_llama_cpp
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
from localbench.submissions.foundation import normalize_result_bundle
from localbench.serving.vllm import (
    VllmAdapter,
    VllmBuildIdentity,
    VllmLaunchConfig,
    quantization_config,
    parse_vllm_startup_log,
    validate_vllm_argv,
    vllm_serve_argv,
    wsl_path,
)


async def run_orchestrated_bench(options: ServeBenchOptions) -> JsonObject:
    if options.runtime == "vllm":
        return await _run_orchestrated_vllm_bench(options)
    if options.runtime != "llama.cpp":
        raise RuntimeError(f"unsupported runtime: {options.runtime}")
    if options.determinism != "strict":
        raise RuntimeError("--determinism throughput is deferred and non-publishable")
    effective_profile = effective_serving_profile(options)
    reasoning_config = llama_cpp_reasoning_for_lane(options.lane, effective_profile)
    validate_capped_thinking_context(options, effective_profile)
    root = run_dir(options)
    output_path = root / "localbench-run.json"
    # Advanced --model-ref runs must prove the agentic setup before resolving/downloading
    # the model. One-shot runs inject a freshly repeated post-download preflight here.
    agentic_preflight = options.agentic_preflight or preflight_agentic_if_needed(options, root)
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
        agentic_canonical_task_ids = None
        agentic_provenance_extra = None
        if agentic_preflight is not None:
            from localbench.scoring.agentic_exec.funnel import chat_client_factory  # noqa: PLC0415

            log_dir = root / "agentic" / "wsl-worker-logs"
            wsl_venv_python, appworld_root = configured_agentic_paths(
                options.wsl_venv_python,
                options.appworld_root,
            )
            agentic_sandbox_factory = wsl_sandbox_factory(
                "",
                wsl_venv_python,
                appworld_root,
                log_dir=log_dir,
                expected_identity=agentic_preflight.identity,
            )
            agentic_model_factory = chat_client_factory(
                f"http://127.0.0.1:{port}/v1",
                options.model_id,
                api_key=api_key,
                chat_template_kwargs=agentic_chat_template_kwargs(options.lane, effective_profile),
            )
            agentic_task_ids = list(agentic_preflight.task_ids)
            agentic_canonical_task_ids = list(
                agentic_preflight.canonical_task_ids or agentic_preflight.task_ids
            )
            agentic_provenance_extra = agentic_preflight.provenance()
        try:
            await run_localbench(
                build_orchestrate_config(bench_config(options, output_path, api_key, port), evidence),
                agentic_sandbox_factory=agentic_sandbox_factory,
                agentic_model_factory=agentic_model_factory,
                agentic_task_ids=agentic_task_ids,
                agentic_canonical_task_ids=agentic_canonical_task_ids,
                agentic_provenance_extra=agentic_provenance_extra,
            )
        except WorkerSetupError as error:
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
    effective_profile = effective_serving_profile(options)
    if (
        options.lane == "bounded-final-v2"
        and options.profile == "auto"
        and effective_profile != "generic_think_tags_8192_v1"
    ):
        raise VllmExecutionProfileMismatchError(
            resolved=effective_profile,
            expected="generic_think_tags_8192_v1",
        )
    options = replace(options, profile=effective_profile, ctx=_vllm_max_model_len(options, effective_profile))
    validate_capped_thinking_context(options, effective_profile)
    root = run_dir(options)
    output_path = root / "localbench-run.json"
    agentic_preflight = options.agentic_preflight or preflight_agentic_if_needed(options, root)
    adapter = VllmAdapter()
    artifact = adapter.resolve_model(
        options.model_ref,
        cache_dir=options.cache_dir or root / "hf-cache",
        run_dir=root,
    )
    quantization = quantization_config(artifact)
    model_path = wsl_path(artifact.model_file, distro=distro)
    template_path = artifact.model_file / "chat_template.jinja"
    if not template_path.is_file() or artifact.chat_template_digest is None:
        raise RuntimeError("vLLM snapshot must contain chat_template.jinja")
    chat_template = wsl_path(template_path, distro=distro)
    chat_template_text = template_path.read_text(encoding="utf-8")
    build = adapter.build_identity(distro=distro, vllm_bin=vllm_bin)
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
    )
    argv = vllm_serve_argv(launch_config)
    validate_vllm_argv(argv, build.help_text)
    env_allowlist = {"CUDA_VISIBLE_DEVICES": "0", "VLLM_BATCH_INVARIANT": "1"}
    safe_argv = redacted_argv(argv)
    fingerprint = server_fingerprint(
        model_file_sha256=artifact.file_sha256,
        executable_sha256=build.runtime_identity_sha256,
        argv=safe_argv,
        env_allowlist=env_allowlist,
        ctx=options.ctx,
        kv_cache_quant=options.vllm_dtype,
        parallel_slots=1,
        flash_attention="batch-invariant",
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
        flash_attention="batch-invariant",
        chat_template_digest=artifact.chat_template_digest,
    )
    precheck_resume_identity(
        options.resume,
        identity,
        chat_template_digest=artifact.chat_template_digest,
        env_allowlist=env_allowlist,
        kv_cache_quant=options.vllm_dtype,
        parallel_slots=1,
        flash_attention="batch-invariant",
    )
    if options.determinism_canary:
        await _run_vllm_determinism_canary(
            adapter,
            launch_config,
            expected_chat_template=chat_template_text,
            root=root,
        )
    launched = None
    teardown: TeardownEvidence | None = None
    try:
        launched = adapter.launch(launch_config, log_path=root / "serve.log")
        try:
            readiness = await adapter.readiness(
                base_url=f"http://127.0.0.1:{port}",
                model_id=options.model_id,
                expected_chat_template=chat_template_text,
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
            raise RuntimeError(f"vLLM startup memory fit failed: {startup_log.fit_failure}")
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
        )
        agentic_sandbox_factory = None
        agentic_model_factory = None
        agentic_task_ids = None
        agentic_canonical_task_ids = None
        agentic_provenance_extra = None
        if agentic_preflight is not None:
            from localbench.scoring.agentic_exec.funnel import chat_client_factory  # noqa: PLC0415

            log_dir = root / "agentic" / "wsl-worker-logs"
            wsl_venv_python, appworld_root = configured_agentic_paths(
                options.wsl_venv_python,
                options.appworld_root,
            )
            agentic_sandbox_factory = wsl_sandbox_factory(
                "",
                wsl_venv_python,
                appworld_root,
                log_dir=log_dir,
                expected_identity=agentic_preflight.identity,
            )
            agentic_model_factory = chat_client_factory(
                f"http://127.0.0.1:{port}/v1",
                options.model_id,
                api_key=api_key,
                chat_template_kwargs=agentic_chat_template_kwargs(options.lane, effective_profile),
            )
            agentic_task_ids = list(agentic_preflight.task_ids)
            agentic_canonical_task_ids = list(
                agentic_preflight.canonical_task_ids or agentic_preflight.task_ids
            )
            agentic_provenance_extra = agentic_preflight.provenance()
        try:
            await run_localbench(
                build_orchestrate_config(bench_config(options, output_path, api_key, port), evidence),
                agentic_sandbox_factory=agentic_sandbox_factory,
                agentic_model_factory=agentic_model_factory,
                agentic_task_ids=agentic_task_ids,
                agentic_canonical_task_ids=agentic_canonical_task_ids,
                agentic_provenance_extra=agentic_provenance_extra,
            )
        except WorkerSetupError as error:
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
        raise RuntimeError("vLLM binary and virtualenv paths must be absolute WSL paths")
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
            raise RuntimeError("--ctx and --vllm-max-model-len must match when both are supplied")
    override = options.vllm_max_model_len if options.vllm_max_model_len is not None else options.ctx
    if override is not None:
        if override <= 0:
            raise RuntimeError("vLLM max model length must be positive")
        return override
    if profile in {"generic_think_tags_8192_v1", "gemma4_channel_8192_v1", "answer_only_v1"}:
        return 8192
    raise RuntimeError(f"no vLLM context requirement is defined for execution profile {profile!r}")


async def _run_vllm_determinism_canary(
    adapter: VllmAdapter,
    config: VllmLaunchConfig,
    *,
    expected_chat_template: str,
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
                expected_chat_template=expected_chat_template,
                api_key=config.api_key,
                seed=config.seed,
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
                outputs.append(json.dumps(rendered, ensure_ascii=False, separators=(",", ":")).encode())
        finally:
            try:
                adapter.teardown(launched)
            finally:
                launched.close_log()
    if len(outputs) != 2 or outputs[0] != outputs[1]:
        raise RuntimeError("vLLM determinism canary failed: outputs differ across two server starts")


def _raise_memory_fit_error_if_present(log_path: Path, cause: BaseException) -> None:
    failed_startup = parse_vllm_startup_log(log_path)
    if failed_startup.fit_failure is not None:
        raise RuntimeError(
            f"vLLM startup memory fit failed: {failed_startup.fit_failure}"
        ) from cause


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
) -> ServingEvidence:
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
            f"quantization={launch_config.quantization} max_num_seqs=1 batch_invariant=1"
        ),
        help_text_sha256=build.help_text_sha256,
        ctx_len_configured=launch_config.ctx,
        parallel_slots=1,
        continuous_batching=False,
        kv_cache_quant=launch_config.kv_cache_dtype,
        flash_attention="batch-invariant",
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
        deterministic_kernel_evidence=parse_vllm_startup_log(root / "serve.log").deterministic_kernel_evidence,
        memory_allocations=parse_vllm_startup_log(root / "serve.log").memory_allocations,
        runtime_identity_sha256=build.runtime_identity_sha256,
        determinism_canary_passed=options.determinism_canary,
    )


def preflight_agentic_if_needed(
    options: ServeBenchOptions,
    root: Path,
) -> WslPreflightResult | None:
    if not needs_wsl_agentic(options):
        return None
    wsl_venv_python, appworld_root = configured_agentic_paths(
        options.wsl_venv_python,
        options.appworld_root,
    )
    try:
        return preflight_wsl_agentic(
            repo_root_wsl_path="",
            venv_python=wsl_venv_python,
            appworld_root=appworld_root,
            log_dir=root / "agentic" / "wsl-worker-logs",
            max_items=options.max_items,
        )
    except AgenticSetupError:
        raise
    except (
        SandboxError,
        OSError,
        subprocess.TimeoutExpired,
        IndexError,
    ) as error:
        raise AgenticSetupError(detail=str(error)) from error


def needs_wsl_agentic(options: ServeBenchOptions) -> bool:
    if options.runtime not in {"llama.cpp", "vllm"}:
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
