"""Benchmark suite orchestration for localbench."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

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
    first_prompt,
    item_hashes,
    read_json_object,
    render_benches,
    suite_version,
)
from localbench._types import JsonObject
from localbench.manifest import ManifestContext, collect_manifest
from localbench.providers import provider_for_name
from localbench.runner import run_benchmark, write_json

BenchChoice = Literal["all", "mmlu_pro", "ifeval", "genmath"]
TierChoice = Literal["quick", "standard"]
LaneChoice = Literal["answer-only", "capped-thinking", "api-uncapped"]


class LocalbenchRun(TypedDict):
    schema: str
    manifest: JsonObject
    benches: dict[str, BenchAggregate]
    composite: float
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
        )
        items.extend(score_bench(bench, record["results"]))

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
            provider_notes=tuple(provider.notes()),
        ),
        transport=transport,
    )
    run_record: LocalbenchRun = {
        "schema": "localbench-run-v0",
        "manifest": manifest,
        "benches": benches,
        "composite": composite(benches),
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
