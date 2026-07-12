"""Response scoring and aggregate math for orchestrated runs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final, NotRequired, TypedDict

from localbench._response import empty_usage
from localbench._suite import RenderedBench
from localbench._types import BenchmarkItem, ItemResult, JsonObject, JsonValue, Usage
from localbench.coding_exec.artifacts import code_artifact_for_generation
from localbench.scorers.bfcl import score_bfcl
from localbench.scorers.bfcl_multi_turn import BFCL_MULTI_TURN_BENCHES, score_bfcl_multi_turn
from localbench.scorers.bfcl_multi_turn._backend import (
    BackendLoadError,
    backend_readiness_error,
)
from localbench.scorers.ifbench import score_ifbench
from localbench.scorers.ifeval import score_ifeval
from localbench.scorers.lcb import score_lcb
from localbench.scorers.math_numeric import extract_final_number, score_math
from localbench.scorers.math_symbolic import extract_math_answer, verify_math
from localbench.scorers.mcq import score_mcq_detailed
from localbench.scorers._reasoning import strip_reasoning
from localbench.scorers.ruler import score_ruler
from localbench.scorers.tc_json_v1 import score_tc_json_v1
from localbench.scoring.axis_status import AxisStatusBlock, bench_is_measured
from localbench.scoring.axes import AXES, materialize_facet_samples
from localbench.scoring.metadata import DOMAIN_WEIGHTS, domain_for_bench
from localbench.scoring.signed_score import signed_score

_RESPONSE_OPEN: Final = "<response>"
_RESPONSE_CLOSE: Final = "</response>"


class ScoredItem(TypedDict):
    id: str
    bench: str
    response_text: str | None
    extracted: str | None
    correct: bool
    finish_reason: str | None
    latency_seconds: float
    started_at: str
    finished_at: str
    attempts: int
    usage: Usage
    error: str | None
    warnings: NotRequired[list[str]]
    failure_kind: NotRequired[str | None]
    reasoning_text: NotRequired[str | None]
    max_tokens: NotRequired[int]
    generated_tokens: NotRequired[JsonValue]
    server_timings: NotRequired[JsonObject | None]
    code_artifact: NotRequired[JsonObject]


class BenchAggregate(TypedDict):
    n: int
    n_errors: int
    n_extraction_failures: int
    n_conformance_failures: NotRequired[int]
    raw_accuracy: float
    chance_corrected: float
    termination_rate: float
    conditional_accuracy: float


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
    readiness_warning = scorer_unavailable_warning(bench)
    if readiness_warning is not None:
        return _scorer_unavailable_items(bench, results, readiness_warning)
    scored: list[ScoredItem] = []
    try:
        for index, (source_item, result) in enumerate(zip(bench.source_items, results, strict=True)):
            if bench.name == "bigcodebench_hard":
                benchmark_item = bench.benchmark_items[index]
                scored.append(_score_bigcodebench_item(bench, source_item, benchmark_item, result))
                continue
            response_text = result["response_text"]
            error = result["error"]
            detailed = _score_response_detail(
                bench.name, source_item, response_text, error, result["finish_reason"]
            )
            correct = detailed["correct"] and result["finish_reason"] != "length"
            scored_item: ScoredItem = {
                "id": result["id"],
                "bench": bench.name,
                "response_text": response_text,
                "extracted": detailed["extracted"],
                "correct": correct,
                "finish_reason": result["finish_reason"],
                "latency_seconds": result["latency_seconds"],
                "started_at": result["started_at"],
                "finished_at": result["finished_at"],
                "attempts": result["attempts"],
                "usage": result["usage"],
                "error": error,
                "server_timings": result.get("server_timings"),
            }
            if "failure_kind" in detailed:
                scored_item["failure_kind"] = detailed["failure_kind"]
            scored.append(scored_item)
    except BackendLoadError as error:
        return _scorer_unavailable_items(
            bench,
            results,
            _scorer_unavailable_message(bench.name, str(error)),
        )
    return scored


def _score_bigcodebench_item(
    bench: RenderedBench,
    source_item: Mapping[str, JsonValue],
    benchmark_item: BenchmarkItem,
    result: ItemResult,
) -> ScoredItem:
    artifact = _code_artifact(source_item, benchmark_item, result)
    verdict = artifact.get("verdict")
    correct = (
        artifact.get("verdict_source") == "verifier"
        and isinstance(verdict, dict)
        and verdict.get("passed") is True
    )
    item: ScoredItem = {
        "id": result["id"],
        "bench": bench.name,
        "response_text": result["response_text"],
        "extracted": artifact.get("sanitized_code") if isinstance(artifact.get("sanitized_code"), str) else None,
        "correct": correct,
        "finish_reason": result["finish_reason"],
        "latency_seconds": result["latency_seconds"],
        "started_at": result["started_at"],
        "finished_at": result["finished_at"],
        "attempts": result["attempts"],
        "usage": result["usage"],
        "error": result["error"],
        "server_timings": result.get("server_timings"),
        "code_artifact": artifact,
    }
    extraction_status = artifact.get("extraction_status")
    if isinstance(extraction_status, dict) and isinstance(extraction_status.get("failure"), str):
        item["failure_kind"] = f"ambiguous_extraction:{extraction_status['failure']}"
    conformance_status = artifact.get("conformance_status")
    if isinstance(conformance_status, dict) and conformance_status.get("failure") == "coding_ast_rejected":
        item["failure_kind"] = "coding_ast_rejected"
    return item


def _code_artifact(
    source_item: Mapping[str, JsonValue],
    benchmark_item: BenchmarkItem,
    result: ItemResult,
) -> JsonObject:
    existing = result.get("code_artifact")
    if isinstance(existing, dict):
        return dict(existing)
    return dict(code_artifact_for_generation(source_item, benchmark_item, result))


def scorer_unavailable_warning(bench: RenderedBench) -> str | None:
    if bench.name in BFCL_MULTI_TURN_BENCHES:
        error = backend_readiness_error(_bfcl_multi_turn_classes(bench.source_items))
        if error is None:
            return None
        return _scorer_unavailable_message(bench.name, error)
    match bench.name:
        case _:
            return None


def scorer_unavailable_results(bench: RenderedBench, error: str) -> list[ItemResult]:
    return [_unavailable_result(item, error) for item in bench.benchmark_items]


def aggregate(bench: str, items: list[ScoredItem], baseline: float) -> BenchAggregate:
    """Aggregate item-level correctness into benchmark metrics."""
    n = len(items)
    n_correct = sum(1 for item in items if item["correct"])
    n_terminated = sum(
        1
        for item in items
        if item["error"] is None and item["finish_reason"] != "length"
    )
    raw_accuracy = n_correct / n if n else 0.0
    aggregate_result: BenchAggregate = {
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
        "chance_corrected": signed_score(raw_accuracy, chance=baseline),
        "termination_rate": n_terminated / n if n else 0.0,
        "conditional_accuracy": n_correct / n_terminated if n_terminated else 0.0,
    }
    if bench == "bigcodebench_hard":
        aggregate_result["n_conformance_failures"] = sum(
            1 for item in items if item.get("failure_kind") == "coding_ast_rejected"
        )
    return aggregate_result


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


def composite(
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock | None = None,
    suite_axes: Mapping[str, JsonValue] | None = None,
    weights: Mapping[str, float] | None = None,
) -> float:
    """Return the HEADLINE composite: benches pool into capability domains
    (item-weighted within a domain), then the HEADLINE domains combine by
    DOMAIN_WEIGHTS, normalized over the headline domains present. Candidate +
    experimental axes carry weight 0.0, so a present-but-unvalidated axis (Math,
    Long-Context, Agentic, Coding) is excluded from the scalar (see METHODOLOGY-v1.2
    §3). Math = olymmath_hard + amo as ONE axis. Matches the web pipeline's
    composite and paired_delta's domains. An unknown domain defaults to weight 0.0
    (never 1.0) so it can't silently dominate; a run with no headline axis -> 0.0.
    """
    if not benches:
        return 0.0
    composite_weights = DOMAIN_WEIGHTS if weights is None else weights
    measured = {
        name: bench
        for name, bench in benches.items()
        if bench_is_measured(name, axis_status, suite_axes)
    }
    domain_scores: dict[str, float] = {}
    for axis in AXES:
        facet_material = materialize_facet_samples(axis, measured)
        if axis.facets:
            if facet_material is None:
                continue
            domain_scores[axis.display] = sum(
                facet_material[1][bench] * aggregate["chance_corrected"]
                for bench, aggregate in facet_material[0].items()
            )
            continue
        selected = [
            aggregate
            for bench, aggregate in measured.items()
            if domain_for_bench(bench) == axis.display
        ]
        n = sum(aggregate["n"] for aggregate in selected)
        if n > 0:
            domain_scores[axis.display] = sum(
                aggregate["chance_corrected"] * aggregate["n"]
                for aggregate in selected
            ) / n
    if not domain_scores:
        return 0.0
    total_weight = sum(composite_weights.get(d, 0.0) for d in domain_scores)
    if total_weight <= 0:
        return 0.0
    return (
        sum(score * composite_weights.get(d, 0.0) for d, score in domain_scores.items())
        / total_weight
    )


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
    finish_reason: str | None = None,
) -> tuple[str | None, bool]:
    detailed = _score_response_detail(bench, source_item, response_text, error, finish_reason)
    return detailed["extracted"], detailed["correct"]


class ResponseScore(TypedDict):
    extracted: str | None
    correct: bool
    failure_kind: NotRequired[str | None]


def _score_response_detail(
    bench: str,
    source_item: Mapping[str, JsonValue],
    response_text: str | None,
    error: str | None,
    finish_reason: str | None = None,
) -> ResponseScore:
    if error is not None or response_text is None:
        return {"extracted": None, "correct": False}
    # Scorers see answer text stripped of reasoning; lane conformance still scans raw text.
    scorer_text = strip_reasoning(_strip_response_wrapper(response_text))
    if bench in BFCL_MULTI_TURN_BENCHES:
        detailed = score_bfcl_multi_turn(source_item, scorer_text)
        return {
            "extracted": detailed["extracted"],
            "correct": detailed["correct"],
            "failure_kind": detailed["failure_kind"],
        }
    match bench:
        case "mmlu_pro" | "supergpqa":
            detailed = score_mcq_detailed(
                scorer_text,
                _string(source_item.get("answer")) or "",
                len(_list(source_item.get("options"))),
            )
            return {"extracted": detailed["extracted"], "correct": detailed["correct"]}
        case "ifeval":
            return {
                "extracted": None,
                "correct": bool(score_ifeval(source_item, scorer_text)["strict"]),
            }
        case "ifbench":
            return {
                "extracted": None,
                "correct": bool(score_ifbench(source_item, scorer_text)["strict"]),
            }
        case "genmath":
            extracted = extract_final_number(scorer_text)
            return {
                "extracted": extracted,
                "correct": score_math(
                    scorer_text, _string(source_item.get("answer")) or ""
                ),
            }
        case "amo" | "olymmath_hard":
            allow_fallback = finish_reason != "length"
            extracted = extract_math_answer(
                scorer_text, allow_bare_number_fallback=allow_fallback
            )
            return {
                "extracted": extracted,
                "correct": verify_math(
                    scorer_text,
                    _string(source_item.get("answer")) or "",
                    finish_reason=finish_reason,
                ),
            }
        case "bfcl":
            detailed = score_bfcl(source_item, scorer_text)
            return {"extracted": detailed["extracted"], "correct": detailed["correct"]}
        case "tc_json_v1":
            detailed = score_tc_json_v1(source_item, scorer_text)
            return {
                "extracted": detailed["extracted"],
                "correct": detailed["correct"],
                "failure_kind": detailed["failure_reason"],
            }
        case "lcb":
            detailed = score_lcb(source_item, scorer_text)
            return {"extracted": detailed["extracted"], "correct": detailed["correct"]}
        case "ruler_32k":
            detailed = score_ruler(source_item, scorer_text)
            return {"extracted": detailed["extracted"], "correct": detailed["correct"]}
        case _:
            return {"extracted": None, "correct": False}


def _scorer_unavailable_items(
    bench: RenderedBench,
    results: list[ItemResult],
    warning: str,
) -> list[ScoredItem]:
    return [
        {
            "id": result["id"],
            "bench": bench.name,
            "response_text": result["response_text"],
            "extracted": None,
            "correct": False,
            "finish_reason": result["finish_reason"],
            "latency_seconds": result["latency_seconds"],
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
            "attempts": result["attempts"],
            "usage": result["usage"],
            "error": warning,
            "warnings": [warning],
            "server_timings": result.get("server_timings"),
        }
        for result in results
    ]


def _unavailable_result(item: BenchmarkItem, error: str) -> ItemResult:
    timestamp = _utc_now()
    return {
        "id": item["id"],
        "response_text": None,
        "reasoning_text": None,
        "finish_reason": None,
        "usage": empty_usage(),
        "latency_seconds": 0.0,
        "started_at": timestamp,
        "finished_at": timestamp,
        "attempts": 0,
        "error": error,
        "server_timings": None,
    }


def _bfcl_multi_turn_classes(items: list[Mapping[str, JsonValue]]) -> list[str]:
    classes: list[str] = []
    for item in items:
        involved = item.get("involved_classes")
        if not isinstance(involved, list):
            continue
        classes.extend(value for value in involved if isinstance(value, str))
    return classes


def _scorer_unavailable_message(bench: str, reason: str) -> str:
    return f"Scorer unavailable for {bench}: {reason}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _strip_response_wrapper(response_text: str) -> str:
    stripped = response_text.strip()
    if not stripped.startswith(_RESPONSE_OPEN) or not stripped.endswith(_RESPONSE_CLOSE):
        return response_text
    inner = stripped[len(_RESPONSE_OPEN) : -len(_RESPONSE_CLOSE)]
    return inner.strip()


def _list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _bench_has_extraction(bench: str) -> bool:
    return bench in BFCL_MULTI_TURN_BENCHES or bench in {
        "mmlu_pro",
        "genmath",
        "amo",
        "olymmath_hard",
        "supergpqa",
        "bfcl",
        "tc_json_v1",
        "lcb",
        "bigcodebench_hard",
        "ruler_32k",
    }


def _sum_usage(items: list[ScoredItem], key: str) -> int:
    return sum(
        value
        for item in items
        if isinstance((value := item["usage"][key]), int)
    )
