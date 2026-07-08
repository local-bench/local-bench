from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SleepWakeClockGap(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True)
class SleepGapMonitor:
    threshold_seconds: float = 300.0
    allow_sleep_risk: bool = False
    _last_wall: float | None = None
    _last_monotonic: float | None = None

    def checkpoint(self, *, wall_seconds: float | None = None, monotonic_seconds: float | None = None) -> None:
        wall = time.time() if wall_seconds is None else wall_seconds
        monotonic = time.monotonic() if monotonic_seconds is None else monotonic_seconds
        if self._last_wall is not None and self._last_monotonic is not None:
            wall_delta = wall - self._last_wall
            monotonic_delta = monotonic - self._last_monotonic
            clock_gap = wall_delta - monotonic_delta
            if clock_gap > self.threshold_seconds and not self.allow_sleep_risk:
                raise SleepWakeClockGap(
                    f"sleep/wake clock gap detected ({clock_gap:.1f}s); rerun with --allow-sleep-risk to continue",
                )
        self._last_wall = wall
        self._last_monotonic = monotonic
