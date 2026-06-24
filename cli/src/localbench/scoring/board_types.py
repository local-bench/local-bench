"""Typed contracts for board_v1 generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from localbench._types import JsonObject


class BoardBuildError(ValueError):
    """Raised when board inputs are invalid enough to stop generation."""


@dataclass(frozen=True, slots=True)
class ParityDivergence:
    model: str
    field: str
    board_value: float | None
    index_value: float | None


@dataclass(frozen=True, slots=True)
class ParityResult:
    checked: bool
    divergences: tuple[ParityDivergence, ...] = ()


@dataclass(frozen=True, slots=True)
class BoardWriteResult:
    board_path: Path
    manifest_path: Path
    board_sha256: str
    parity: ParityResult


class CuratedSource(TypedDict):
    family: str
    file: str
    independent_replication: bool
    kind: str
    model_id: str | None
    model_label: str
    quant_label: str | None
    recommended: bool
    reasoning_lane: str | None


class ScoredRun(TypedDict):
    axes: JsonObject
    best_run_id: str
    catalog_id: str | None
    composite: JsonObject
    composite_raw: float
    est_cost_usd: float | None
    family: str
    kind: str
    lane: str | None
    model_label: str
    order: int
    quant_label: str | None
    ranked: bool
    recommended: bool
    replicated: bool
    run_id: str
    run_path_stem: str
    score_status: str
    slug: str
    tier: str | None
    tokens_to_answer_median: float | None
    tokens_to_answer_p95: float | None
    latency_s_median: float | None
    wall_time_seconds: float | None
    suite_version: str | None
    item_set_hashes: JsonObject
