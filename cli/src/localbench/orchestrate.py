"""Benchmark suite orchestration for localbench."""

from __future__ import annotations

import importlib.util
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NotRequired, TypeAlias, TypedDict

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
from localbench._types import BenchmarkItem, ItemResult, JsonObject, JsonValue
from localbench.budget_forcing import CAPPED_THINKING_THINK_BUDGET
from localbench.lane_conformance import assess_run_conformance
from localbench.manifest import ManifestContext, collect_manifest
from localbench.prompt_rendering import (
    PromptRenderer,
    ReasoningActivation,
    build_forced_prompt_renderer,
)
from localbench.providers import ReasoningEffort, provider_for_name
from localbench.reasoning_registry import reasoning_entry_for_activation
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

_RULER_TRUNCATION_RATIO: Final = 0.80
_RULER_TRUNCATION_MIN_GAP: Final = 2_048
_APPWORLD_C_BENCH: Final = "appworld_c"
# Frozen per-turn output-token cap for the inline SCORED agentic campaign. Every official
# AppWorld-C .scored run (qwen36-27b all quants, qwopus, qwable-coder, gemma4-31b) uses 3072.
# The LoopConfig default (1024) truncates verbose native-thinking models mid-reasoning ->
# finish_reason="length" -> cap_exceeded -> harness-dominated ~0 ASR. The inline campaign must
# override it to match the board's frozen cap, else its mean ASR is not comparable.
_AGENTIC_SCORED_MAX_OUTPUT_TOKENS_PER_TURN: Final = 3072
_HEADLINE_AXIS_KEYS: Final = tuple(axis.key for axis in AXES if axis.role == "headline")


class LocalbenchRun(TypedDict):
    schema: str
    schema_version: str
    submission_ticket_id: str | None
    server_nonce: str | None
    issued_at: str | None
    run_started_at: str
    run_finished_at: str
    source: str
    tier: str
    account: str | None
    model: JsonObject
    manifest: JsonObject
    axis_status: AxisStatusBlock
    headline_complete: bool
    benches: dict[str, BenchAggregate]
    composite: float
    conformance: JsonObject
    items: list[ScoredItem]
    totals: RunTotals
    warnings: list[str]
    output_path: str
    agentic_run: NotRequired[JsonObject]
    estimated_cost_usd: NotRequired[float]


@dataclass(frozen=True, slots=True)
class AgenticOutcome:
    aggregate: BenchAggregate
    items: list[ScoredItem]
    provenance: JsonObject


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


async def run_localbench(
    config: OrchestrateConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    agentic_sandbox_factory: SandboxFactory | None = None,
    agentic_model_factory: ModelFactory | None = None,
    agentic_task_ids: list[str] | None = None,
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

    thinking_budget = 0
    prompt_renderer: PromptRenderer | None = None
    reasoning_registry_entry_id: str | None = None
    forcing_format = None
    if config.provider == "local" and config.lane == "capped-thinking":
        # Local capped-thinking enforces the locked thinking budget with two-pass forcing
        # (budget_forcing.run_forced_item). Stamp each item with the budget the runner reads.
        thinking_budget = _plumb_think_budget(scorable_benches, suite)
        if thinking_budget > 0:
            reasoning_entry = reasoning_entry_for_activation(config.reasoning_activation)
            if reasoning_entry is not None:
                reasoning_registry_entry_id = reasoning_entry.id
                forcing_format = reasoning_entry.forcing
            prompt_renderer = _forced_prompt_renderer(config, provider.name)

    results_by_bench: dict[str, list[ItemResult]] = {}
    for bench in scorable_benches:
        sampling_by_bench[bench.name] = bench.decoding
        item_files.append(bench.item_file)
        record = await run_benchmark(
            base_url=config.endpoint,
            model=config.model,
            items=bench.benchmark_items,
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
        )
        scored_items = score_bench(bench, record["results"])
        _attach_reasoning_text(scored_items, record["results"])
        warnings.extend(_annotate_ruler_truncation(bench, record["results"], scored_items))
        items.extend(scored_items)
        results_by_bench[bench.name] = record["results"]

    benches = {
        bench.name: aggregate(
            bench.name,
            [item for item in items if item["bench"] == bench.name],
            bench.baseline,
        )
        for bench in scorable_benches
    }
    output_path = config.out or default_output_path(config.model, config.tier)
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
        "conformance": assess_run_conformance(results_by_bench, forced=forcing_active),
        "items": items,
        "totals": totals,
        "warnings": warnings,
        "output_path": str(output_path),
    }
    if agentic_provenance is not None:
        run_record["agentic_run"] = agentic_provenance
    if config.price_in is not None or config.price_out is not None:
        run_record["estimated_cost_usd"] = estimated_cost(
            totals,
            config.price_in,
            config.price_out,
        )
    write_json(run_record, output_path)
    return run_record


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
    return AgenticOutcome(
        aggregate=_appworld_campaign_aggregate(agg, subset.size),
        items=_appworld_report_to_items(last_report),
        provenance={
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
        },
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
