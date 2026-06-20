"""Benchmark suite orchestration for localbench."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, NotRequired, TypedDict

import httpx

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
from localbench.runner import run_benchmark, write_json
from localbench.scorers.ruler import estimate_prompt_tokens

BenchChoice = Literal[
    "all",
    "mmlu_pro",
    "ifeval",
    "genmath",
    "supergpqa",
    "ifbench",
    "bfcl",
    "lcb",
    "amo",
    "olymmath_hard",
    "ruler_32k",
]
TierChoice = Literal["quick", "standard"]
LaneChoice = Literal["answer-only", "capped-thinking", "api-uncapped"]
ReasoningEffortChoice = ReasoningEffort
ReasoningActivationChoice = ReasoningActivation

_RULER_TRUNCATION_RATIO: Final = 0.80
_RULER_TRUNCATION_MIN_GAP: Final = 2_048


class LocalbenchRun(TypedDict):
    schema: str
    manifest: JsonObject
    benches: dict[str, BenchAggregate]
    composite: float
    conformance: JsonObject
    items: list[ScoredItem]
    totals: RunTotals
    warnings: list[str]
    output_path: str
    estimated_cost_usd: NotRequired[float]


@dataclass(frozen=True, slots=True)
class OrchestrateConfig:
    endpoint: str
    model: str
    bench: BenchChoice = "all"
    tier: TierChoice = "quick"
    concurrency: int = 4
    out: Path | None = None
    api_key: str | None = None
    max_items: int | None = None
    suite_dir: Path | None = None
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
) -> LocalbenchRun:
    """Run selected suite benches, score responses, write JSON, and return the record."""
    suite_dir = config.suite_dir or discover_suite_dir()
    suite = read_json_object(suite_dir / "suite.json")
    started_at = utc_now()
    started_perf = time.perf_counter()
    warnings: list[str] = []
    provider = provider_for_name(config.provider)
    rendered_benches = render_benches(
        config.bench,
        config.tier,
        config.max_items,
        suite_dir,
        suite,
        warnings,
    )
    rendered_benches = _exclude_exec_lane(rendered_benches, suite, warnings)
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

    thinking_budget = 0
    prompt_renderer: PromptRenderer | None = None
    if config.provider == "local" and config.lane == "capped-thinking":
        # Local capped-thinking enforces the locked thinking budget with two-pass forcing
        # (budget_forcing.run_forced_item). Stamp each item with the budget the runner reads.
        thinking_budget = _plumb_think_budget(rendered_benches, suite)
        if thinking_budget > 0:
            prompt_renderer = _forced_prompt_renderer(config, provider.name)

    results_by_bench: dict[str, list[ItemResult]] = {}
    for bench in rendered_benches:
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
        )
        scored_items = score_bench(bench, record["results"])
        warnings.extend(_annotate_ruler_truncation(bench, record["results"], scored_items))
        items.extend(scored_items)
        results_by_bench[bench.name] = record["results"]

    wall_time = time.perf_counter() - started_perf
    finished_at = utc_now()
    totals = run_totals(items, wall_time)
    benches = {
        bench.name: aggregate(
            bench.name,
            [item for item in items if item["bench"] == bench.name],
            bench.baseline,
        )
        for bench in rendered_benches
    }
    output_path = config.out or default_output_path(config.model, config.tier)
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
            rendered_prompt_sample=first_prompt(rendered_benches),
            provider=provider.name,
            provider_notes=tuple(
                provider.notes(
                    effort=config.reasoning_effort,
                    decodings=tuple(sampling_by_bench.values()),
                ),
            ),
            reasoning_effort=config.reasoning_effort,
            thinking_budget=thinking_budget,
        ),
        transport=transport,
    )
    forcing_active = thinking_budget > 0
    warnings.extend(_audit_forced_cap_hits(items, forcing_active))
    run_record: LocalbenchRun = {
        "schema": "localbench-run-v0",
        "manifest": manifest,
        "benches": benches,
        "composite": composite(benches),
        "conformance": assess_run_conformance(results_by_bench, forced=forcing_active),
        "items": items,
        "totals": totals,
        "warnings": warnings,
        "output_path": str(output_path),
    }
    if config.price_in is not None or config.price_out is not None:
        run_record["estimated_cost_usd"] = estimated_cost(
            totals,
            config.price_in,
            config.price_out,
        )
    write_json(run_record, output_path)
    return run_record


def discover_suite_dir() -> Path:
    """Return the repo-local suite/v0 directory for source-tree execution."""
    return Path(__file__).resolve().parents[3] / "suite" / "v0"


def default_output_path(model: str, tier: str) -> Path:
    """Build the default timestamped run output path."""
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("_") or "model"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("runs") / f"{safe_model}_{tier}_{timestamp}.json"


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
