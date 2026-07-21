from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Protocol, TextIO

import anyio

from localbench._types import JsonObject
from localbench.coding_exec.orchestrate import (
    CodingExecConfig,
    CodingExecError,
    DEFAULT_IMAGE,
    execute_pending_artifacts,
)
from localbench.coding_exec.sandbox import (
    OPT_IN_WARNING,
    DockerEnv,
    Runner as SandboxRunner,
    preflight_sandbox_controls,
    probe_docker_env,
)
from localbench.exit_codes import (
    EXIT_AGENTIC_SETUP_REQUIRED,
    EXIT_INTERNAL_RUNNER_BUG,
    EXIT_PREFLIGHT_FAILED,
    EXIT_USER_INTERRUPTED,
)
from localbench.one_shot.catalog import CatalogResolutionError
from localbench.one_shot.download import (
    DownloadError,
    HfDownloadClient,
    download_artifact_atomic,
    download_tokenizer_snapshot,
)
from localbench.one_shot.preflight import JsonPostClient, OneShotChoiceError, PlanLockMismatch, validate_one_shot_choices
from localbench.one_shot.plan_lock import (
    OneShotDownloadLockFacts,
    write_download_plan_lock,
)
from localbench.one_shot.resolution import (
    CatalogLoader,
    RawArtifactResolver,
    resolve_one_shot,
    server_publishability_preflight,
)
from localbench.one_shot.runtime import print_scorecard, run_root
from localbench.one_shot.serve_plan import OneShotServeRequest, build_serve_options
from localbench.one_shot.sleep import SleepGapMonitor, SleepWakeClockGap
from localbench.one_shot.submission import OneShotSubmitContext, Submitter, maybe_submit
from localbench.one_shot.tokenizer_pin import TokenizerPlanRequest, prepare_tokenizer_plan
from localbench.one_shot.types import (
    FULL_EXEC_SUITE_IDENTITY,
    ONE_SHOT_LOCAL_PREVIEW_REASON,
    OneShotSuiteIdentity,
    ResolvedOneShotModel,
)
from localbench.serving.options import ServeBenchOptions
from localbench.serving.runner import (
    AgenticSetupError,
    needs_wsl_agentic,
    preflight_agentic_if_needed,
    run_orchestrated_bench,
)
from localbench.scoring.agentic_exec.wsl_bridge import WslPreflightResult
from localbench.suite_errors import SuiteResolutionError
from localbench.suite_release import (
    SUITE_RELEASE_MANIFEST_FILE,
    suite_manifest_sha256,
    verify_suite_release_files,
)
from localbench.suite_resolver import resolve_suite_dir
from localbench.suite_verify import read_json_object
from localbench.submissions.submit_run import DEFAULT_SITE, SubmitRunError


class BenchRunner(Protocol):
    def __call__(self, options: ServeBenchOptions) -> JsonObject: ...


class AgenticPreflight(Protocol):
    def __call__(self, options: ServeBenchOptions, root: Path) -> WslPreflightResult | None: ...


class CodingGrader(Protocol):
    def __call__(
        self,
        run_path: Path,
        suite_dir: Path,
        *,
        image: str,
        docker_env: DockerEnv,
    ) -> JsonObject: ...


@dataclass(slots=True)
class OneShotRunnerDeps:
    catalog_loader: CatalogLoader | None = None
    preflight_http: JsonPostClient | None = None
    hf_client: HfDownloadClient | None = None
    bench_runner: BenchRunner | None = None
    submitter: Submitter | None = None
    raw_artifact_resolver: RawArtifactResolver | None = None
    sleep_monitor: "SleepGapMonitor | None" = None
    agentic_preflight: AgenticPreflight | None = None
    coding_docker_env: DockerEnv | None = None
    coding_sandbox_runner: SandboxRunner | None = None
    coding_grader: CodingGrader | None = None


def run_one_shot_bench(
    args,
    *,
    cli_version: str,
    deps: OneShotRunnerDeps | None = None,
    is_tty: bool | None = None,
    input_fn=input,
) -> int:
    dependencies = deps or OneShotRunnerDeps()
    site = str(getattr(args, "site", None) or DEFAULT_SITE)
    root = run_root(args)
    try:
        print(OPT_IN_WARNING)
        if not bool(getattr(args, "allow_untrusted_code", False)):
            raise CodingExecError(
                "Refusing to execute model-generated code without explicit consent; "
                "pass --allow-untrusted-code."
            )
        choices = validate_one_shot_choices(
            is_tty=sys.stdin.isatty() if is_tty is None else is_tty,
            yes=bool(getattr(args, "yes", False)),
            submit_choice=getattr(args, "one_shot_submit", None),
            accept_suite_terms=bool(getattr(args, "accept_suite_terms", False)),
            vram_gb=getattr(args, "vram_gb", None),
            quant=getattr(args, "quant", None),
            vram_detected=getattr(args, "vram_gb", None) is not None,
            offline=bool(getattr(args, "offline", False)),
        )
        suite_identity = _suite_identity(args)
        suite_ref = resolve_suite_dir(
            suite_id=suite_identity.release_id,
            suite_dir=getattr(args, "suite_dir", None),
            accept_suite_terms=bool(getattr(args, "accept_suite_terms", False)),
            source=getattr(args, "suite_source", None),
            cache_root=getattr(args, "cache_dir", None),
        )
        _verify_suite_identity(suite_ref.path, suite_identity)
        coding_docker_env = dependencies.coding_docker_env or probe_docker_env()
        coding_preflight = preflight_sandbox_controls(
            DEFAULT_IMAGE,
            coding_docker_env,
            runner=dependencies.coding_sandbox_runner,
        )
        if not coding_preflight.ok:
            raise CodingExecError("coding preflight failed: " + "; ".join(coding_preflight.blockers))
        for warning in coding_preflight.warnings:
            print(f"preflight coding sandbox: {warning}")
        resolved = resolve_one_shot(
            args,
            choices.vram_gb,
            dependencies.catalog_loader,
            dependencies.raw_artifact_resolver,
            site,
        )
        if choices.offline:
            resolved = replace(
                resolved,
                local_only=True,
                publishable=False,
                blocking_reasons=resolved.blocking_reasons + ("offline local-only",),
            )
            print("preflight offline local-only")
        elif not resolved.local_only:
            server_publishability_preflight(
                resolved,
                cli_version,
                site,
                dependencies.preflight_http,
                suite_identity,
            )
        elif resolved.source_kind == "raw_hf" and choices.submit is not True:
            _print_ranked_remediation(args, resolved, prefix="preview", file=sys.stdout)
        else:
            for reason in resolved.blocking_reasons:
                print(f"preflight {reason}")
        if choices.submit is True and (choices.offline or resolved.local_only):
            _print_ranked_remediation(args, resolved, prefix="error", file=sys.stderr)
            return 2
        options = build_serve_options(
            OneShotServeRequest(
                args=args,
                resolved=resolved,
                root=root,
                suite_identity=suite_identity,
            ),
        )
        options = replace(options, suite_dir=suite_ref.path)
        if needs_wsl_agentic(options):
            agentic_preflight = dependencies.agentic_preflight or preflight_agentic_if_needed
            options = replace(options, agentic_preflight=agentic_preflight(options, root))
        tokenizer_plan = prepare_tokenizer_plan(
            TokenizerPlanRequest(
                resolved,
                root,
                getattr(args, "resume", None),
                cli_version,
                dependencies.hf_client,
                suite_identity,
            ),
        )
        resolved = tokenizer_plan.resolved
        downloaded = download_artifact_atomic(resolved.artifact, root / "models", hf_client=dependencies.hf_client)
        tokenizer = download_tokenizer_snapshot(
            repo_id=tokenizer_plan.repo_id,
            revision=tokenizer_plan.revision,
            destination_dir=root / "tokenizer",
            hf_client=dependencies.hf_client,
        )
        write_download_plan_lock(
            tokenizer_plan.context,
            OneShotDownloadLockFacts(
                artifact_path=downloaded.path,
                artifact_sha256=downloaded.sha256,
                tokenizer_snapshot_sha256=tokenizer.snapshot_sha256,
            ),
        )
        if needs_wsl_agentic(options):
            agentic_preflight = dependencies.agentic_preflight or preflight_agentic_if_needed
            try:
                options = replace(options, agentic_preflight=agentic_preflight(options, root))
            except AgenticSetupError as error:
                raise AgenticSetupError(
                    detail=error.detail,
                    model_download_started=True,
                ) from error
        monitor = dependencies.sleep_monitor or SleepGapMonitor(
            allow_sleep_risk=bool(getattr(args, "allow_sleep_risk", False)),
        )
        monitor.checkpoint()
        record = _bench_runner(dependencies)(replace(
            options,
            model_file=downloaded.path,
            hf_model_id=resolved.tokenizer_repo,
            hf_revision=tokenizer_plan.revision,
            gguf_repo_only=resolved.tokenizer_repo is None,
        ))
        monitor.checkpoint()
        record = (dependencies.coding_grader or _grade_coding_run)(
            root / "localbench-run.json",
            suite_ref.path,
            image=DEFAULT_IMAGE,
            docker_env=coding_docker_env,
        )
        print_scorecard(record)
        return maybe_submit(
            OneShotSubmitContext(
                args=args,
                run_root=root,
                submit_choice=choices.submit,
                resolved=resolved,
                submitter=dependencies.submitter,
                input_fn=input_fn,
                record=record,
                suite_identity=suite_identity,
            ),
        )
    except KeyboardInterrupt:
        print("error      one-shot bench interrupted", file=sys.stderr)
        return EXIT_USER_INTERRUPTED
    except SleepWakeClockGap as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_USER_INTERRUPTED
    except AgenticSetupError as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_AGENTIC_SETUP_REQUIRED
    except CodingExecError as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_PREFLIGHT_FAILED
    except (
        CatalogResolutionError,
        OneShotChoiceError,
        PlanLockMismatch,
        DownloadError,
        SuiteResolutionError,
    ) as error:
        print(f"error      {error}", file=sys.stderr)
        return 2
    except SubmitRunError as error:
        print(f"error      {error}", file=sys.stderr)
        return error.exit_code
    except Exception as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_INTERNAL_RUNNER_BUG


def _print_ranked_remediation(
    args: argparse.Namespace,
    resolved: ResolvedOneShotModel,
    *,
    prefix: str,
    file: TextIO,
) -> None:
    base_model = resolved.tokenizer_repo or "<exact-non-GGUF-HF-repo>"
    server_bin = getattr(args, "llama_server_path", None) or getattr(args, "server_bin", None)
    server_bin_text = str(server_bin) if server_bin is not None else "<path-to-llama-server>"
    run_dir = PurePosixPath("runs") / "bench" / resolved.model_id
    model_ref = resolved.artifact.model_ref or "<pinned-model-ref>"
    print(f"{prefix:<11}{ONE_SHOT_LOCAL_PREVIEW_REASON}", file=file)
    print(
        "ranked     localbench bench --runtime llama.cpp "
        f"--model-ref '{model_ref}' --model-id {resolved.model_id} "
        f"--server-bin {server_bin_text} --hf-model-id {base_model} "
        "--lane bounded-final-v2 --profile auto --tier standard --ctx 32768 --seed 1234 "
        f"--allow-untrusted-code --out {run_dir}",
        file=file,
    )
    print(
        f"submit     localbench submit run --run {run_dir} --base-model {base_model}",
        file=file,
    )


def _bench_runner(deps: OneShotRunnerDeps) -> BenchRunner:
    if deps.bench_runner is not None:
        return deps.bench_runner
    return _default_bench_runner


def _default_bench_runner(options: ServeBenchOptions) -> JsonObject:
    return anyio.run(run_orchestrated_bench, options)


def _grade_coding_run(
    run_path: Path,
    suite_dir: Path,
    *,
    image: str,
    docker_env: DockerEnv,
) -> JsonObject:
    return execute_pending_artifacts(
        run_path,
        CodingExecConfig(
            endpoint="",
            model="one-shot-coding-grader",
            suite_dir=suite_dir,
            image=image,
            out=run_path,
            allow_untrusted_code=True,
        ),
        docker_env=docker_env,
    )


def _suite_identity(args: argparse.Namespace) -> OneShotSuiteIdentity:
    return FULL_EXEC_SUITE_IDENTITY


def _verify_suite_identity(suite_dir: Path, expected: OneShotSuiteIdentity) -> None:
    manifest_path = suite_dir / SUITE_RELEASE_MANIFEST_FILE
    try:
        manifest = read_json_object(manifest_path)
    except (OSError, ValueError) as error:
        raise SuiteResolutionError(
            f"suite {expected.release_id!r} is missing a valid release manifest: {error}",
        ) from error
    release_id = manifest.get("suite_release_id")
    declared_sha = manifest.get("suite_manifest_sha256")
    actual_sha = suite_manifest_sha256(manifest)
    if release_id != expected.release_id:
        raise SuiteResolutionError(
            f"suite release mismatch: {release_id!r} != {expected.release_id!r}",
        )
    if declared_sha != expected.manifest_sha256 or actual_sha != expected.manifest_sha256:
        raise SuiteResolutionError(
            "suite release manifest sha256 mismatch: "
            f"declared={declared_sha!r} actual={actual_sha!r} "
            f"expected={expected.manifest_sha256!r}",
        )
    verify_suite_release_files(suite_dir, manifest)
