"""Benchmark suite orchestration for localbench."""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NotRequired, TypeAlias, TypedDict, cast

import httpx

from localbench._response import empty_usage
from localbench._requests import utc_now
from localbench._scoring import (
    BenchAggregate,
    RunTotals,
    ScoredItem,
    aggregate,
    composite,
    estimated_cost,
    run_totals,
    score_bench,
    scorer_unavailable_warning,
)
from localbench._suite import (
    RenderedBench,
    first_prompt,
    item_hashes,
    read_json_object,
    render_benches,
    suite_version,
)
from localbench._types import BenchmarkItem, ItemResult, JsonObject, JsonValue, Usage
from localbench.budget_forcing import CAPPED_THINKING_THINK_BUDGET
from localbench.campaign import (
    CampaignConfig,
    CampaignPaths,
    StatusUpdate,
    campaign_paths,
    initialize_campaign,
    write_status,
)
from localbench.campaign_checkpoints import (
    CompletedBench,
    ExpectedItemCheckpoint,
    append_item_checkpoint,
    append_scored_checkpoint,
    checkpoint_segment_summaries,
    completed_benches,
    next_segment_id,
    read_partial_item_checkpoints,
    write_bench_complete,
)
from localbench.campaign_records import item_hash
from localbench.lane_conformance import assess_run_conformance
from localbench.manifest import ManifestContext, collect_manifest
from localbench.prompt_rendering import (
    PromptRenderer,
    ReasoningActivation,
    build_forced_prompt_renderer,
)
from localbench.providers import ReasoningEffort, provider_for_name
from localbench.reasoning_registry import ReasoningRegistryEntry, reasoning_entry_for_activation
from localbench.reasoning_leaks import registry_leak_regexes
from localbench.run_plan import resolve_run_benches
from localbench.run_schema import RUN_SCHEMA_VERSION
from localbench.runner import run_benchmark, write_json
from localbench.scoring.axes import AXES
from localbench.scoring.axis_status import (
    AxisStatusBlock,
    axis_key_for_bench,
    axis_status_for_benches,
    mark_axis_not_measured,
)
from localbench.scorers.ruler import estimate_prompt_tokens
from localbench.submissions.foundation import normalize_result_bundle
from localbench.suite_resolver import DEFAULT_SUITE_ID, resolve_suite_dir

if TYPE_CHECKING:
    from localbench.scoring.agentic_exec.benchmark import ModelFactory, SandboxFactory
    from localbench.scoring.agentic_exec.funnel import RerunAggregate, StageRunResult
    from localbench.scoring.agentic_exec.loop_types import BenchmarkReport

BenchChoice: TypeAlias = str
TierChoice = Literal["quick", "standard"]
LaneChoice = Literal["answer-only", "capped-thinking", "api-uncapped"]
ReasoningEffortChoice = ReasoningEffort
ReasoningActivationChoice = ReasoningActivation
ModelIdentitySource = Literal["gguf.embedded", "external.file", "server.override"]

_RULER_TRUNCATION_RATIO: Final = 0.80
_RULER_TRUNCATION_MIN_GAP: Final = 2_048
_APPWORLD_C_BENCH: Final = "appworld_c"
_SERVE_HEALTH_CIRCUIT_BREAKER_LIMIT: Final = 3
_SERVE_HEALTH_CIRCUIT_BREAKER_REASON: Final = "server_unreachable_circuit_breaker"
# Frozen per-turn output-token cap for the inline SCORED agentic campaign. Every official
# AppWorld-C .scored run (qwen36-27b all quants, qwopus, qwable-coder, gemma4-31b) uses 3072.
# The LoopConfig default (1024) truncates verbose native-thinking models mid-reasoning ->
# finish_reason="length" -> cap_exceeded -> harness-dominated ~0 ASR. The inline campaign must
# override it to match the board's frozen cap, else its mean ASR is not comparable.
_AGENTIC_SCORED_MAX_OUTPUT_TOKENS_PER_TURN: Final = 3072
_HEADLINE_AXIS_KEYS: Final = tuple(axis.key for axis in AXES if axis.role == "headline")


class LocalbenchRun(TypedDict):
    schema: NotRequired[str]
    schema_version: str
    submission_ticket_id: NotRequired[str | None]
    server_nonce: NotRequired[str | None]
    issued_at: NotRequired[str | None]
    run_started_at: str
    run_finished_at: str
    source: NotRequired[str]
    producer: NotRequired[str]
    tier: str
    account: NotRequired[str | None]
    serving_mode: NotRequired[str]
    model: JsonObject
    manifest: JsonObject
    axis_status: AxisStatusBlock
    headline_complete: bool
    benches: dict[str, BenchAggregate]
    composite: NotRequired[float]
    scores: NotRequired[JsonObject]
    conformance: JsonObject
    items: list[ScoredItem]
    totals: RunTotals
    warnings: list[str]
    output_path: NotRequired[str]
    agentic_run: NotRequired[JsonObject]
    estimated_cost_usd: NotRequired[float]
    resumed: NotRequired[bool]
    resume_count: NotRequired[int]
    segments: NotRequired[list[JsonObject]]
    trust_tier: NotRequired[str]
    serving_verification_level: NotRequired[str]


class UnsafeResumeError(RuntimeError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class ServeHealthCircuitBreakerError(RuntimeError):
    reason: str = _SERVE_HEALTH_CIRCUIT_BREAKER_REASON

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class PublishableCappedThinkingError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class AgenticOutcome:
    aggregate: BenchAggregate
    items: list[ScoredItem]
    provenance: JsonObject


@dataclass(frozen=True, slots=True)
class BenchItemContext:
    bench: RenderedBench
    seq: int
    item_hash: str
    source_item: Mapping[str, JsonValue]
    benchmark_item: BenchmarkItem


@dataclass(frozen=True, slots=True)
class OrchestrateConfig:
    endpoint: str
    model: str
    suite: str = DEFAULT_SUITE_ID
    bench: BenchChoice = "all"
    tier: TierChoice = "quick"
    concurrency: int = 4
    out: Path | None = None
    api_key: str | None = None
    max_items: int | None = None
    suite_dir: Path | None = None
    suite_source: Path | None = None
    accept_suite_terms: bool = False
    cache_root: Path | None = None
    price_in: float | None = None
    price_out: float | None = None
    lane: LaneChoice = "answer-only"
    provider: str = "local"
    reasoning_effort: ReasoningEffortChoice | None = None
    hf_model_id: str | None = None
    reasoning_activation: ReasoningActivationChoice = "qwen3"
    max_tokens: int | None = None
    resume: Path | None = None
    publishable: bool = False
    sampler_temperature: float | None = None
    sampler_top_k: int | None = None
    sampler_top_p: float | None = None
    sampler_min_p: float | None = None
    sampler_seed: int | None = None
    determinism_policy: str | None = None
    model_file: Path | None = None
    model_family: str | None = None
    quant_label: str | None = None
    model_format: str | None = None
    tokenizer_file: Path | None = None
    chat_template_file: Path | None = None
    tokenizer_digest: str | None = None
    tokenizer_digest_source: ModelIdentitySource | None = None
    chat_template_digest: str | None = None
    chat_template_digest_source: ModelIdentitySource | None = None
    runtime_name: str | None = None
    runtime_version: str | None = None
    kv_cache_quant: str | None = None
    ctx_len_configured: int | None = None
    parallel_slots: int | None = None
    build_flags: str | None = None
    runtime_backend: str | None = None
    cuda_version: str | None = None
    runner_build_id: str | None = None
    server_fingerprint: str | None = None
    resume_identity: str | None = None
    serve_fingerprint: JsonObject | None = None
    retry_errored: bool = False


async def run_localbench(
    config: OrchestrateConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    agentic_sandbox_factory: SandboxFactory | None = None,
    agentic_model_factory: ModelFactory | None = None,
    agentic_task_ids: list[str] | None = None,
    agentic_provenance_extra: JsonObject | None = None,
) -> LocalbenchRun:
    """Run selected suite benches, score responses, write JSON, and return the record."""
    suite_ref = resolve_suite_dir(
        suite_id=config.suite,
        suite_dir=config.suite_dir,
        accept_suite_terms=config.accept_suite_terms,
        source=config.suite_source,
        cache_root=config.cache_root,
    )
    suite_dir = suite_ref.path
    suite = read_json_object(suite_dir / "suite.json")
    started_at = utc_now()
    started_perf = time.perf_counter()
    output_path = _campaign_output_path(config)
    warnings: list[str] = []
    provider = provider_for_name(config.provider)
    resolved = resolve_run_benches(config.bench, suite)
    run_agentic = _APPWORLD_C_BENCH in resolved
    bench_choice = ",".join(bench for bench in resolved if bench != _APPWORLD_C_BENCH)
    rendered_benches = render_benches(
        bench_choice,
        config.tier,
        config.max_items,
        suite_dir,
        suite,
        warnings,
    )
    rendered_benches = _exclude_exec_lane(rendered_benches, suite, warnings)
    suite_axes = suite.get("axes")
    suite_axis_map = suite_axes if isinstance(suite_axes, dict) else None
    if config.max_tokens is not None:
        for rendered in rendered_benches:
            for benchmark_item in rendered.benchmark_items:
                existing = benchmark_item.get("max_tokens")
                benchmark_item["max_tokens"] = (
                    config.max_tokens
                    if not isinstance(existing, int)
                    else min(existing, config.max_tokens)
                )
    if _has_sampler_overrides(config):
        _apply_sampler_overrides(rendered_benches, config)
    items: list[ScoredItem] = []
    sampling_by_bench: dict[str, JsonObject] = {}
    item_files: list[str] = []

    if config.provider == "local" and config.lane == "answer-only":
        # Local-runtime lane: disable Qwen3-family thinking via vLLM's
        # chat_template_kwargs passthrough (llama.cpp/Ollama ignore the field;
        # cloud lanes never send it because OpenAI-style APIs reject unknown params).
        for bench in rendered_benches:
            for benchmark_item in bench.benchmark_items:
                benchmark_item["sampling_params"]["chat_template_kwargs"] = {
                    "enable_thinking": False,
                }

    scorer_unavailable_axes: dict[str, str] = {}
    scorable_benches: list[RenderedBench] = []
    for bench in rendered_benches:
        readiness_warning = scorer_unavailable_warning(bench)
        if readiness_warning is not None:
            warnings.append(readiness_warning)
            scorer_unavailable_axes[
                axis_key_for_bench(bench.name, suite_axis_map)
            ] = readiness_warning
            continue
        scorable_benches.append(bench)

    paths = campaign_paths(output_path, config.resume)
    session_segment_id = "segment-1" if config.resume is None else next_segment_id(paths)
    segment_completed_item_ids: list[str] = []
    total_items = sum(len(bench.benchmark_items) for bench in scorable_benches)
    campaign_config = CampaignConfig(
        endpoint=config.endpoint,
        model=config.model,
        suite_id=suite_ref.suite_id,
        suite_hash=suite_ref.suite_hash,
        suite_dir=suite_dir,
        suite_terms_accepted=config.accept_suite_terms,
        tier=config.tier,
        lane=config.lane,
        provider=provider.name,
        concurrency=config.concurrency,
        max_items=config.max_items,
        max_tokens=config.max_tokens,
        reasoning_effort=config.reasoning_effort,
        reasoning_activation=config.reasoning_activation,
        hf_model_id=config.hf_model_id,
        output_path=output_path,
        server_fingerprint=config.server_fingerprint,
        resume_identity=config.resume_identity,
        serve_fingerprint=config.serve_fingerprint,
    )
    if config.resume is None:
        initialize_campaign(
            paths,
            campaign_config,
            suite,
            suite_dir,
            scorable_benches,
            started_at=started_at,
        )
    else:
        _validate_resume_campaign(paths.root / "campaign.json", campaign_config)
        write_status(
            paths,
            StatusUpdate(
                state="running",
                current_bench=None,
                current_item_index=None,
                current_item_id=None,
                completed_items=0,
                total_items=total_items,
                started_at=started_at,
            ),
        )
    all_completed = completed_benches(paths) if config.resume is not None else {}
    completed = _completed_benches_to_skip(all_completed, retry_errored=config.retry_errored)

    thinking_budget = 0
    prompt_renderer: PromptRenderer | None = None
    reasoning_registry_entry_id: str | None = None
    reasoning_leak_regexes: tuple[str, ...] = ()
    forcing_format = None
    if config.provider == "local" and config.lane == "capped-thinking":
        # Local capped-thinking enforces the locked thinking budget with two-pass forcing
        # (budget_forcing.run_forced_item). Stamp each item with the budget the runner reads.
        thinking_budget = _plumb_think_budget(scorable_benches, suite)
        if thinking_budget > 0:
            reasoning_entry = _capped_thinking_reasoning_entry(config)
            if reasoning_entry is not None:
                reasoning_registry_entry_id = reasoning_entry.id
                reasoning_leak_regexes = registry_leak_regexes(reasoning_entry.conformance)
                forcing_format = reasoning_entry.forcing
            prompt_renderer = _forced_prompt_renderer(config, provider.name)

    results_by_bench: dict[str, list[ItemResult]] = {}
    bench_aggregates: dict[str, BenchAggregate] = {}
    completed_items = 0
    consecutive_connection_failures = 0
    for bench in scorable_benches:
        sampling_by_bench[bench.name] = bench.decoding
        item_files.append(bench.item_file)
        if bench.name in completed:
            checkpoint = completed[bench.name]
            scored_from_disk = _checkpoint_scored_items(checkpoint)
            items.extend(_ordered_streamed_scored(bench, scored_from_disk))
            results_by_bench[bench.name] = _ordered_streamed_raw(bench, _checkpoint_raw_results(checkpoint))
            bench_aggregates[bench.name] = _checkpoint_aggregate(checkpoint)
            completed_items += len(scored_from_disk)
            continue
        item_context = _bench_item_context(bench)
        streamed_raw: list[ItemResult] = []
        streamed_scored: list[ScoredItem] = []
        if config.resume is not None:
            for checkpoint in read_partial_item_checkpoints(
                paths,
                bench.name,
                _expected_item_checkpoints(item_context),
            ):
                raw_result = cast(ItemResult, checkpoint.raw_result)
                if checkpoint.scored_item is None:
                    scored_item = _score_single_checkpoint(item_context[checkpoint.item_id], raw_result, warnings)
                    append_scored_checkpoint(
                        paths,
                        bench.name,
                        checkpoint.seq,
                        checkpoint.item_hash,
                        scored_item,
                        session_segment_id,
                    )
                else:
                    scored_item = cast(ScoredItem, checkpoint.scored_item)
                if config.retry_errored and _checkpoint_has_error(raw_result, scored_item):
                    # payload.error marks a non-measurement; wrong model answers are scored with
                    # error=None, so retry-errored only replaces non-measurements.
                    continue
                streamed_raw.append(raw_result)
                streamed_scored.append(scored_item)
        checkpointed_ids = {result["id"] for result in streamed_raw}
        pending_bench = _pending_bench(bench, checkpointed_ids)
        circuit_breaker_tripped = False

        def on_item_complete(result: ItemResult) -> bool:
            nonlocal consecutive_connection_failures, circuit_breaker_tripped
            single = item_context[result["id"]]
            scored_item = _score_single_checkpoint(single, result, warnings)
            streamed_raw.append(result)
            streamed_scored.append(scored_item)
            segment_completed_item_ids.append(result["id"])
            append_item_checkpoint(
                paths,
                bench.name,
                single.seq,
                single.item_hash,
                result,
                scored_item,
                session_segment_id,
            )
            write_status(
                paths,
                StatusUpdate(
                    state="running",
                    current_bench=bench.name,
                    current_item_index=single.seq,
                    current_item_id=result["id"],
                    completed_items=completed_items + len(streamed_scored),
                    total_items=total_items,
                    started_at=started_at,
                ),
            )
            if _is_connection_failure(result):
                consecutive_connection_failures += 1
            else:
                consecutive_connection_failures = 0
            circuit_breaker_tripped = (
                consecutive_connection_failures >= _SERVE_HEALTH_CIRCUIT_BREAKER_LIMIT
            )
            return circuit_breaker_tripped

        write_status(
            paths,
            StatusUpdate(
                state="running",
                current_bench=bench.name,
                current_item_index=0 if pending_bench.benchmark_items else None,
                current_item_id=pending_bench.benchmark_items[0]["id"] if pending_bench.benchmark_items else None,
                completed_items=completed_items + len(streamed_scored),
                total_items=total_items,
                started_at=started_at,
            ),
        )
        if pending_bench.benchmark_items:
            try:
                await run_benchmark(
                    base_url=config.endpoint,
                    model=config.model,
                    items=pending_bench.benchmark_items,
                    api_key=config.api_key,
                    concurrency=config.concurrency,
                    transport=transport,
                    provider=provider,
                    lane=config.lane,
                    effort=config.reasoning_effort,
                    hf_model_id=config.hf_model_id,
                    reasoning_activation=config.reasoning_activation,
                    prompt_renderer=prompt_renderer,
                    forcing_format=forcing_format,
                    on_item_complete=on_item_complete,
                )
                if circuit_breaker_tripped:
                    _write_circuit_breaker_status(
                        paths,
                        bench=bench.name,
                        completed_items=completed_items + len(streamed_scored),
                        total_items=total_items,
                        started_at=started_at,
                        last_completed_item_id=_last_completed_item_id(streamed_scored),
                    )
                    raise ServeHealthCircuitBreakerError()
            except (httpx.HTTPError, OSError, RuntimeError) as error:
                if isinstance(error, ServeHealthCircuitBreakerError):
                    raise
                write_status(
                    paths,
                    _failure_status(
                        paths,
                        bench=bench.name,
                        completed_items=completed_items + len(streamed_scored),
                        total_items=total_items,
                        started_at=started_at,
                        exit_code=70,
                        error=error,
                        last_completed_item_id=_last_completed_item_id(streamed_scored),
                    ),
                )
                raise
        raw_results = _ordered_streamed_raw(bench, streamed_raw)
        scored_items = _ordered_streamed_scored(bench, streamed_scored)
        items.extend(scored_items)
        results_by_bench[bench.name] = raw_results
        bench_aggregate = aggregate(bench.name, scored_items, bench.baseline)
        bench_aggregates[bench.name] = bench_aggregate
        write_bench_complete(paths, bench.name, raw_results, scored_items, bench_aggregate)
        completed_items += len(scored_items)
        write_status(
            paths,
            StatusUpdate(
                state="running",
                current_bench=bench.name,
                current_item_index=None,
                current_item_id=None,
                completed_items=completed_items,
                total_items=total_items,
                started_at=started_at,
            ),
        )

    benches = dict(bench_aggregates)
    agentic_provenance: JsonObject | None = None
    agentic_unavailable_detail: str | None = None
    if run_agentic:
        warning_start = len(warnings)
        agentic_outcome = _run_agentic_axis(
            config,
            warnings,
            sandbox_factory=agentic_sandbox_factory,
            model_factory=agentic_model_factory,
            task_ids=agentic_task_ids,
            results_dir=_agentic_results_dir(output_path),
            provenance_extra=agentic_provenance_extra,
        )
        if agentic_outcome is None:
            agentic_unavailable_detail = _agentic_warning_since(warnings, warning_start)
        else:
            benches[_APPWORLD_C_BENCH] = agentic_outcome.aggregate
            items.extend(agentic_outcome.items)
            agentic_provenance = agentic_outcome.provenance

    wall_time = time.perf_counter() - started_perf
    finished_at = utc_now()
    totals = run_totals(items, wall_time)
    axis_status = axis_status_for_benches(
        benches,
        suite_axis_map,
    )
    if run_agentic and agentic_unavailable_detail is not None:
        mark_axis_not_measured(
            axis_status,
            "agentic",
            reason="sandbox_unavailable",
            detail=agentic_unavailable_detail,
        )
    for axis, warning in scorer_unavailable_axes.items():
        mark_axis_not_measured(
            axis_status,
            axis,
            reason="scorer_unavailable",
            detail=warning,
        )
    headline_complete = _headline_complete(axis_status)
    manifest = await collect_manifest(
        ManifestContext(
            endpoint=config.endpoint,
            requested_model=config.model,
            suite_version=suite_version(suite),
            tier=config.tier,
            lane=config.lane,
            item_set_hashes=item_hashes(suite_dir, item_files),
            sampling_by_bench=sampling_by_bench,
            concurrency=max(1, config.concurrency),
            started_at=started_at,
            finished_at=finished_at,
            wall_clock_s=wall_time,
            totals={
                "items": totals["n_items"],
                "errors": totals["n_errors"],
                "prompt_tokens": totals["prompt_tokens"],
                "completion_tokens": totals["completion_tokens"],
                "total_tokens": totals["total_tokens"],
                "active_wall_seconds": wall_time,
                "completion_tokens_per_second": totals["completion_tokens_per_second"],
            },
            rendered_prompt_sample=first_prompt(scorable_benches),
            suite_id=suite_ref.suite_id,
            suite_hash=suite_ref.suite_hash,
            suite_source=suite_ref.source,
            accepted_suite_terms=config.accept_suite_terms,
            suite_license_manifest=suite_ref.license_manifest,
            provider=provider.name,
            provider_notes=tuple(
                provider.notes(
                    effort=config.reasoning_effort,
                    decodings=tuple(sampling_by_bench.values()),
                ),
            ),
            reasoning_effort=config.reasoning_effort,
            thinking_budget=thinking_budget,
            reasoning_registry_entry_id=reasoning_registry_entry_id,
            model_file=config.model_file,
            model_family=config.model_family,
            quant_label=config.quant_label,
            model_format=config.model_format,
            tokenizer_file=config.tokenizer_file,
            chat_template_file=config.chat_template_file,
            tokenizer_digest=config.tokenizer_digest,
            tokenizer_digest_source=config.tokenizer_digest_source,
            chat_template_digest=config.chat_template_digest,
            chat_template_digest_source=config.chat_template_digest_source,
            runtime_name=config.runtime_name,
            runtime_version=config.runtime_version,
            kv_cache_quant=config.kv_cache_quant,
            ctx_len_configured=config.ctx_len_configured,
            parallel_slots=config.parallel_slots,
            build_flags=config.build_flags,
            runtime_backend=config.runtime_backend,
            cuda_version=config.cuda_version,
            runner_build_id=config.runner_build_id,
            determinism_policy=config.determinism_policy,
        ),
        transport=transport,
    )
    forcing_active = thinking_budget > 0
    warnings.extend(_audit_forced_cap_hits(items, forcing_active))
    run_record: LocalbenchRun = {
        "schema": "localbench-run-v0",
        "schema_version": RUN_SCHEMA_VERSION,
        "submission_ticket_id": None,
        "server_nonce": None,
        "issued_at": None,
        "run_started_at": started_at,
        "run_finished_at": finished_at,
        "source": "localbench-cli",
        "tier": config.tier,
        "account": None,
        "model": _run_record_model(config.model, manifest),
        "manifest": manifest,
        "axis_status": axis_status,
        "headline_complete": headline_complete,
        "benches": benches,
        "composite": composite(benches, axis_status, suite_axis_map),
        "conformance": assess_run_conformance(
            results_by_bench,
            forced=forcing_active,
            leak_regexes_by_bench={
                bench: reasoning_leak_regexes
                for bench in results_by_bench
            },
        ),
        "items": items,
        "totals": totals,
        "warnings": warnings,
    }
    if config.resume is not None:
        run_record["resumed"] = True
        segments = _resume_segments(
            paths,
            current_segment_id=session_segment_id,
            started_at=started_at,
            finished_at=finished_at,
            server_fingerprint=config.server_fingerprint,
            completed_items=segment_completed_item_ids,
        )
        run_record["resume_count"] = max(0, len(segments) - 1)
        run_record["segments"] = segments
    if agentic_provenance is not None:
        run_record["agentic_run"] = agentic_provenance
    if config.price_in is not None or config.price_out is not None:
        run_record["estimated_cost_usd"] = estimated_cost(
            totals,
            config.price_in,
            config.price_out,
        )
    run_record = _assemble_from_checkpoints(run_record, paths, scorable_benches)
    run_record = cast(LocalbenchRun, normalize_result_bundle(run_record, suite_dir=suite_dir))
    write_json(run_record, output_path)
    write_status(
        paths,
        StatusUpdate(
            state="complete",
            current_bench=None,
            current_item_index=None,
            current_item_id=None,
            completed_items=completed_items,
            total_items=total_items,
            started_at=started_at,
            exit_code=0,
        ),
    )
    return run_record


def _campaign_output_path(config: OrchestrateConfig) -> Path:
    if config.out is not None:
        return config.out
    if config.resume is not None:
        return config.resume / "localbench-run.json"
    return default_output_path(config.model, config.tier)


def _bench_item_context(bench: RenderedBench) -> dict[str, BenchItemContext]:
    contexts: dict[str, BenchItemContext] = {}
    for seq, (source_item, benchmark_item) in enumerate(
        zip(bench.source_items, bench.benchmark_items, strict=True),
    ):
        single = RenderedBench(
            name=bench.name,
            source_items=[source_item],
            benchmark_items=[benchmark_item],
            baseline=bench.baseline,
            decoding=bench.decoding,
            item_file=bench.item_file,
        )
        contexts[benchmark_item["id"]] = BenchItemContext(
            bench=single,
            seq=seq,
            item_hash=item_hash(benchmark_item),
            source_item=source_item,
            benchmark_item=benchmark_item,
        )
    return contexts


def _expected_item_checkpoints(
    item_context: dict[str, BenchItemContext],
) -> list[ExpectedItemCheckpoint]:
    return [
        ExpectedItemCheckpoint(
            seq=context.seq,
            item_id=context.benchmark_item["id"],
            item_hash=context.item_hash,
        )
        for context in sorted(item_context.values(), key=lambda item: item.seq)
    ]


def _has_sampler_overrides(config: OrchestrateConfig) -> bool:
    return any(
        value is not None
        for value in (
            config.sampler_temperature,
            config.sampler_top_k,
            config.sampler_top_p,
            config.sampler_min_p,
            config.sampler_seed,
        )
    )


def _apply_sampler_overrides(benches: list[RenderedBench], config: OrchestrateConfig) -> None:
    overrides = _sampler_overrides(config)
    for bench in benches:
        bench.decoding.update(overrides)
        for item in bench.benchmark_items:
            sampling_params = item.get("sampling_params")
            if isinstance(sampling_params, dict):
                sampling_params.update(overrides)


def _sampler_overrides(config: OrchestrateConfig) -> JsonObject:
    overrides: JsonObject = {}
    if config.sampler_temperature is not None:
        overrides["temperature"] = config.sampler_temperature
    if config.sampler_top_k is not None:
        overrides["top_k"] = config.sampler_top_k
    if config.sampler_top_p is not None:
        overrides["top_p"] = config.sampler_top_p
    if config.sampler_min_p is not None:
        overrides["min_p"] = config.sampler_min_p
    if config.sampler_seed is not None:
        overrides["seed"] = config.sampler_seed
    return overrides


def _pending_bench(bench: RenderedBench, checkpointed_ids: set[str]) -> RenderedBench:
    source_items: list[Mapping[str, JsonValue]] = []
    benchmark_items: list[BenchmarkItem] = []
    for source_item, benchmark_item in zip(bench.source_items, bench.benchmark_items, strict=True):
        if benchmark_item["id"] not in checkpointed_ids:
            source_items.append(source_item)
            benchmark_items.append(benchmark_item)
    return RenderedBench(
        name=bench.name,
        source_items=source_items,
        benchmark_items=benchmark_items,
        baseline=bench.baseline,
        decoding=bench.decoding,
        item_file=bench.item_file,
    )


def _score_single_checkpoint(
    context: BenchItemContext,
    result: ItemResult,
    warnings: list[str],
) -> ScoredItem:
    scored = score_bench(context.bench, [result])
    _attach_reasoning_text(scored, [result])
    warnings.extend(_annotate_ruler_truncation(context.bench, [result], scored))
    return scored[0]


def _failure_status(
    paths: CampaignPaths,
    *,
    bench: str,
    completed_items: int,
    total_items: int,
    started_at: str,
    exit_code: int,
    error: BaseException,
    last_completed_item_id: str | None,
) -> StatusUpdate:
    return StatusUpdate(
        state="failed",
        current_bench=bench,
        current_item_index=None,
        current_item_id=None,
        completed_items=completed_items,
        total_items=total_items,
        started_at=started_at,
        exit_code=exit_code,
        failure_reason=f"{error.__class__.__name__}: {error}",
        stderr_tail=_tail_lines(paths.logs_dir / "run.log"),
        serve_log_tail=_tail_lines(paths.logs_dir / "serve.log"),
        monitor_snapshot=_latest_monitor_snapshot(paths.monitor_dir / "monitor.jsonl"),
        resume_hint=f"localbench run --resume {paths.root}",
        last_completed_item_id=last_completed_item_id,
    )


def _write_circuit_breaker_status(
    paths: CampaignPaths,
    *,
    bench: str,
    completed_items: int,
    total_items: int,
    started_at: str,
    last_completed_item_id: str | None,
) -> None:
    write_status(
        paths,
        StatusUpdate(
            state="failed",
            current_bench=bench,
            current_item_index=None,
            current_item_id=None,
            completed_items=completed_items,
            total_items=total_items,
            started_at=started_at,
            exit_code=70,
            failure_reason=_SERVE_HEALTH_CIRCUIT_BREAKER_REASON,
            stderr_tail=_tail_lines(paths.logs_dir / "run.log"),
            serve_log_tail=_tail_lines(paths.logs_dir / "serve.log"),
            monitor_snapshot=_latest_monitor_snapshot(paths.monitor_dir / "monitor.jsonl"),
            resume_hint=f"localbench bench --resume {paths.root} --retry-errored",
            last_completed_item_id=last_completed_item_id,
        ),
    )


def _completed_benches_to_skip(
    checkpoints: dict[str, CompletedBench],
    *,
    retry_errored: bool,
) -> dict[str, CompletedBench]:
    if not retry_errored:
        return checkpoints
    return {
        name: checkpoint
        for name, checkpoint in checkpoints.items()
        if not _completed_bench_has_error(checkpoint)
    }


def _completed_bench_has_error(checkpoint: CompletedBench) -> bool:
    return any(_payload_has_error(item) for item in [*checkpoint.raw_results, *checkpoint.scored_items])


def _checkpoint_has_error(raw_result: ItemResult, scored_item: ScoredItem) -> bool:
    return _payload_has_error(raw_result) or _payload_has_error(scored_item)


def _payload_has_error(payload: Mapping[str, JsonValue]) -> bool:
    return payload.get("error") is not None


def _is_connection_failure(result: ItemResult) -> bool:
    return result.get("error_type") in {"ConnectError", "ConnectTimeout"}


def _resume_segments(
    paths: CampaignPaths,
    *,
    current_segment_id: str,
    started_at: str,
    finished_at: str,
    server_fingerprint: str | None,
    completed_items: list[str],
) -> list[JsonObject]:
    previous = _existing_run_segments(paths.final_run)
    if not previous:
        previous = checkpoint_segment_summaries(paths)
    previous = [segment for segment in previous if segment.get("segment_id") != current_segment_id]
    return [
        *previous,
        {
            "segment_id": current_segment_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "server_fingerprint": server_fingerprint,
            "completed_items": completed_items,
        },
    ]


def _existing_run_segments(path: Path) -> list[JsonObject]:
    if not path.exists():
        return []
    record = read_json_object(path)
    segments = record.get("segments")
    if not isinstance(segments, list):
        return []
    return [
        json.loads(json.dumps(segment, ensure_ascii=False))
        for segment in segments
        if isinstance(segment, dict)
    ]


def _last_completed_item_id(items: list[ScoredItem]) -> str | None:
    if not items:
        return None
    return items[-1]["id"]


def _tail_lines(path: Path, limit: int = 40) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]


def _latest_monitor_snapshot(path: Path) -> JsonObject | None:
    if not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        raw = json.loads(line)
        return raw if isinstance(raw, dict) else None
    return None


def _ordered_streamed_raw(
    bench: RenderedBench,
    raw_results: list[ItemResult],
) -> list[ItemResult]:
    by_id = {item["id"]: item for item in raw_results}
    return [by_id[item["id"]] for item in bench.benchmark_items]


def _ordered_streamed_scored(
    bench: RenderedBench,
    scored_items: list[ScoredItem],
) -> list[ScoredItem]:
    by_id = {item["id"]: item for item in scored_items}
    return [by_id[item["id"]] for item in bench.benchmark_items]


def _validate_resume_campaign(path: Path, config: CampaignConfig) -> None:
    campaign = read_json_object(path)
    model = campaign.get("model")
    suite = campaign.get("suite")
    provider = campaign.get("provider")
    if not isinstance(model, dict) or not isinstance(suite, dict) or not isinstance(provider, dict):
        raise UnsafeResumeError("campaign.json is missing hard-invariant sections")
    mismatches: list[str] = []
    _append_mismatch(mismatches, "model", model.get("declared_model_id"), config.model)
    _append_mismatch(mismatches, "suite_id", suite.get("suite_id"), config.suite_id)
    _append_mismatch(mismatches, "suite_hash", suite.get("suite_hash"), config.suite_hash)
    _append_mismatch(mismatches, "tier", campaign.get("tier"), config.tier)
    _append_mismatch(mismatches, "lane", campaign.get("lane"), config.lane)
    _append_mismatch(mismatches, "provider", provider.get("name"), config.provider)
    serve_fingerprint = campaign.get("serve_fingerprint")
    if isinstance(serve_fingerprint, dict):
        actual_resume_identity = serve_fingerprint.get("resume_identity")
    else:
        actual_resume_identity = None
    if actual_resume_identity is not None and config.resume_identity is not None:
        # Legacy serve_fingerprint records lack resume_identity, so orchestrate skips them.
        # Serve-mode resumes are still fail-closed by serving.precheck_resume_identity.
        _append_optional_mismatch(
            mismatches,
            "resume_identity",
            actual_resume_identity,
            config.resume_identity,
        )
    if mismatches:
        raise UnsafeResumeError("unsafe resume refused: " + ", ".join(mismatches))


def _append_mismatch(
    mismatches: list[str],
    field: str,
    actual: JsonValue | None,
    expected: str,
) -> None:
    if actual != expected:
        mismatches.append(f"{field} changed")


def _append_optional_mismatch(
    mismatches: list[str],
    field: str,
    actual: JsonValue | None,
    expected: str | None,
) -> None:
    if actual != expected:
        mismatches.append(f"{field} changed")


def _checkpoint_raw_results(checkpoint: CompletedBench) -> list[ItemResult]:
    return [_item_result_from_json(row) for row in checkpoint.raw_results]


def _checkpoint_scored_items(checkpoint: CompletedBench) -> list[ScoredItem]:
    return [_scored_item_from_json(row) for row in checkpoint.scored_items]


def _checkpoint_aggregate(checkpoint: CompletedBench) -> BenchAggregate:
    return _aggregate_from_json(checkpoint.aggregate)


def _assemble_from_checkpoints(
    record: LocalbenchRun,
    paths: CampaignPaths,
    scorable_benches: list[RenderedBench],
) -> LocalbenchRun:
    checkpoints = completed_benches(paths)
    disk_items: list[ScoredItem] = []
    disk_benches: dict[str, BenchAggregate] = {}
    for bench in scorable_benches:
        checkpoint = checkpoints.get(bench.name)
        if checkpoint is None:
            continue
        disk_benches[bench.name] = _checkpoint_aggregate(checkpoint)
        disk_items.extend(_ordered_streamed_scored(bench, _checkpoint_scored_items(checkpoint)))
    checkpointed = set(disk_benches)
    passthrough = [item for item in record["items"] if item["bench"] not in checkpointed]
    record["items"] = [*disk_items, *passthrough]
    record["benches"] = disk_benches | {
        bench: aggregate_record
        for bench, aggregate_record in record["benches"].items()
        if bench not in checkpointed
    }
    return record


def _item_result_from_json(row: JsonObject) -> ItemResult:
    usage = _usage_from_json(_object_value(row.get("usage"), "usage"))
    result: ItemResult = {
        "id": _text_value(row.get("id"), "id"),
        "response_text": _nullable_text(row.get("response_text"), "response_text"),
        "reasoning_text": _nullable_text(row.get("reasoning_text"), "reasoning_text"),
        "finish_reason": _nullable_text(row.get("finish_reason"), "finish_reason"),
        "usage": usage,
        "latency_seconds": _number_value(row.get("latency_seconds"), "latency_seconds"),
        "started_at": _text_value(row.get("started_at"), "started_at"),
        "finished_at": _text_value(row.get("finished_at"), "finished_at"),
        "attempts": _int_value(row.get("attempts"), "attempts"),
        "error": _nullable_text(row.get("error"), "error"),
    }
    thinking_forced = row.get("thinking_forced")
    if isinstance(thinking_forced, bool):
        result["thinking_forced"] = thinking_forced
    return result


def _scored_item_from_json(row: JsonObject) -> ScoredItem:
    item: ScoredItem = {
        "id": _text_value(row.get("id"), "id"),
        "bench": _text_value(row.get("bench"), "bench"),
        "response_text": _nullable_text(row.get("response_text"), "response_text"),
        "extracted": _nullable_text(row.get("extracted"), "extracted"),
        "correct": _bool_value(row.get("correct"), "correct"),
        "finish_reason": _nullable_text(row.get("finish_reason"), "finish_reason"),
        "latency_seconds": _number_value(row.get("latency_seconds"), "latency_seconds"),
        "started_at": _text_value(row.get("started_at"), "started_at"),
        "finished_at": _text_value(row.get("finished_at"), "finished_at"),
        "attempts": _int_value(row.get("attempts"), "attempts"),
        "usage": _usage_from_json(_object_value(row.get("usage"), "usage")),
        "error": _nullable_text(row.get("error"), "error"),
    }
    reasoning_text = row.get("reasoning_text")
    if reasoning_text is None or isinstance(reasoning_text, str):
        item["reasoning_text"] = reasoning_text
    warnings = row.get("warnings")
    if isinstance(warnings, list):
        item["warnings"] = [warning for warning in warnings if isinstance(warning, str)]
    return item


def _aggregate_from_json(row: JsonObject) -> BenchAggregate:
    return {
        "n": _int_value(row.get("n"), "n"),
        "n_errors": _int_value(row.get("n_errors"), "n_errors"),
        "n_extraction_failures": _int_value(row.get("n_extraction_failures"), "n_extraction_failures"),
        "raw_accuracy": _number_value(row.get("raw_accuracy"), "raw_accuracy"),
        "chance_corrected": _number_value(row.get("chance_corrected"), "chance_corrected"),
        "termination_rate": _number_value(row.get("termination_rate"), "termination_rate"),
        "conditional_accuracy": _number_value(row.get("conditional_accuracy"), "conditional_accuracy"),
    }


def _usage_from_json(row: JsonObject) -> Usage:
    usage: Usage = {
        "prompt_tokens": _nullable_int(row.get("prompt_tokens"), "prompt_tokens"),
        "completion_tokens": _nullable_int(row.get("completion_tokens"), "completion_tokens"),
        "total_tokens": _nullable_int(row.get("total_tokens"), "total_tokens"),
    }
    reasoning_tokens = row.get("reasoning_tokens")
    if isinstance(reasoning_tokens, int) and not isinstance(reasoning_tokens, bool):
        usage["reasoning_tokens"] = reasoning_tokens
    return usage


def _object_value(value: JsonValue | None, field: str) -> JsonObject:
    if isinstance(value, dict):
        return value
    raise UnsafeResumeError(f"checkpoint field {field} is not an object")


def _text_value(value: JsonValue | None, field: str) -> str:
    if isinstance(value, str):
        return value
    raise UnsafeResumeError(f"checkpoint field {field} is not text")


def _nullable_text(value: JsonValue | None, field: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise UnsafeResumeError(f"checkpoint field {field} is not nullable text")


def _bool_value(value: JsonValue | None, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise UnsafeResumeError(f"checkpoint field {field} is not boolean")


def _int_value(value: JsonValue | None, field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise UnsafeResumeError(f"checkpoint field {field} is not an integer")


def _nullable_int(value: JsonValue | None, field: str) -> int | None:
    if value is None:
        return None
    return _int_value(value, field)


def _number_value(value: JsonValue | None, field: str) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    raise UnsafeResumeError(f"checkpoint field {field} is not a number")


def discover_suite_dir() -> Path:
    """Return the resolved default suite directory without source-tree fallback."""
    return resolve_suite_dir(suite_id=DEFAULT_SUITE_ID).path


def _run_agentic_axis(
    config: OrchestrateConfig,
    warnings: list[str],
    *,
    sandbox_factory: SandboxFactory | None = None,
    model_factory: ModelFactory | None = None,
    task_ids: list[str] | None = None,
    results_dir: Path | None = None,
    provenance_extra: JsonObject | None = None,
) -> AgenticOutcome | None:
    injected = sandbox_factory is not None or model_factory is not None or task_ids is not None
    resolved_sandbox_factory = sandbox_factory
    resolved_model_factory = model_factory
    if injected:
        if resolved_sandbox_factory is None or resolved_model_factory is None:
            warnings.append(
                "appworld sandbox unavailable: incomplete injected agentic factories",
            )
            return None
    else:
        unavailable_detail = _agentic_preflight_unavailable_detail()
        if unavailable_detail is not None:
            warnings.append(unavailable_detail)
            return None
        from localbench.scoring.agentic_exec.benchmark import (  # noqa: PLC0415
            appworld_sandbox_factory,
        )
        from localbench.scoring.agentic_exec.funnel import chat_client_factory  # noqa: PLC0415

        chat_template_kwargs: JsonObject = {"enable_thinking": True}
        resolved_sandbox_factory = appworld_sandbox_factory()
        resolved_model_factory = chat_client_factory(
            config.endpoint,
            config.model,
            api_key=config.api_key or "",
            chat_template_kwargs=chat_template_kwargs,
        )
    if injected:
        chat_template_kwargs = {}

    from localbench.scoring.agentic_exec import task_pool  # noqa: PLC0415
    from localbench.scoring.agentic_exec.funnel import Stage, run_with_reruns  # noqa: PLC0415
    from localbench.scoring.agentic_exec.loop_config import LoopConfig  # noqa: PLC0415

    if resolved_sandbox_factory is None or resolved_model_factory is None:
        warnings.append(
            "appworld sandbox unavailable: incomplete injected agentic factories",
        )
        return None

    if injected:
        if task_ids is None:
            warnings.append(
                "appworld sandbox unavailable: agentic task subset not configured for inline run",
            )
            return None
        injected_task_ids = list(task_ids)
        if config.tier == "quick" and config.max_items is not None:
            injected_task_ids = injected_task_ids[: config.max_items]
        subset = task_pool.subset_from_task_ids(injected_task_ids)
        provenance_stage = "injected"
    else:
        subset = task_pool.build_subset(Stage.SCORED, wide_smoke=False, with_metadata=True)
        provenance_stage = "scored"

    agg = run_with_reruns(
        label=config.model,
        stage=Stage.SCORED,
        subset=subset,
        model_factory=resolved_model_factory,
        sandbox_factory=resolved_sandbox_factory,
        config=LoopConfig(max_output_tokens_per_turn=_AGENTIC_SCORED_MAX_OUTPUT_TOKENS_PER_TURN),
        base_count=2,
        results_dir=results_dir,
        endpoint=config.endpoint,
        model_id=config.model,
        chat_template_kwargs=chat_template_kwargs,
    )
    last_report = agg.runs[-1].report
    provenance: JsonObject = {
        "campaign": True,
        "single_pass": False,
        "asr_series": list(agg.asr_series),
        "mean_asr": agg.mean_asr,
        "max_abs_delta_pp": agg.max_abs_delta_pp,
        "triggered_third_run": agg.triggered_third_run,
        "subset_size": subset.size,
        "subset_hash": subset.manifest_hash,
        "stage": provenance_stage,
        "diagnostics": _appworld_report_summary(last_report),
        "runs": [_appworld_stage_run_summary(run) for run in agg.runs],
    }
    attestations = _appworld_report_attestations(last_report)
    if attestations:
        provenance["attestations"] = attestations
    if provenance_extra is not None:
        provenance.update(provenance_extra)
    return AgenticOutcome(
        aggregate=_appworld_campaign_aggregate(agg, subset.size),
        items=_appworld_report_to_items(last_report),
        provenance=provenance,
    )


def _agentic_preflight_unavailable_detail() -> str | None:
    failures: list[str] = []
    if importlib.util.find_spec("appworld") is None:
        failures.append("appworld package not importable")
    if not os.environ.get("APPWORLD_ROOT"):
        failures.append("APPWORLD_ROOT is not set")
    from localbench.scoring.agentic_exec.sandbox import resolve_bwrap  # noqa: PLC0415

    if resolve_bwrap() is None:
        failures.append("bubblewrap (bwrap) not found")
    if not failures:
        return None
    return "appworld sandbox unavailable: " + "; ".join(failures)


def _appworld_report_to_aggregate(report: BenchmarkReport) -> BenchAggregate:
    successes = [result.success for result in report.results]
    asr = sum(1 for success in successes if success) / len(successes) if successes else 0.0
    return {
        "n": len(successes),
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": asr,
        "chance_corrected": asr,
        "conditional_accuracy": asr,
        "termination_rate": 1.0,
    }


def _agentic_results_dir(output_path: Path) -> Path:
    return output_path.parent / "agentic" / output_path.stem


def _appworld_campaign_aggregate(agg: RerunAggregate, n: int) -> BenchAggregate:
    mean_asr = agg.mean_asr
    return {
        "n": n,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": mean_asr,
        "chance_corrected": mean_asr,
        "conditional_accuracy": mean_asr,
        "termination_rate": 1.0,
    }


def _appworld_report_summary(report: BenchmarkReport) -> JsonObject:
    return {
        "tasks_total": report.tasks_total,
        "tasks_succeeded": report.tasks_succeeded,
        "agentic_success_rate": report.agentic_success_rate,
        "asr_excluding_infra": report.asr_excluding_infra,
        "collateral_damage_rate": report.collateral_damage_rate,
        "cap_exceeded_rate": report.cap_exceeded_rate,
        "no_final_answer_rate": report.no_final_answer_rate,
        "harness_error_rate": report.harness_error_rate,
        "infra_timeout_rate": report.infra_timeout_rate,
        "infra_sandbox_rate": report.infra_sandbox_rate,
        "model_failure_rate": report.model_failure_rate,
        "model_no_progress_rate": report.model_no_progress_rate,
        "harness_error_subclass_rate": report.harness_error_subclass_rate,
        "format_failure_rate": report.format_failure_rate,
        "syntax_error_rate": report.syntax_error_rate,
        "runtime_error_rate": report.runtime_error_rate,
        "observation_truncation_rate": report.observation_truncation_rate,
        "api_docs_usage_rate": report.api_docs_usage_rate,
        "mean_turns_used": report.mean_turns_used,
        "mean_blocks_run": report.mean_blocks_run,
        "mean_api_calls": report.mean_api_calls,
        "mean_output_tokens": report.mean_output_tokens,
        "outcome_counts": dict(report.outcome_counts),
    }


def _appworld_stage_run_summary(run: StageRunResult) -> JsonObject:
    summary = _appworld_report_summary(run.report)
    summary["run_index"] = run.run_index
    summary["stage"] = run.stage
    summary["subset_hash"] = run.subset_hash
    summary["results_path"] = run.results_path
    return summary


def _appworld_report_attestations(report: BenchmarkReport) -> list[JsonObject]:
    return [dict(result.attestation) for result in report.results if result.attestation is not None]


def _appworld_report_to_items(report: BenchmarkReport) -> list[ScoredItem]:
    timestamp = utc_now()
    return [
        {
            "id": result.task_id,
            "bench": _APPWORLD_C_BENCH,
            "response_text": None,
            "extracted": None,
            "correct": result.success,
            "finish_reason": None,
            "latency_seconds": 0.0,
            "started_at": timestamp,
            "finished_at": timestamp,
            "attempts": 1,
            "usage": empty_usage(),
            "error": None,
        }
        for result in report.results
    ]


def _agentic_warning_since(warnings: list[str], start: int) -> str:
    for warning in warnings[start:]:
        if warning.startswith("appworld sandbox unavailable:"):
            return warning
    return "appworld sandbox unavailable: unknown agentic preflight failure"


def _headline_complete(axis_status: AxisStatusBlock) -> bool:
    return all(
        axis_status["axes"].get(axis, {}).get("status") == "measured"
        for axis in _HEADLINE_AXIS_KEYS
    )


def default_output_path(model: str, tier: str) -> Path:
    """Build the default timestamped run output path."""
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("_") or "model"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("runs") / f"{safe_model}_{tier}_{timestamp}.json"


def _run_record_model(model_name: str, manifest: JsonObject) -> JsonObject:
    manifest_model = manifest.get("model")
    manifest_model = manifest_model if isinstance(manifest_model, dict) else {}
    return {
        "name": model_name,
        "file_sha256": _nullable_digest(manifest_model.get("file_sha256")),
        "tokenizer_digest": _nullable_digest(manifest_model.get("tokenizer_digest")),
        "chat_template_digest": _nullable_digest(manifest_model.get("chat_template_digest")),
    }


def _nullable_digest(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value not in {"", "UNHASHED", "unknown", "endpoint-applied-unknown"}:
        return value
    return None


def _attach_reasoning_text(scored_items: list[ScoredItem], results: list[ItemResult]) -> None:
    for scored_item, result in zip(scored_items, results, strict=True):
        scored_item["reasoning_text"] = result["reasoning_text"]


def _plumb_think_budget(rendered_benches: list[RenderedBench], suite: JsonObject) -> int:
    """Stamp each item's think_budget for local capped-thinking; return the budget used."""
    benches_cfg = suite.get("benches")
    benches_cfg = benches_cfg if isinstance(benches_cfg, dict) else {}
    budget_used = 0
    for bench in rendered_benches:
        think_budget = _bench_think_budget(benches_cfg.get(bench.name))
        for benchmark_item in bench.benchmark_items:
            benchmark_item["think_budget"] = think_budget
        budget_used = max(budget_used, think_budget)
    return budget_used


def _forced_prompt_renderer(config: OrchestrateConfig, provider_name: str) -> PromptRenderer | None:
    if provider_name != "local" or config.lane != "capped-thinking":
        return None
    return build_forced_prompt_renderer(config.hf_model_id, config.reasoning_activation)


def _capped_thinking_reasoning_entry(
    config: OrchestrateConfig,
) -> ReasoningRegistryEntry | None:
    reasoning_entry = reasoning_entry_for_activation(config.reasoning_activation)
    if not config.publishable:
        return reasoning_entry
    if reasoning_entry is None:
        raise PublishableCappedThinkingError(
            "publishable capped-thinking has no ranked reasoning-registry entry "
            f"for activation {config.reasoning_activation!r}",
        )
    _require_reasoning_family_match(config, reasoning_entry)
    if config.hf_model_id is None:
        raise PublishableCappedThinkingError(
            "publishable capped-thinking requires --hf-model-id; "
            "the ChatML fallback renderer is only valid for diagnostic runs",
        )
    return reasoning_entry


def _require_reasoning_family_match(
    config: OrchestrateConfig,
    reasoning_entry: ReasoningRegistryEntry,
) -> None:
    model_family = config.model_family
    if model_family is None or model_family == "":
        return
    if _reasoning_family_matches(model_family, reasoning_entry.model_match):
        return
    patterns = ", ".join(reasoning_entry.model_match)
    raise PublishableCappedThinkingError(
        f"publishable capped-thinking model family {model_family!r} does not match "
        f"activation {config.reasoning_activation!r} reasoning-registry entry "
        f"{reasoning_entry.id!r} patterns: {patterns}",
    )


def _reasoning_family_matches(model_family: str, patterns: tuple[str, ...]) -> bool:
    family = model_family.casefold()
    for pattern in patterns:
        candidate = pattern.casefold()
        if _has_glob_syntax(candidate):
            if fnmatch.fnmatchcase(family, candidate):
                return True
        elif family == candidate:
            return True
    return False


def _has_glob_syntax(pattern: str) -> bool:
    return any(char in pattern for char in "*?[]")


def _audit_forced_cap_hits(items: list[ScoredItem], forcing_active: bool) -> list[str]:
    """Defensive invariant check: strict completion gating should make this empty.

    A cap-hit item is non-terminating and cannot score correct. If one appears here,
    the production scorer failed to apply the strict completion gate uniformly.
    """
    if not forcing_active:
        return []
    flagged = [
        item["id"]
        for item in items
        if item.get("finish_reason") == "length" and item.get("correct")
    ]
    if not flagged:
        return []
    sample = ", ".join(flagged[:3])
    return [
        f"SCORER-GATE BUG: {len(flagged)} answer-cap-hit item(s) scored CORRECT "
        f"(e.g. {sample}); strict completion gating failed",
    ]


def _bench_think_budget(bench_cfg: JsonValue) -> int:
    """Read a per-bench capped-thinking budget from suite lane_caps, else the locked default."""
    if isinstance(bench_cfg, dict):
        lane_caps = bench_cfg.get("lane_caps")
        if isinstance(lane_caps, dict):
            capped = lane_caps.get("capped-thinking")
            if isinstance(capped, dict):
                value = capped.get("think_budget")
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    return value
    return CAPPED_THINKING_THINK_BUDGET


def _exclude_exec_lane(
    rendered_benches: list[RenderedBench],
    suite: JsonObject,
    warnings: list[str],
) -> list[RenderedBench]:
    """Drop exec-lane benches from the standard run path; they need `localbench code`."""
    benches = suite.get("benches")
    benches = benches if isinstance(benches, dict) else {}
    kept: list[RenderedBench] = []
    for bench in rendered_benches:
        bench_config = benches.get(bench.name)
        lane = bench_config.get("lane") if isinstance(bench_config, dict) else None
        if lane == "exec":
            warnings.append(
                f"Skipping {bench.name}: exec-lane bench is run with `localbench code`, "
                "not `localbench run`",
            )
            continue
        kept.append(bench)
    return kept


def _annotate_ruler_truncation(
    bench: RenderedBench,
    results: list[ItemResult],
    scored_items: list[ScoredItem],
) -> list[str]:
    if bench.name != "ruler_32k":
        return []
    warnings: list[str] = []
    for benchmark_item, result, scored_item in zip(
        bench.benchmark_items,
        results,
        scored_items,
        strict=True,
    ):
        warning = _ruler_truncation_warning(benchmark_item, result)
        if warning is None:
            continue
        scored_item.setdefault("warnings", []).append(warning)
        warnings.append(warning)
    return warnings


def _ruler_truncation_warning(
    benchmark_item: BenchmarkItem,
    result: ItemResult,
) -> str | None:
    expected = estimate_prompt_tokens(
        "\n\n".join(message["content"] for message in benchmark_item["messages"]),
    )
    reported = result["usage"]["prompt_tokens"]
    item_id = benchmark_item["id"]
    if reported is None:
        return (
            f"ruler_32k item {item_id}: usage.prompt_tokens missing; "
            "full-context serving could not be verified"
        )
    threshold = int(expected * _RULER_TRUNCATION_RATIO)
    if reported < threshold and expected - reported >= _RULER_TRUNCATION_MIN_GAP:
        return (
            f"ruler_32k item {item_id}: serving-truncation suspected; "
            f"reported prompt_tokens={reported}, rendered_prompt_estimate={expected}, "
            f"threshold={threshold}"
        )
    return None
