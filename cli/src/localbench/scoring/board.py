"""Public scorer-side board_v1.json generator API."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.scoring.axes import web_composite_weights
from localbench.scoring.board_manifest import release_manifest
from localbench.scoring.board_scoring import model_rows, scored_runs, suite_version
from localbench.scoring.board_sources import load_sources
from localbench.scoring.board_support import (
    DATASET_VERSION,
    DEFAULT_BOOTSTRAP_ITERS,
    DEFAULT_CURATION,
    DEFAULT_OUT,
    DEFAULT_PARITY_INDEX,
    DEFAULT_RUNS_DIR,
    LANE_SCOPE,
    index_version,
    number_or_none,
    object_or_empty,
    object_or_none,
    object_value,
    objects_value,
    read_json,
    text_value,
    write_json,
)
from localbench.scoring.board_types import BoardBuildError, BoardWriteResult, ParityDivergence, ParityResult
from localbench.scoring.scorecard import SCORECARD_VERSION

GENERATED_NOTE: Final = (
    "Produced by localbench board from scorer-side scores; board-v1 is an immutable "
    "release artifact for pure rendering."
)


def build_board(
    *,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    curation_path: Path | None = None,
    generated_at: str | None = None,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
) -> JsonObject:
    """Build the board payload without writing files."""
    timestamp = generated_at or datetime.now(UTC).isoformat()
    sources = load_sources(curation_path or DEFAULT_CURATION)
    scored, skipped = scored_runs(
        sources,
        runs_dir=runs_dir,
        bootstrap_iters=bootstrap_iters,
        weights=web_composite_weights(),
    )
    board_suite_version = suite_version(scored)
    board_index_version = index_version(DEFAULT_PARITY_INDEX)
    return {
        "generated_note": GENERATED_NOTE,
        "schema_version": "board-v1",
        "index_version": board_index_version,
        "suite_version": board_suite_version,
        "scoring_version": SCORECARD_VERSION,
        "dataset_version": DATASET_VERSION,
        "lane_scope": LANE_SCOPE,
        "generated_at": timestamp,
        "models": model_rows(scored),
        "manifest": release_manifest(
            scored,
            skipped=skipped,
            generated_at=timestamp,
            suite_version=board_suite_version,
            index_version=board_index_version,
        ),
    }


def write_board(
    *,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    out: Path = DEFAULT_OUT,
    curation_path: Path | None = None,
    frozen_timestamp: str | None = None,
    check_parity: bool = True,
    parity_index: Path = DEFAULT_PARITY_INDEX,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
) -> BoardWriteResult:
    """Write board_v1.json and its sidecar release manifest."""
    board = build_board(
        runs_dir=runs_dir,
        curation_path=curation_path,
        generated_at=frozen_timestamp,
        bootstrap_iters=bootstrap_iters,
    )
    write_json(out, board)
    board_sha = hashlib.sha256(out.read_bytes()).hexdigest()
    manifest = object_value(board["manifest"], "board.manifest") | {"board_sha256": board_sha}
    manifest_path = out.with_name(f"{out.stem}.manifest.json")
    write_json(manifest_path, manifest)
    parity = check_board_parity(board, index_path=parity_index) if check_parity else ParityResult(False)
    return BoardWriteResult(out, manifest_path, board_sha, parity)


def check_board_parity(
    board: Mapping[str, JsonValue],
    *,
    index_path: Path = DEFAULT_PARITY_INDEX,
    tolerance: float = 1e-6,
) -> ParityResult:
    """Compare board points with the current web index points."""
    if not index_path.exists():
        return ParityResult(False)
    index = object_value(read_json(index_path), str(index_path))
    by_slug = {
        text_value(model.get("slug")): model
        for model in objects_value(index.get("models"), "index.models")
        if text_value(model.get("slug")) is not None
    }
    divergences: list[ParityDivergence] = []
    for model in objects_value(board.get("models"), "board.models"):
        slug = text_value(model.get("slug"))
        if slug is None or not _is_measured(model):
            continue
        index_model = by_slug.get(slug)
        if index_model is None or not _is_measured(index_model):
            divergences.append(ParityDivergence(slug, "model", _model_point(model), None))
            continue
        _compare_score(divergences, slug, "composite.point", model.get("composite"), index_model.get("composite"), tolerance)
        _compare_axes(divergences, slug, model, index_model, tolerance)
    return ParityResult(True, tuple(divergences))


def _compare_axes(
    divergences: list[ParityDivergence],
    slug: str,
    model: Mapping[str, JsonValue],
    index_model: Mapping[str, JsonValue],
    tolerance: float,
) -> None:
    board_axes = object_value(model.get("axes"), f"{slug}.axes")
    index_axes = object_value(index_model.get("axes"), f"{slug}.index_axes")
    for axis, board_axis in board_axes.items():
        if axis in index_axes:
            _compare_score(divergences, slug, f"axes.{axis}.point", board_axis, index_axes[axis], tolerance)


def _compare_score(
    divergences: list[ParityDivergence],
    slug: str,
    field: str,
    board_raw: JsonValue | None,
    index_raw: JsonValue | None,
    tolerance: float,
) -> None:
    board_point = _score_point(object_or_none(board_raw))
    index_point = _score_point(object_or_none(index_raw))
    if board_point is None or index_point is None or abs(board_point - index_point) > tolerance:
        divergences.append(ParityDivergence(slug, field, board_point, index_point))


def _is_measured(model: Mapping[str, JsonValue]) -> bool:
    return text_value(model.get("score_status")) in {None, "measured"} and object_or_none(model.get("composite")) is not None


def _model_point(model: Mapping[str, JsonValue]) -> float | None:
    return number_or_none(object_or_empty(model.get("composite")).get("point"))


def _score_point(score: Mapping[str, JsonValue] | None) -> float | None:
    return None if score is None else number_or_none(score.get("point"))


__all__ = [
    "BoardBuildError",
    "BoardWriteResult",
    "ParityDivergence",
    "ParityResult",
    "build_board",
    "check_board_parity",
    "web_composite_weights",
    "write_board",
]
