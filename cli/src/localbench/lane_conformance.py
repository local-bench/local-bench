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

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Final, Literal

from localbench._types import ItemResult, JsonObject

ConformanceStatus = Literal["headline-comparable", "nonconformant", "diagnostic-only"]

_SEVERITY: Final[dict[str, int]] = {
    "headline-comparable": 0,
    "nonconformant": 1,
    "diagnostic-only": 2,
}

# Reasoning that leaked into the SCORED content (the endpoint did NOT separate
# reasoning_content from content). Every alternative REQUIRES a delimiter, so the bare
# word "think" in a normal answer never matches. Covers the common fences across runtimes
# (llama.cpp, vLLM, DeepSeek/Qwen <|...|> sentinels). The separated reasoning_text channel
# is fine — only markers inside response_text are leaks.
_LEAKED_REASONING: Final = re.compile(
    r"</?think\b|</?thinking\b|</?thought\b|</?reason(?:ing)?\b|</?scratchpad\b"
    r"|◁think▷|<\|/?think(?:ing)?\|>|<\|/?(?:begin|end)_of_thought\|>",
    re.IGNORECASE,
)


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

    def as_dict(self) -> JsonObject:
        data: JsonObject = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def has_leaked_reasoning(response_text: str | None) -> bool:
    """True when chain-of-thought leaked into the SCORED content (response_text)."""
    return bool(response_text) and _LEAKED_REASONING.search(response_text) is not None


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


def assess_conformance(
    results: Sequence[ItemResult],
    *,
    thresholds: ConformanceThresholds = DEFAULT_THRESHOLDS,
    forced: bool = False,
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
    scored = [result for result in results if not result.get("error")]
    n = len(scored)
    if n == 0:
        return ConformanceReport("diagnostic-only", 0, 0.0, 0.0, 0.0, ("no scored items",), forced)

    truncation_rate = _rate(sum(1 for r in scored if r.get("finish_reason") == "length"), n)
    leaked_rate = _rate(sum(1 for r in scored if has_leaked_reasoning(r.get("response_text"))), n)
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


def assess_run_conformance(
    results_by_bench: Mapping[str, Sequence[ItemResult]],
    *,
    thresholds: ConformanceThresholds = DEFAULT_THRESHOLDS,
    forced: bool = False,
) -> JsonObject:
    """Run-level conformance = the WORST bench status (no dilution of a bench-local
    failure), plus the per-bench breakdown. This is the run_record["conformance"] block.

    `forced` is threaded to every bench: under budget-forcing, answer-pass cap hits are
    scored model failures, not headline-excluding truncation (see assess_conformance).
    """
    per_bench = {
        bench: assess_conformance(results, thresholds=thresholds, forced=forced)
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
