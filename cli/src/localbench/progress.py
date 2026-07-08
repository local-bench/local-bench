from __future__ import annotations

import os
import re
import shutil
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import TextIO

from localbench.scoring.axes import AXES


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
    # (bench name, done, total) in plan order — drives the per-bench segmented bar.
    bench_progress: tuple[tuple[str, int, int], ...] = field(default=())


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
        bench_progress = tuple(
            (
                plan.name,
                bench_done if plan.name == current_bench else self._done[plan.name],
                self._totals[plan.name],
            )
            for plan in self._plans
        )
        return ProgressSnapshot(
            current_bench=current_bench,
            current_bench_done=bench_done,
            current_bench_total=bench_total,
            overall_done=overall_done,
            overall_total=overall_total,
            percent=percent,
            elapsed_seconds=max(0.0, elapsed_seconds),
            eta_seconds=self.eta_seconds(),
            bench_progress=bench_progress,
        )

    def _sample_count(self) -> int:
        return sum(len(samples) for samples in self._samples.values())

    def _global_average(self) -> float | None:
        values = [value for samples in self._samples.values() for value in samples]
        if not values:
            return None
        return sum(values) / len(values)


# Mirrors AXIS_CONFIG colors in web/lib/axis-config.ts (keep in sync) so the CLI's
# per-bench bar segments match the leaderboard's axis palette.
_AXIS_RGB: dict[str, tuple[int, int, int]] = {
    "agentic": (0x3F, 0xD0, 0xD4),
    "knowledge": (0x7C, 0x9F, 0xFF),
    "instruction": (0xB3, 0x88, 0xFF),
    "tool_calling": (0xFF, 0xB6, 0x27),
    "coding": (0xFF, 0x5F, 0xA8),
    "math": (0x36, 0xE0, 0xB0),
}
_DEFAULT_RGB: tuple[int, int, int] = (0xA0, 0xA0, 0xA0)

_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _bench_rgb() -> dict[str, tuple[int, int, int]]:
    colors: dict[str, tuple[int, int, int]] = {}
    for axis in AXES:
        rgb = _AXIS_RGB.get(axis.web_key, _DEFAULT_RGB)
        for bench in (*axis.benches, *axis.legacy_benches):
            colors[bench] = rgb
    return colors


def _visible_len(line: str) -> int:
    return len(_ANSI_PATTERN.sub("", line))


class ProgressLineFormatter:
    def __init__(
        self,
        *,
        width: int | None = None,
        bar_width: int = 20,
        bar_chars: tuple[str, str] = ("█", "░"),
        use_color: bool = False,
    ) -> None:
        self._width = width
        self._bar_width = max(0, bar_width)
        self._bar_chars = bar_chars
        self._use_color = use_color
        self._bench_rgb = _bench_rgb()

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

        bar = (
            self._segmented_bar(snapshot.bench_progress)
            if snapshot.bench_progress
            else self._bar(snapshot.percent)
        )
        line = render(bar)
        # On narrow consoles the bar is the expendable part: drop it before letting
        # _truncate cut counts/ETA out of the middle of the line. Width checks use the
        # visible length — ANSI color codes take no columns.
        if _visible_len(line) > self._effective_width():
            line = render("")
        return self._truncate(line)

    def _bar(self, percent: float) -> str:
        if self._bar_width == 0:
            return ""
        clamped = min(100.0, max(0.0, percent))
        filled = round(clamped / 100.0 * self._bar_width)
        filled_char, empty_char = self._bar_chars
        return f"[{filled_char * filled}{empty_char * (self._bar_width - filled)}] "

    def _segmented_bar(self, bench_progress: tuple[tuple[str, int, int], ...]) -> str:
        if self._bar_width == 0:
            return ""
        widths = _segment_widths([total for _, _, total in bench_progress], self._bar_width)
        filled_char, empty_char = self._bar_chars
        parts: list[str] = []
        for (bench, done, total), segment_width in zip(bench_progress, widths):
            if segment_width == 0:
                continue
            ratio = 0.0 if total <= 0 else min(1.0, max(0.0, done / total))
            filled = round(ratio * segment_width)
            segment = f"{filled_char * filled}{empty_char * (segment_width - filled)}"
            parts.append(self._colorize(segment, bench))
        return f"[{''.join(parts)}] "

    def _colorize(self, segment: str, bench: str) -> str:
        if not self._use_color or segment == "":
            return segment
        r, g, b = self._bench_rgb.get(bench, _DEFAULT_RGB)
        return f"\x1b[38;2;{r};{g};{b}m{segment}\x1b[0m"

    def _effective_width(self) -> int:
        return self._width or shutil.get_terminal_size(fallback=(120, 20)).columns

    def _truncate(self, line: str) -> str:
        width = self._effective_width()
        if width <= 0 or _visible_len(line) <= width:
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


def _color_enabled(stream: TextIO, is_tty: bool) -> bool:
    if not is_tty or os.environ.get("NO_COLOR"):
        return False
    if sys.platform != "win32":
        return True
    return _enable_windows_vt(stream)


# Classic conhost needs ENABLE_VIRTUAL_TERMINAL_PROCESSING switched on before ANSI
# color sequences render as color instead of literal escape text.
def _enable_windows_vt(stream: TextIO) -> bool:
    try:
        import ctypes
        import msvcrt

        handle = msvcrt.get_osfhandle(stream.fileno())
        kernel32 = ctypes.windll.kernel32
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (OSError, ValueError, AttributeError, ImportError):
        return False


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
        self._formatter = ProgressLineFormatter(
            width=width,
            bar_chars=_bar_chars_for_stream(self._stream),
            use_color=_color_enabled(self._stream, self._is_tty),
        )
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
        visible = _visible_len(line)
        padding = max(0, self._last_status_len - visible)
        self._stream.write("\r" + line + (" " * padding))
        self._stream.flush()
        self._last_status_len = visible


def plans_from_bench_counts(counts: Iterable[tuple[str, int]]) -> tuple[BenchProgressPlan, ...]:
    return tuple(BenchProgressPlan(name, count) for name, count in counts if count > 0)


# Largest-remainder allocation: every bench with items gets at least one cell so tiny
# benches stay visible, and the widths always sum exactly to the bar width.
def _segment_widths(totals: Sequence[int], bar_width: int) -> list[int]:
    clamped = [max(0, total) for total in totals]
    grand_total = sum(clamped)
    if grand_total == 0 or bar_width == 0:
        return [0 for _ in clamped]
    quotas = [total / grand_total * bar_width for total in clamped]
    widths = [max(1, int(quota)) if total > 0 else 0 for quota, total in zip(quotas, clamped)]
    while sum(widths) > bar_width:
        candidates = [index for index, width in enumerate(widths) if width > 1]
        if not candidates:
            break
        shrink = max(candidates, key=lambda index: widths[index] - quotas[index])
        widths[shrink] -= 1
    remainders = sorted(
        (index for index, total in enumerate(clamped) if total > 0),
        key=lambda index: quotas[index] - widths[index],
        reverse=True,
    )
    cursor = 0
    while sum(widths) < bar_width and remainders:
        widths[remainders[cursor % len(remainders)]] += 1
        cursor += 1
    return widths


def _format_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
