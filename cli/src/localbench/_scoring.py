"""Response scoring and aggregate math for orchestrated runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from localbench._suite import RenderedBench
from localbench._types import ItemResult, JsonValue, Usage
from localbench.scorers.ifeval import score_ifeval
from localbench.scorers.math_numeric import extract_final_number, score_math
from localbench.scorers.mcq import score_mcq_detailed


class ScoredItem(TypedDict):
    id: str
    bench: str
    response_text: str | None
    extracted: str | None
    correct: bool
    latency_seconds: float
    usage: Usage
    error: str | None


class BenchAggregate(TypedDict):
    n: int
    n_errors: int
    n_extraction_failures: int
    raw_accuracy: float
    chance_corrected: float


class RunTotals(TypedDict):
    n_items: int
    n_errors: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    wall_time_seconds: float
    completion_tokens_per_second: float


def score_bench(bench: RenderedBench, results: list[ItemResult]) -> list[ScoredItem]:
    """Score runner results for one rendered bench."""
    scored: list[ScoredItem] = []
    for source_item, result in zip(bench.source_items, results, strict=True):
        response_text = result["response_text"]
        error = result["error"]
        extracted, correct = _score_response(bench.name, source_item, response_text, error)
        scored.append(
            {
                "id": result["id"],
                "bench": bench.name,
                "response_text": response_text,
                "extracted": extracted,
                "correct": correct,
                "latency_seconds": result["latency_seconds"],
                "usage": result["usage"],
                "error": error,
            },
        )
    return scored


def aggregate(bench: str, items: list[ScoredItem], baseline: float) -> BenchAggregate:
    """Aggregate item-level correctness into benchmark metrics."""
    n = len(items)
    raw_accuracy = sum(1 for item in items if item["correct"]) / n if n else 0.0
    denominator = 1.0 - baseline
    corrected = (raw_accuracy - baseline) / denominator if denominator > 0 else 0.0
    return {
        "n": n,
        "n_errors": sum(1 for item in items if item["error"] is not None),
        "n_extraction_failures": sum(
            1
            for item in items
            if _bench_has_extraction(bench)
            and item["error"] is None
            and item["extracted"] is None
        ),
        "raw_accuracy": raw_accuracy,
        "chance_corrected": max(0.0, corrected),
    }


def run_totals(items: list[ScoredItem], wall_time: float) -> RunTotals:
    """Sum token usage and wall-clock metrics across all scored items."""
    completion_tokens = _sum_usage(items, "completion_tokens")
    return {
        "n_items": len(items),
        "n_errors": sum(1 for item in items if item["error"] is not None),
        "prompt_tokens": _sum_usage(items, "prompt_tokens"),
        "completion_tokens": completion_tokens,
        "total_tokens": _sum_usage(items, "total_tokens"),
        "wall_time_seconds": wall_time,
        "completion_tokens_per_second": completion_tokens / wall_time if wall_time > 0 else 0.0,
    }


def composite(benches: Mapping[str, BenchAggregate]) -> float:
    """Return equal-weight mean chance-corrected score for benches that ran."""
    if not benches:
        return 0.0
    return sum(bench["chance_corrected"] for bench in benches.values()) / len(benches)


def estimated_cost(totals: RunTotals, price_in: float | None, price_out: float | None) -> float:
    """Estimate run cost from per-million-token prices."""
    return (
        totals["prompt_tokens"] * (price_in or 0.0)
        + totals["completion_tokens"] * (price_out or 0.0)
    ) / 1_000_000


def _score_response(
    bench: str,
    source_item: Mapping[str, JsonValue],
    response_text: str | None,
    error: str | None,
) -> tuple[str | None, bool]:
    if error is not None or response_text is None:
        return None, False
    match bench:
        case "mmlu_pro":
            detailed = score_mcq_detailed(
                response_text,
                _string(source_item.get("answer")) or "",
                len(_list(source_item.get("options"))),
            )
            return detailed["extracted"], detailed["correct"]
        case "ifeval":
            return None, bool(score_ifeval(source_item, response_text)["strict"])
        case "genmath":
            extracted = extract_final_number(response_text)
            return extracted, score_math(response_text, _string(source_item.get("answer")) or "")
        case _:
            return None, False


def _list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _bench_has_extraction(bench: str) -> bool:
    return bench in {"mmlu_pro", "genmath"}


def _sum_usage(items: list[ScoredItem], key: str) -> int:
    return sum(
        value
        for item in items
        if isinstance((value := item["usage"][key]), int)
    )
