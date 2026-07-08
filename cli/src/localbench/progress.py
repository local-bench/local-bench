from __future__ import annotations

import shutil
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True, slots=True)
class BenchProgressPlan:
    name: str
    total_items: int


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    current_bench: str
    current_bench_done: int
    current_bench_total: int
    overall_done: int
    overall_total: int
    percent: float
    elapsed_seconds: float
    eta_seconds: float | None


class ProgressEstimator:
    def __init__(
        self,
        plans: Sequence[BenchProgressPlan],
        *,
        min_samples: int = 3,
        rolling_window: int = 20,
    ) -> None:
        self._plans = tuple(plans)
        self._totals = {plan.name: max(0, plan.total_items) for plan in self._plans}
        self._done = {plan.name: 0 for plan in self._plans}
        self._samples = {plan.name: deque[float](maxlen=max(1, rolling_window)) for plan in self._plans}
        self._min_samples = max(1, min_samples)

    @property
    def plans(self) -> tuple[BenchProgressPlan, ...]:
        return self._plans

    @property
    def overall_total(self) -> int:
        return sum(self._totals.values())

    @property
    def overall_done(self) -> int:
        return sum(self._done.values())

    def record_completion(self, bench: str, item_seconds: float) -> None:
        if bench not in self._totals:
            return
        self._samples[bench].append(max(0.0, float(item_seconds)))
        self._done[bench] = min(self._totals[bench], self._done[bench] + 1)

    def per_bench_average_seconds(self, bench: str) -> float | None:
        samples = self._samples.get(bench)
        if not samples:
            return None
        return sum(samples) / len(samples)

    def eta_seconds(self) -> float | None:
        if self.overall_done >= self.overall_total:
            return 0.0
        if self._sample_count() < self._min_samples:
            return None
        fallback = self._global_average()
        if fallback is None:
            return None
        eta = 0.0
        for plan in self._plans:
            remaining = max(0, self._totals[plan.name] - self._done[plan.name])
            average = self.per_bench_average_seconds(plan.name) or fallback
            eta += remaining * average
        return max(0.0, eta)

    def snapshot(
        self,
        *,
        current_bench: str,
        current_bench_done: int | None = None,
        elapsed_seconds: float = 0.0,
    ) -> ProgressSnapshot:
        bench_total = self._totals.get(current_bench, 0)
        bench_done = self._done.get(current_bench, 0)
        if current_bench_done is not None:
            bench_done = min(bench_total, max(0, current_bench_done))
        overall_total = self.overall_total
        overall_done = self.overall_done
        percent = 0.0 if overall_total == 0 else min(100.0, (overall_done / overall_total) * 100.0)
        return ProgressSnapshot(
            current_bench=current_bench,
            current_bench_done=bench_done,
            current_bench_total=bench_total,
            overall_done=overall_done,
            overall_total=overall_total,
            percent=percent,
            elapsed_seconds=max(0.0, elapsed_seconds),
            eta_seconds=self.eta_seconds(),
        )

    def _sample_count(self) -> int:
        return sum(len(samples) for samples in self._samples.values())

    def _global_average(self) -> float | None:
        values = [value for samples in self._samples.values() for value in samples]
        if not values:
            return None
        return sum(values) / len(values)


class ProgressLineFormatter:
    def __init__(
        self,
        *,
        width: int | None = None,
        bar_width: int = 20,
        bar_chars: tuple[str, str] = ("█", "░"),
    ) -> None:
        self._width = width
        self._bar_width = max(0, bar_width)
        self._bar_chars = bar_chars

    def prerun_total_line(self, plans: Sequence[BenchProgressPlan], eta_seconds: float | None = None) -> str:
        total = sum(max(0, plan.total_items) for plan in plans)
        benches = len(plans)
        eta = "estimating..." if eta_seconds is None else _format_seconds(eta_seconds)
        return self._truncate(f"estimate   {total} items across {benches} benches; ETA {eta}")

    def status_line(self, snapshot: ProgressSnapshot) -> str:
        eta = "estimating..." if snapshot.eta_seconds is None else _format_seconds(snapshot.eta_seconds)

        def render(bar: str) -> str:
            return (
                f"progress {snapshot.current_bench} "
                f"{snapshot.current_bench_done}/{snapshot.current_bench_total} bench "
                f"{snapshot.overall_done}/{snapshot.overall_total} "
                f"{bar}{snapshot.percent:.1f}% e {_format_seconds(snapshot.elapsed_seconds)} ETA {eta}"
            )

        line = render(self._bar(snapshot.percent))
        # On narrow consoles the bar is the expendable part: drop it before letting
        # _truncate cut counts/ETA out of the middle of the line.
        if len(line) > self._effective_width():
            line = render("")
        return self._truncate(line)

    def _bar(self, percent: float) -> str:
        if self._bar_width == 0:
            return ""
        clamped = min(100.0, max(0.0, percent))
        filled = round(clamped / 100.0 * self._bar_width)
        filled_char, empty_char = self._bar_chars
        return f"[{filled_char * filled}{empty_char * (self._bar_width - filled)}] "

    def _effective_width(self) -> int:
        return self._width or shutil.get_terminal_size(fallback=(120, 20)).columns

    def _truncate(self, line: str) -> str:
        width = self._effective_width()
        if width <= 0 or len(line) <= width:
            return line
        if width <= 4:
            return line[:width]
        suffix_len = min(32, max(12, width // 3))
        prefix_len = max(1, width - suffix_len - 3)
        return f"{line[:prefix_len]}...{line[-suffix_len:]}"


class NonTtyProgressCadence:
    def __init__(self, *, item_interval: int = 25, seconds_interval: float = 300.0) -> None:
        self._item_interval = max(1, item_interval)
        self._seconds_interval = max(0.0, seconds_interval)
        self._last_items: int | None = None
        self._last_time: float | None = None

    def should_emit(self, *, now_seconds: float, completed_items: int) -> bool:
        if self._last_items is None or self._last_time is None:
            return True
        if completed_items - self._last_items >= self._item_interval:
            return True
        return now_seconds - self._last_time >= self._seconds_interval

    def mark_emitted(self, *, now_seconds: float, completed_items: int) -> None:
        self._last_items = completed_items
        self._last_time = now_seconds


# Legacy Windows console codepages (cp850/cp1252 when stderr is redirected through
# wrappers that report them) cannot encode the block glyphs; fall back to ASCII there.
def _bar_chars_for_stream(stream: TextIO) -> tuple[str, str]:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        "█░".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return ("#", "-")
    return ("█", "░")


class ProgressReporter:
    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        is_tty: bool | None = None,
        width: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        min_samples: int = 3,
        rolling_window: int = 20,
    ) -> None:
        self._stream = stream or sys.stderr
        self._is_tty = self._stream.isatty() if is_tty is None else is_tty
        self._formatter = ProgressLineFormatter(width=width, bar_chars=_bar_chars_for_stream(self._stream))
        self._clock = clock
        self._min_samples = min_samples
        self._rolling_window = rolling_window
        self._cadence = NonTtyProgressCadence()
        self._estimator: ProgressEstimator | None = None
        self._started_at: float | None = None
        self._last_status_len = 0

    def start(self, plans: Sequence[BenchProgressPlan]) -> None:
        self._estimator = ProgressEstimator(
            tuple(plans),
            min_samples=self._min_samples,
            rolling_window=self._rolling_window,
        )
        self._started_at = self._clock()
        self._stream.write(self._formatter.prerun_total_line(plans) + "\n")
        self._stream.flush()
        if not self._is_tty:
            self._cadence.mark_emitted(now_seconds=self._started_at, completed_items=0)

    def item_complete(self, *, bench: str, item_seconds: float, bench_done: int | None = None) -> None:
        if self._estimator is None or self._started_at is None:
            return
        self._estimator.record_completion(bench, item_seconds)
        elapsed = max(0.0, self._clock() - self._started_at)
        snapshot = self._estimator.snapshot(
            current_bench=bench,
            current_bench_done=bench_done,
            elapsed_seconds=elapsed,
        )
        line = self._formatter.status_line(snapshot)
        if self._is_tty:
            self._write_status_line(line)
            return
        now = self._clock()
        if self._cadence.should_emit(now_seconds=now, completed_items=snapshot.overall_done):
            self._stream.write(line + "\n")
            self._stream.flush()
            self._cadence.mark_emitted(now_seconds=now, completed_items=snapshot.overall_done)

    def clear_line(self) -> None:
        if not self._is_tty or self._last_status_len == 0:
            return
        self._stream.write("\r" + (" " * self._last_status_len) + "\r")
        self._stream.flush()
        self._last_status_len = 0

    def finish(self) -> None:
        if self._is_tty and self._last_status_len:
            self._stream.write("\n")
            self._stream.flush()
            self._last_status_len = 0

    def _write_status_line(self, line: str) -> None:
        padding = max(0, self._last_status_len - len(line))
        self._stream.write("\r" + line + (" " * padding))
        self._stream.flush()
        self._last_status_len = len(line)


def plans_from_bench_counts(counts: Iterable[tuple[str, int]]) -> tuple[BenchProgressPlan, ...]:
    return tuple(BenchProgressPlan(name, count) for name, count in counts if count > 0)


def _format_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
