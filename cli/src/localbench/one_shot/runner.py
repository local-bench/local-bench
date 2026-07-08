from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, cast

import anyio
import httpx

from localbench._types import JsonObject
from localbench.exit_codes import EXIT_COMPLETE, EXIT_INTERNAL_RUNNER_BUG, EXIT_SUBMISSION_FAILED, EXIT_USER_INTERRUPTED
from localbench.one_shot.catalog import CatalogResolutionError, resolve_one_shot_model
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
    validate_resume_plan_lock,
    write_plan_lock,
)
from localbench.one_shot.types import (
    FULL_EXEC_SUITE_MANIFEST_SHA256,
    FULL_EXEC_SUITE_RELEASE_ID,
    ONE_SHOT_PLAN_SCHEMA_VERSION,
    OneShotArtifact,
    ResolvedOneShotModel,
)
from localbench.progress import ProgressReporter
from localbench.serving.options import ServeBenchOptions
from localbench.serving.runner import run_orchestrated_bench
from localbench.submissions.submit_run import DEFAULT_SITE, SubmitRunOptions, SubmitRunResult, submit_finished_run


class CatalogLoader(Protocol):
    def load(self, *, requested_model: str, site: str) -> dict[str, object]: ...


class BenchRunner(Protocol):
    def __call__(self, options: ServeBenchOptions) -> JsonObject: ...


class Submitter(Protocol):
    def __call__(self, options: SubmitRunOptions) -> SubmitRunResult: ...


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


@dataclass(frozen=True, slots=True)
class SleepWakeClockGap(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True)
class SleepGapMonitor:
    threshold_seconds: float = 300.0
    allow_sleep_risk: bool = False
    _last_wall: float | None = None
    _last_monotonic: float | None = None

    def checkpoint(self, *, wall_seconds: float | None = None, monotonic_seconds: float | None = None) -> None:
        wall = time.time() if wall_seconds is None else wall_seconds
        monotonic = time.monotonic() if monotonic_seconds is None else monotonic_seconds
        if self._last_wall is not None and self._last_monotonic is not None:
            wall_delta = wall - self._last_wall
            monotonic_delta = monotonic - self._last_monotonic
            clock_gap = wall_delta - monotonic_delta
            if clock_gap > self.threshold_seconds and not self.allow_sleep_risk:
                raise SleepWakeClockGap(
                    f"sleep/wake clock gap detected ({clock_gap:.1f}s); rerun with --allow-sleep-risk to continue",
                )
        self._last_wall = wall
        self._last_monotonic = monotonic


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
        _validate_or_write_lock(run_root, resolved, cli_version, resume=getattr(args, "resume", None))
        downloaded = download_artifact_atomic(resolved.artifact, run_root / "models", hf_client=dependencies.hf_client)
        tokenizer_repo = resolved.tokenizer_repo or resolved.artifact.repo_id
        tokenizer_revision = resolved.tokenizer_revision or resolved.artifact.revision
        tokenizer = download_tokenizer_snapshot(
            repo_id=tokenizer_repo,
            revision=tokenizer_revision,
            destination_dir=run_root / "tokenizer",
            hf_client=dependencies.hf_client,
        )
        _write_download_lock(run_root, resolved, cli_version, downloaded.path, downloaded.sha256, tokenizer.snapshot_sha256)
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
            gguf_repo_only=resolved.tokenizer_repo is None,
            wsl_venv_python=str(getattr(args, "wsl_venv_python", "~/appworld-harness/venv/bin/python3")),
            appworld_root=str(getattr(args, "appworld_root", "/home/michael/appworld-data")),
            progress_reporter=ProgressReporter(),
        ))
        monitor.checkpoint()
        _print_scorecard(record)
        return _maybe_submit(args, run_root, choices.submit, resolved, dependencies.submitter, input_fn)
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


class HttpCatalogLoader:
    def load(self, *, requested_model: str, site: str) -> dict[str, object]:
        url = f"{site.rstrip('/')}/data/models/{requested_model}.json"
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            value = response.json()
        if not isinstance(value, dict):
            raise CatalogResolutionError("model catalog response must be a JSON object")
        if "models" in value:
            return {str(key): item for key, item in value.items()}
        return {"models": [value]}


class HuggingFaceRawArtifactResolver:
    def resolve_raw_artifact(self, *, repo_id: str, quant: str | None) -> OneShotArtifact:
        try:
            from huggingface_hub import HfApi
        except ImportError as error:
            raise DownloadError("install localbench[hf] to resolve raw Hugging Face GGUF repos") from error
        info = HfApi().model_info(repo_id, files_metadata=True)
        revision = getattr(info, "sha", None)
        if not isinstance(revision, str) or len(revision) != 40:
            raise CatalogResolutionError("raw HF repo must resolve to a full pinned commit SHA")
        selected = _select_raw_gguf(getattr(info, "siblings", ()), quant)
        filename = _sibling_filename(selected)
        return OneShotArtifact(
            repo_id=repo_id,
            filename=filename,
            revision=revision.lower(),
            quant_label=quant or _quant_from_filename(filename),
            sha256=_sibling_sha256(selected),
            size_bytes=_sibling_size(selected),
            vram_required_gb_8k=None,
            vram_required_gb_32k=None,
        )


def _select_raw_gguf(siblings: object, quant: str | None) -> object:
    if not isinstance(siblings, list | tuple):
        raise CatalogResolutionError("raw HF repo file listing is unavailable")
    candidates: list[object] = []
    for sibling in siblings:
        filename = _sibling_filename_or_none(sibling)
        if filename is None or not filename.lower().endswith(".gguf"):
            continue
        if quant is not None and quant.lower() not in filename.lower():
            continue
        candidates.append(sibling)
    if not candidates:
        suffix = f" matching {quant}" if quant is not None else ""
        raise CatalogResolutionError(f"raw HF repo has no GGUF artifact{suffix}")
    return sorted(candidates, key=_sibling_filename)[0]


def _sibling_filename(sibling: object) -> str:
    filename = _sibling_filename_or_none(sibling)
    if filename is None:
        raise CatalogResolutionError("raw HF repo file listing contains an unnamed file")
    return filename


def _sibling_filename_or_none(sibling: object) -> str | None:
    value = getattr(sibling, "rfilename", None) or getattr(sibling, "path", None)
    return value if isinstance(value, str) and value else None


def _sibling_size(sibling: object) -> int | None:
    value = getattr(sibling, "size", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sibling_sha256(sibling: object) -> str | None:
    lfs = getattr(sibling, "lfs", None)
    value = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
    if isinstance(value, str) and len(value) == 64:
        return value.lower()
    return None


def _quant_from_filename(filename: str) -> str:
    upper = filename.upper()
    for label in ("Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K", "IQ2_XS", "F16"):
        if label in upper:
            return label
    return "unknown"


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


def _validate_or_write_lock(
    run_root: Path,
    resolved: ResolvedOneShotModel,
    cli_version: str,
    *,
    resume: Path | None,
) -> None:
    plan = _plan_lock(resolved, cli_version)
    lock_path = run_root / "plan.lock.json"
    if resume is not None:
        validate_resume_plan_lock(lock_path, plan)
        return
    write_plan_lock(lock_path, plan)


def _write_download_lock(
    run_root: Path,
    resolved: ResolvedOneShotModel,
    cli_version: str,
    artifact_path: Path,
    artifact_sha256: str,
    tokenizer_snapshot_sha256: str | None,
) -> None:
    plan = _plan_lock(resolved, cli_version)
    plan.update(
        {
            "artifact_path": str(artifact_path),
            "artifact_sha256": artifact_sha256,
            "tokenizer_snapshot_sha256": tokenizer_snapshot_sha256,
        },
    )
    write_plan_lock(run_root / "plan.lock.json", plan)


def _plan_lock(resolved: ResolvedOneShotModel, cli_version: str) -> dict[str, object]:
    return {
        "schema_version": ONE_SHOT_PLAN_SCHEMA_VERSION,
        "requested_model": resolved.requested,
        "quant_label": resolved.artifact.quant_label,
        "artifact_revision": resolved.artifact.revision,
        "artifact_filename": resolved.artifact.filename,
        "suite_release_id": FULL_EXEC_SUITE_RELEASE_ID,
        "suite_manifest_sha256": FULL_EXEC_SUITE_MANIFEST_SHA256,
        "cli_version": cli_version,
    }


def _bench_runner(deps: OneShotRunnerDeps) -> BenchRunner:
    if deps.bench_runner is not None:
        return deps.bench_runner
    return _default_bench_runner


def _default_bench_runner(options: ServeBenchOptions) -> JsonObject:
    return cast(JsonObject, anyio.run(run_orchestrated_bench, options))


def _maybe_submit(
    args,
    run_root: Path,
    submit_choice: bool | None,
    resolved: ResolvedOneShotModel,
    submitter: Submitter | None,
    input_fn,
) -> int:
    should_submit = submit_choice
    if should_submit is None and not resolved.local_only:
        print("submit? [y/N] ", end="")
        should_submit = input_fn().strip().lower() in {"y", "yes"}
    if should_submit is not True:
        print("submit    skipped")
        return EXIT_COMPLETE
    result = (submitter or submit_finished_run)(_submit_options(args, run_root))
    for line in result.lines:
        print(line)
    return result.exit_code if result.exit_code != 0 else EXIT_COMPLETE


def _submit_options(args, run_root: Path) -> SubmitRunOptions:
    return SubmitRunOptions(
        site=str(getattr(args, "site", None) or DEFAULT_SITE),
        run=run_root / "localbench-run.json",
        bundle=None,
        suite_dir=getattr(args, "suite_dir", None),
        signing_key=getattr(args, "signing_key", None),
        display_name=getattr(args, "display_name", None),
        bypass_token=getattr(args, "bypass_token", None),
        bypass_token_file=getattr(args, "bypass_token_file", None),
        dry_run=False,
    )


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
