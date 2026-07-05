"""Lane-conformance assessment: is a run actually comparable on the locked lane?

Oracle red-team finding #2: "OpenAI-compatible" is an API shape, not a semantics
guarantee. Different runtimes can leak chain-of-thought into the SCORED content, hit the
token cap (truncating answers), or return no final answer at all — and because IFBench
(50% of the headline) scores the FINAL answer text, a runtime that leaks <think> or
truncates is measuring the wrong thing, not instruction-following.

This classifies each run from its OWN item results (no extra endpoint calls) as
headline-comparable / nonconformant / diagnostic-only, so a nonconformant endpoint never
silently enters the headline. Conformance is assessed PER BENCH and the run takes the
worst status — a bench-local failure (e.g. IFBench leakage) can't be diluted by the rest
of the run (autoreview, 2026-06-19).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Final, Literal

from localbench._types import ItemResult, JsonObject
from localbench.lane_spec import BOUNDED_FINAL_LANE_SPEC_ID
from localbench.reasoning_leaks import has_reasoning_leak

ConformanceStatus = Literal["headline-comparable", "nonconformant", "diagnostic-only"]

_SEVERITY: Final[dict[str, int]] = {
    "headline-comparable": 0,
    "nonconformant": 1,
    "diagnostic-only": 2,
}

@dataclass(frozen=True, slots=True)
class ConformanceThresholds:
    """Editorial thresholds; a breach excludes a bench (and so the run) from the headline.

    Leaked reasoning is the most corrupting (it changes WHAT is scored), so it trips at a
    low rate; truncation / no-final-answer degrade scores and trip higher. The `diagnostic`
    levels mark a bench so broken it is barely usable even as a profile.
    """

    leaked_reasoning_nonconformant: float = 0.02
    leaked_reasoning_diagnostic: float = 0.25
    truncation_nonconformant: float = 0.10
    no_final_answer_nonconformant: float = 0.10
    no_final_answer_diagnostic: float = 0.25


DEFAULT_THRESHOLDS: Final = ConformanceThresholds()


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    status: ConformanceStatus
    n_scored: int
    truncation_rate: float
    leaked_reasoning_rate: float
    no_final_answer_rate: float
    reasons: tuple[str, ...]
    forced: bool = False
    budget_cap_hit_rate: float | None = None
    measurement_truncation_rate: float | None = None
    empty_final_rate: float | None = None
    ambiguous_or_contaminated_final_rate: float | None = None

    def as_dict(self) -> JsonObject:
        data: JsonObject = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def has_leaked_reasoning(
    response_text: str | None,
    extra_regexes: Sequence[str] = (),
) -> bool:
    """True when chain-of-thought leaked into the SCORED content (response_text)."""
    return has_reasoning_leak(response_text, extra_regexes)


def _no_final_answer(result: ItemResult) -> bool:
    """True when there is no distinct FINAL answer to score.

    Empty content, or the parser's reasoning-fallback (`_response.py`: when content is
    empty it sets response_text = reasoning_content) — a truncated-mid-think / reasoning-
    only response whose 'answer' is actually raw chain-of-thought.
    """
    text = result.get("response_text")
    if not (text or "").strip():
        return True
    reasoning = result.get("reasoning_text")
    return bool(reasoning) and text == reasoning


def _empty_final(result: ItemResult) -> bool:
    return not (result.get("response_text") or "").strip()


def _ambiguous_or_contaminated_final(
    result: ItemResult,
    leak_regexes: Sequence[str],
) -> bool:
    text = result.get("response_text")
    reasoning = result.get("reasoning_text")
    return (bool(reasoning) and text == reasoning) or has_leaked_reasoning(text, leak_regexes)


def assess_conformance(
    results: Sequence[ItemResult],
    *,
    thresholds: ConformanceThresholds = DEFAULT_THRESHOLDS,
    forced: bool = False,
    leak_regexes: Sequence[str] = (),
    lane_spec_id: str | None = None,
) -> ConformanceReport:
    """Classify ONE bench's lane-conformance from its item results.

    Errored items are excluded (they're an availability problem, not a conformance one);
    rates are over the scored remainder. Zero scored items is diagnostic-only.

    `forced` marks a budget-forcing run (local capped-thinking with two-pass forcing): the
    model got the locked think budget plus a forced answer pass, so an answer-pass cap hit
    (finish_reason=length) is the MODEL failing to terminate (degenerate loop / non-
    termination), scored wrong, NOT a measurement breach. It is surfaced as a visible
    diagnostic but does not exclude the run from the headline (oracle red-team 2026-06-20,
    option A). Leaked-reasoning and no-final-answer remain hard gates either way.
    """
    if lane_spec_id == BOUNDED_FINAL_LANE_SPEC_ID:
        return _assess_bounded_final_conformance(
            results,
            thresholds=thresholds,
            leak_regexes=leak_regexes,
        )

    scored = [result for result in results if not result.get("error")]
    n = len(scored)
    if n == 0:
        return ConformanceReport("diagnostic-only", 0, 0.0, 0.0, 0.0, ("no scored items",), forced)

    truncation_rate = _rate(sum(1 for r in scored if r.get("finish_reason") == "length"), n)
    leaked_rate = _rate(sum(1 for r in scored if has_leaked_reasoning(r.get("response_text"), leak_regexes)), n)
    no_answer_rate = _rate(sum(1 for r in scored if _no_final_answer(r)), n)

    reasons: list[str] = []
    status: ConformanceStatus = "headline-comparable"

    if leaked_rate >= thresholds.leaked_reasoning_diagnostic:
        status = "diagnostic-only"
        reasons.append(f"chain-of-thought leaked into scored content in {leaked_rate:.0%} of items")
    elif no_answer_rate >= thresholds.no_final_answer_diagnostic:
        status = "diagnostic-only"
        reasons.append(f"no distinct final answer in {no_answer_rate:.0%} of items")
    else:
        if leaked_rate >= thresholds.leaked_reasoning_nonconformant:
            status = "nonconformant"
            reasons.append(
                f"chain-of-thought leaked into scored content in {leaked_rate:.0%} of items "
                "(IFBench/MCQ corrupting)"
            )
        if not forced and truncation_rate >= thresholds.truncation_nonconformant:
            status = "nonconformant"
            reasons.append(f"{truncation_rate:.0%} of items hit the token cap (answers truncated)")
        if no_answer_rate >= thresholds.no_final_answer_nonconformant:
            status = "nonconformant"
            reasons.append(f"no distinct final answer in {no_answer_rate:.0%} of items")

    if forced and truncation_rate > 0:
        # Soft diagnostic (oracle option A + D): visible, but not a headline exclusion.
        reasons.append(
            f"answer_cap_hit_rate={truncation_rate:.0%} - scored as model failures under "
            "budget-forcing (degenerate loop / non-termination), not a conformance breach"
        )

    return ConformanceReport(
        status=status,
        n_scored=n,
        truncation_rate=truncation_rate,
        leaked_reasoning_rate=leaked_rate,
        no_final_answer_rate=no_answer_rate,
        reasons=tuple(reasons),
        forced=forced,
    )


def _assess_bounded_final_conformance(
    results: Sequence[ItemResult],
    *,
    thresholds: ConformanceThresholds,
    leak_regexes: Sequence[str],
) -> ConformanceReport:
    scored = [result for result in results if not result.get("error")]
    n = len(scored)
    if n == 0:
        return ConformanceReport("diagnostic-only", 0, 0.0, 0.0, 0.0, ("no scored items",))

    budget_cap_hits = sum(1 for result in scored if _is_budget_cap_hit(result))
    measurement_truncations = sum(
        1
        for result in scored
        if result.get("finish_reason") == "length" and not _is_budget_cap_hit(result)
    )
    empty_finals = sum(1 for result in scored if _empty_final(result))
    contaminated = sum(
        1
        for result in scored
        if _ambiguous_or_contaminated_final(result, leak_regexes)
    )
    leaked = sum(
        1
        for result in scored
        if has_leaked_reasoning(result.get("response_text"), leak_regexes)
    )
    budget_cap_rate = _rate(budget_cap_hits, n)
    measurement_rate = _rate(measurement_truncations, n)
    empty_rate = _rate(empty_finals, n)
    contaminated_rate = _rate(contaminated, n)
    leaked_rate = _rate(leaked, n)
    truncation_rate = _rate(budget_cap_hits + measurement_truncations, n)
    no_answer_rate = _rate(empty_finals + contaminated, n)

    reasons: list[str] = []
    status: ConformanceStatus = "headline-comparable"
    if leaked_rate >= thresholds.leaked_reasoning_diagnostic:
        status = "diagnostic-only"
        reasons.append(f"chain-of-thought leaked into scored content in {leaked_rate:.0%} of items")
    elif contaminated_rate >= thresholds.leaked_reasoning_diagnostic:
        status = "diagnostic-only"
        reasons.append(
            "ambiguous_or_contaminated_final_rate="
            f"{contaminated_rate:.0%} - final text is not a clean final answer",
        )
    else:
        if measurement_rate > 0:
            status = "nonconformant"
            reasons.append(
                f"measurement_truncation_rate={measurement_rate:.0%} - stopped below promised T_i",
            )
        if leaked_rate >= thresholds.leaked_reasoning_nonconformant:
            status = "nonconformant"
            reasons.append(
                f"chain-of-thought leaked into scored content in {leaked_rate:.0%} of items "
                "(IFBench/MCQ corrupting)"
            )
        if contaminated_rate >= thresholds.leaked_reasoning_nonconformant:
            status = "nonconformant"
            reasons.append(
                "ambiguous_or_contaminated_final_rate="
                f"{contaminated_rate:.0%} - final text is not a clean final answer",
            )
    if budget_cap_rate > 0:
        reasons.append(
            f"budget_cap_hit_rate={budget_cap_rate:.0%} - visible scored cap hits, not exclusions",
        )
    if empty_rate > 0:
        reasons.append(
            f"empty_final_rate={empty_rate:.0%} - scored as zero, not an automatic exclusion",
        )
    return ConformanceReport(
        status=status,
        n_scored=n,
        truncation_rate=truncation_rate,
        leaked_reasoning_rate=leaked_rate,
        no_final_answer_rate=no_answer_rate,
        reasons=tuple(reasons),
        budget_cap_hit_rate=budget_cap_rate,
        measurement_truncation_rate=measurement_rate,
        empty_final_rate=empty_rate,
        ambiguous_or_contaminated_final_rate=contaminated_rate,
    )


def _is_budget_cap_hit(result: ItemResult) -> bool:
    if result.get("finish_reason") != "length":
        return False
    total = _generated_total(result)
    max_tokens = result.get("max_tokens")
    return (
        total is not None
        and isinstance(max_tokens, int)
        and not isinstance(max_tokens, bool)
        and total == max_tokens
    )


def _generated_total(result: ItemResult) -> int | None:
    usage = result.get("usage")
    if isinstance(usage, dict):
        completion = usage.get("completion_tokens")
        if isinstance(completion, int) and not isinstance(completion, bool):
            return completion
    generated = result.get("generated_tokens")
    if isinstance(generated, dict):
        total = generated.get("total")
        if isinstance(total, int) and not isinstance(total, bool):
            return total
    return None


def assess_run_conformance(
    results_by_bench: Mapping[str, Sequence[ItemResult]],
    *,
    thresholds: ConformanceThresholds = DEFAULT_THRESHOLDS,
    forced: bool = False,
    leak_regexes_by_bench: Mapping[str, Sequence[str]] | None = None,
    lane_spec_id: str | None = None,
) -> JsonObject:
    """Run-level conformance = the WORST bench status (no dilution of a bench-local
    failure), plus the per-bench breakdown. This is the run_record["conformance"] block.

    `forced` is threaded to every bench: under budget-forcing, answer-pass cap hits are
    scored model failures, not headline-excluding truncation (see assess_conformance).
    """
    per_bench = {
        bench: assess_conformance(
            results,
            thresholds=thresholds,
            forced=forced,
            leak_regexes=(leak_regexes_by_bench or {}).get(bench, ()),
            lane_spec_id=lane_spec_id,
        )
        for bench, results in results_by_bench.items()
    }
    if not per_bench:
        return {"status": "diagnostic-only", "n_scored": 0, "worst_bench": None, "reasons": ["no benches"], "per_bench": {}}

    worst_bench, worst = max(per_bench.items(), key=lambda item: _SEVERITY[item[1].status])
    clean = worst.status == "headline-comparable"
    return {
        "status": worst.status,
        "n_scored": sum(report.n_scored for report in per_bench.values()),
        "worst_bench": None if clean else worst_bench,
        "reasons": [] if clean else [f"{worst_bench}: {reason}" for reason in worst.reasons],
        "per_bench": {bench: report.as_dict() for bench, report in per_bench.items()},
    }


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0
