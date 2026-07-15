from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from localbench.scoring.agentic_exec.task_journal_types import JournalError


class SleepDuringTaskError(JournalError):
    pass


class RuntimeRevalidationError(JournalError):
    pass


@dataclass(frozen=True, slots=True)
class TaskClockStart:
    wall_seconds: float
    monotonic_seconds: float
    slept_between_tasks: bool


class SleepWakeMonitor:
    def __init__(
        self,
        *,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        threshold_seconds: float = 5.0,
    ) -> None:
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._threshold_seconds = threshold_seconds
        self._previous_wall = wall_clock()
        self._previous_monotonic = monotonic_clock()

    def task_started(self) -> TaskClockStart:
        wall = self._wall_clock()
        monotonic = self._monotonic_clock()
        slept = self._diverged(
            self._previous_wall,
            self._previous_monotonic,
            wall,
            monotonic,
        )
        return TaskClockStart(wall, monotonic, slept)

    def task_finished(self, start: TaskClockStart) -> bool:
        wall = self._wall_clock()
        monotonic = self._monotonic_clock()
        slept = self._diverged(
            start.wall_seconds,
            start.monotonic_seconds,
            wall,
            monotonic,
        )
        self._previous_wall = wall
        self._previous_monotonic = monotonic
        return slept

    def _diverged(
        self,
        wall_start: float,
        monotonic_start: float,
        wall_end: float,
        monotonic_end: float,
    ) -> bool:
        wall_elapsed = wall_end - wall_start
        monotonic_elapsed = monotonic_end - monotonic_start
        return wall_elapsed - monotonic_elapsed > self._threshold_seconds
