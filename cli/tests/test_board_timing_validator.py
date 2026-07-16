"""Wall-time consistency validator: a resumed run's last-segment-only clock must not board.

Regression guard for the 2026-07-15 gemma-31b incident: three run segments, cumulative
token totals, but totals.wall_time_seconds overwritten with the final segment's process
clock — implying 385 tok/s from a model that decodes at 63 tok/s.
"""

from pathlib import Path

import pytest

from localbench.scoring.board_scoring import (
    _WALL_TIME_CONSISTENCY_FACTOR,
    _validate_wall_time_consistency,
)
from localbench.scoring.board_types import BoardBuildError

PATH = Path("gemma-4-31b-it-q4km-s2v5.json")


def record(wall: float | None, completion: float | None, decode: float | None) -> tuple[dict, dict]:
    run = {"perf": {"decode_tps": decode}} if decode is not None else {"perf": {}}
    totals: dict = {}
    if wall is not None:
        totals["wall_time_seconds"] = wall
    if completion is not None:
        totals["completion_tokens"] = completion
    return run, totals


def test_last_segment_only_wall_time_is_rejected() -> None:
    # The real corrupted numbers: 4.85M tokens over 12,580s vs 63.08 tok/s decode.
    run, totals = record(wall=12580.05, completion=4_848_815, decode=63.08)
    with pytest.raises(BoardBuildError) as exc:
        _validate_wall_time_consistency(run, totals, PATH)
    message = str(exc.value)
    assert "wall_time_seconds" in message
    assert "decode_tps" in message
    assert PATH.name in message


def test_corrected_cumulative_wall_time_passes() -> None:
    # The corrected record: implied 48.4 tok/s under a 63.08 tok/s decode rate.
    run, totals = record(wall=100_257.26, completion=4_848_815, decode=63.08)
    _validate_wall_time_consistency(run, totals, PATH)


def test_every_current_ranked_ratio_shape_passes() -> None:
    # Implied/decode ratios seen on the live board (0.77-0.93) sit well under the factor.
    for wall, completion, decode in [
        (85_346, 5_921_541, 74.4),
        (85_137, 5_429_223, 71.0),
        (33_278, 6_349_939, 228.0),
        (61_750, 8_468_917, 147.5),
    ]:
        run, totals = record(wall=wall, completion=completion, decode=decode)
        _validate_wall_time_consistency(run, totals, PATH)


def test_tolerance_band_is_not_a_hair_trigger() -> None:
    # Slightly above decode (measurement noise) stays under factor 1.25 and passes...
    run, totals = record(wall=1_000, completion=70_000, decode=63.0)
    _validate_wall_time_consistency(run, totals, PATH)
    # ...but beyond the band it fails.
    run, totals = record(wall=1_000, completion=80_000, decode=63.0)
    with pytest.raises(BoardBuildError):
        _validate_wall_time_consistency(run, totals, PATH)


def test_missing_fields_do_not_trip_the_guard() -> None:
    for wall, completion, decode in [
        (None, 4_848_815, 63.08),
        (12_580.05, None, 63.08),
        (12_580.05, 4_848_815, None),
        (0, 4_848_815, 63.08),
        (12_580.05, 4_848_815, 0),
    ]:
        run, totals = record(wall=wall, completion=completion, decode=decode)
        _validate_wall_time_consistency(run, totals, PATH)


def test_factor_is_a_deliberate_band() -> None:
    assert _WALL_TIME_CONSISTENCY_FACTOR == 1.25
