"""Per-quant system row assembly for board_v1 family rows."""

from __future__ import annotations

from collections.abc import Sequence

from localbench._types import JsonObject
from localbench.scoring.board_types import BoardBuildError, ScoredRun


def best_system(group: Sequence[ScoredRun]) -> ScoredRun:
    """Return the quant that carries the family headline score."""
    return _ranked_systems(group)[0]


def system_fields(group: Sequence[ScoredRun], best: ScoredRun) -> JsonObject:
    """Build additive per-quant fields for one family row."""
    recommended = _recommended_system(group, best)
    return {
        "best_system_run_id": best["run_id"],
        "recommended_system_run_id": recommended["run_id"],
        "systems": [_system_row(run, best=best, recommended=recommended) for run in _ranked_systems(group)],
    }


def _ranked_systems(group: Sequence[ScoredRun]) -> list[ScoredRun]:
    return sorted(group, key=lambda run: (-run["composite_raw"], run["order"]))


def _recommended_system(group: Sequence[ScoredRun], best: ScoredRun) -> ScoredRun:
    recommended = [run for run in group if run["recommended"]]
    if len(recommended) > 1:
        raise BoardBuildError(f"{best['family']} must have at most one recommended quant")
    return recommended[0] if recommended else best


def _system_row(run: ScoredRun, *, best: ScoredRun, recommended: ScoredRun) -> JsonObject:
    row: JsonObject = {
        "quant_label": run["quant_label"],
        "run_id": run["run_id"],
        "composite": run["composite"],
        "axes": run["axes"],
        "tier": run["tier"],
        "lane": run["lane"],
        "ranked": run["ranked"],
        "n_runs": 1,
        "replicated": run["replicated"],
        "score_status": run["score_status"],
        "tokens_to_answer_median": run["tokens_to_answer_median"],
        "tokens_to_answer_p95": run["tokens_to_answer_p95"],
        "latency_s_median": run["latency_s_median"],
        "wall_time_seconds": run["wall_time_seconds"],
        "est_cost_usd": run["est_cost_usd"],
        "is_best": run["run_id"] == best["run_id"],
        "is_recommended": run["run_id"] == recommended["run_id"],
    }
    publisher = run.get("publisher")
    if publisher is not None:
        row["publisher"] = publisher
    gguf_repo = run.get("gguf_repo")
    if gguf_repo is not None:
        row["gguf_repo"] = gguf_repo
    if "conformance_gates" in run:
        row["conformance_gates"] = run["conformance_gates"]
    return row
