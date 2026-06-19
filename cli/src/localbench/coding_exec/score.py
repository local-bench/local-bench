"""Aggregate per-task sandbox results into the coding-exec axis score.

Pass/fail is computed by the trusted runner from each task's subprocess exit code, never
self-reported by the generation. Chance baseline is 0 (writing working code is not
guessable), so chance-corrected == raw pass rate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict

from localbench.scoring.signed_score import signed_score

BENCH = "bigcodebench_hard"


class CodingExecScore(TypedDict):
    bench: str
    n: int
    n_passed: int
    n_timed_out: int
    n_no_code: int
    raw_accuracy: float
    chance_corrected: float


def score_coding_exec(results: Sequence[Mapping[str, object]]) -> CodingExecScore:
    """Aggregate task results (each with a bool `passed`) into the axis score."""
    n = len(results)
    n_passed = sum(1 for result in results if result.get("passed") is True)
    n_timed_out = sum(1 for result in results if result.get("timed_out") is True)
    n_no_code = sum(1 for result in results if result.get("no_code") is True)
    raw = n_passed / n if n else 0.0
    return {
        "bench": BENCH,
        "n": n,
        "n_passed": n_passed,
        "n_timed_out": n_timed_out,
        "n_no_code": n_no_code,
        "raw_accuracy": raw,
        "chance_corrected": signed_score(raw, chance=0.0),
    }
