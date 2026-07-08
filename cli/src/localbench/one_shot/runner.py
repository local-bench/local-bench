from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

import anyio

from localbench._types import JsonObject
from localbench.exit_codes import EXIT_INTERNAL_RUNNER_BUG, EXIT_USER_INTERRUPTED
from localbench.one_shot.catalog import CatalogResolutionError, resolve_one_shot_model
from localbench.one_shot.catalog_loader import HttpCatalogLoader
from localbench.one_shot.download import (
    DownloadError,
    HfDownloadClient,
    download_artifact_atomic,
    download_tokenizer_snapshot,
)
from localbench.one_shot.preflight import (
    JsonPostClient,
    OneShotChoiceError,
    PlanLockMismatch,
    build_publishability_preflight_payload,
    request_publishability_preflight,
    validate_one_shot_choices,
)
from localbench.one_shot.plan_lock import (
    OneShotDownloadLockFacts,
    write_download_plan_lock,
)
from localbench.one_shot.raw_hf import HuggingFaceRawArtifactResolver
from localbench.one_shot.sleep import SleepGapMonitor, SleepWakeClockGap
from localbench.one_shot.submission import OneShotSubmitContext, Submitter, maybe_submit
from localbench.one_shot.tokenizer_pin import TokenizerPlanRequest, prepare_tokenizer_plan
from localbench.one_shot.types import (
    FULL_EXEC_SUITE_RELEASE_ID,
    OneShotArtifact,
    ResolvedOneShotModel,
)
from localbench.progress import ProgressReporter
from localbench.serving.options import ServeBenchOptions
from localbench.serving.runner import run_orchestrated_bench
from localbench.submissions.submit_run import DEFAULT_SITE


class CatalogLoader(Protocol):
    def load(self, *, requested_model: str, site: str) -> dict[str, object]: ...


class BenchRunner(Protocol):
    def __call__(self, options: ServeBenchOptions) -> JsonObject: ...


class RawArtifactResolver(Protocol):
    def resolve_raw_artifact(self, *, repo_id: str, quant: str | None) -> OneShotArtifact: ...


@dataclass(slots=True)
class OneShotRunnerDeps:
    catalog_loader: CatalogLoader | None = None
    preflight_http: JsonPostClient | None = None
    hf_client: HfDownloadClient | None = None
    bench_runner: BenchRunner | None = None
    submitter: Submitter | None = None
    raw_artifact_resolver: RawArtifactResolver | None = None
    sleep_monitor: "SleepGapMonitor | None" = None


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
    run_root = _run_root(args)
    try:
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
        resolved = _resolve(
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
            _server_publishability_preflight(resolved, cli_version, site, dependencies.preflight_http)
        else:
            for reason in resolved.blocking_reasons:
                print(f"preflight {reason}")
        if choices.submit is True and (choices.offline or resolved.local_only):
            print("error      one-shot run is local-only and cannot be submitted", file=sys.stderr)
            return 2
        tokenizer_plan = prepare_tokenizer_plan(
            TokenizerPlanRequest(resolved, run_root, getattr(args, "resume", None), cli_version, dependencies.hf_client),
        )
        resolved = tokenizer_plan.resolved
        downloaded = download_artifact_atomic(resolved.artifact, run_root / "models", hf_client=dependencies.hf_client)
        tokenizer = download_tokenizer_snapshot(
            repo_id=tokenizer_plan.repo_id,
            revision=tokenizer_plan.revision,
            destination_dir=run_root / "tokenizer",
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
        monitor = dependencies.sleep_monitor or SleepGapMonitor(
            allow_sleep_risk=bool(getattr(args, "allow_sleep_risk", False)),
        )
        monitor.checkpoint()
        record = _bench_runner(dependencies)(ServeBenchOptions(
            runtime="llama.cpp",
            model_file=downloaded.path,
            model_ref=None,
            model_id=resolved.model_id,
            server_bin=_server_bin(args),
            ctx=32768,
            determinism="strict",
            tier="standard",
            bench="all",
            lane="bounded-final-v2",
            profile="auto",
            seed=1234,
            max_items=getattr(args, "max_items", None),
            suite=FULL_EXEC_SUITE_RELEASE_ID,
            suite_source=getattr(args, "suite_source", None),
            suite_dir=getattr(args, "suite_dir", None),
            out=run_root,
            resume=getattr(args, "resume", None),
            retry_errored=False,
            cache_dir=getattr(args, "cache_dir", None),
            threads=int(getattr(args, "threads", 8)),
            threads_batch=int(getattr(args, "threads_batch", 8)),
            reasoning_activation=None,
            hf_model_id=resolved.tokenizer_repo,
            hf_revision=tokenizer_plan.revision,
            gguf_repo_only=resolved.tokenizer_repo is None,
            wsl_venv_python=str(getattr(args, "wsl_venv_python", "~/appworld-harness/venv/bin/python3")),
            appworld_root=str(getattr(args, "appworld_root", "/home/michael/appworld-data")),
            progress_reporter=ProgressReporter(),
        ))
        monitor.checkpoint()
        _print_scorecard(record)
        return maybe_submit(
            OneShotSubmitContext(
                args=args,
                run_root=run_root,
                submit_choice=choices.submit,
                resolved=resolved,
                submitter=dependencies.submitter,
                input_fn=input_fn,
            ),
        )
    except KeyboardInterrupt:
        print("error      one-shot bench interrupted", file=sys.stderr)
        return EXIT_USER_INTERRUPTED
    except SleepWakeClockGap as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_USER_INTERRUPTED
    except (CatalogResolutionError, OneShotChoiceError, PlanLockMismatch, DownloadError) as error:
        print(f"error      {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_INTERNAL_RUNNER_BUG


def _resolve(
    args,
    vram_gb: float | None,
    catalog_loader: CatalogLoader | None,
    raw_artifact_resolver: RawArtifactResolver | None,
    site: str,
) -> ResolvedOneShotModel:
    requested_model = str(getattr(args, "one_shot_model"))
    catalog = {"models": []} if "/" in requested_model else (catalog_loader or HttpCatalogLoader()).load(
        requested_model=requested_model,
        site=site,
    )
    resolved = resolve_one_shot_model(
        requested_model,
        catalog,
        quant=getattr(args, "quant", None),
        vram_gb=vram_gb,
    )
    if resolved.local_only and resolved.artifact.filename == "":
        resolver = raw_artifact_resolver or HuggingFaceRawArtifactResolver()
        artifact = resolver.resolve_raw_artifact(
            repo_id=requested_model,
            quant=getattr(args, "quant", None),
        )
        resolved = replace(
            resolved,
            model_id=Path(artifact.filename).stem,
            tokenizer_repo=requested_model,
            tokenizer_revision=artifact.revision,
            artifact=artifact,
        )
    print(f"resolve   {resolved.display_name} {resolved.artifact.quant_label}")
    return resolved


def _server_publishability_preflight(
    resolved: ResolvedOneShotModel,
    cli_version: str,
    site: str,
    http: JsonPostClient | None,
) -> None:
    payload = build_publishability_preflight_payload(resolved, cli_version=cli_version)
    response = request_publishability_preflight(site, payload, http=http)
    if response.get("publishable") is not True:
        reasons = response.get("reasons")
        detail = ", ".join(str(item) for item in reasons) if isinstance(reasons, list) else "preflight rejected"
        raise CatalogResolutionError(f"publishability preflight rejected one-shot run: {detail}")
    print("preflight publishable")


def _bench_runner(deps: OneShotRunnerDeps) -> BenchRunner:
    if deps.bench_runner is not None:
        return deps.bench_runner
    return _default_bench_runner


def _default_bench_runner(options: ServeBenchOptions) -> JsonObject:
    return anyio.run(run_orchestrated_bench, options)


def _print_scorecard(record: JsonObject) -> None:
    scores = record.get("scores")
    if isinstance(scores, dict) and isinstance(scores.get("headline_score"), int | float):
        print(f"scorecard headline {float(scores['headline_score']):.3f}")
    else:
        print("scorecard written")


def _run_root(args) -> Path:
    resume = getattr(args, "resume", None)
    if isinstance(resume, Path):
        return resume
    out = getattr(args, "out", None)
    if isinstance(out, Path):
        return out
    requested_model = str(getattr(args, "one_shot_model", "model"))
    return Path("runs") / "bench" / requested_model.replace("/", "__")


def _server_bin(args) -> Path | None:
    value = getattr(args, "llama_server_path", None) or getattr(args, "server_bin", None)
    return value if isinstance(value, Path) else None
