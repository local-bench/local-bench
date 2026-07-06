"""Aggregate per-task sandbox results into the coding-exec axis score.

Pass/fail is computed by the trusted runner from each task's subprocess exit code, never
self-reported by the generation. Chance baseline is 0 (writing working code is not
guessable), so chance-corrected == raw pass rate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, TypedDict

from localbench.scoring.signed_score import signed_score

BENCH: Final = "bigcodebench_hard"
CODING_SCOREABLE_REV: Final = "bcbh-scoreable-v1"
"""Revision tag for the BigCodeBench-Hard sandbox-scoreable scorer rule."""

SANDBOX_UNSCOREABLE_BCBH: Final[frozenset[str]] = frozenset(
    {
        "bcbh-006",
        "bcbh-007",
        "bcbh-014",
        "bcbh-035",
        "bcbh-074",
        "bcbh-096",
        "bcbh-104",
    },
)
"""Item ids whose upstream canonical solution fails in the mandatory --network none sandbox.

Derived from the pinned-revision ground-truth run; see
docs/reports/coding-exec-groundtruth-and-probes-2026-07-05.md and
docs/reports/bigcodebench_hard.scoreable-2026-07-05.json.
"""


class CodingExecScore(TypedDict):
    bench: str
    n: int
    n_passed: int
    n_timed_out: int
    n_no_code: int
    n_conformance_failures: int
    n_unscoreable: int
    raw_accuracy: float
    chance_corrected: float


def score_coding_exec(results: Sequence[Mapping[str, object]]) -> CodingExecScore:
    """Aggregate task results (each with a bool `passed`) into the axis score."""
    scoreable = [result for result in results if _is_scoreable(result)]
    n = len(scoreable)
    n_passed = sum(1 for result in scoreable if result.get("passed") is True)
    n_timed_out = sum(1 for result in scoreable if result.get("timed_out") is True)
    n_no_code = sum(1 for result in scoreable if result.get("no_code") is True)
    n_conformance_failures = sum(
        1 for result in scoreable if result.get("conformance_failure") == "coding_ast_rejected"
    )
    raw = n_passed / n if n else 0.0
    return {
        "bench": BENCH,
        "n": n,
        "n_passed": n_passed,
        "n_timed_out": n_timed_out,
        "n_no_code": n_no_code,
        "n_conformance_failures": n_conformance_failures,
        "n_unscoreable": len(results) - n,
        "raw_accuracy": raw,
        "chance_corrected": signed_score(raw, chance=0.0),
    }


def _is_scoreable(result: Mapping[str, object]) -> bool:
    item_id = result.get("id")
    return not isinstance(item_id, str) or item_id not in SANDBOX_UNSCOREABLE_BCBH
