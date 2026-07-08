from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from localbench.exit_codes import EXIT_USER_INTERRUPTED, EXIT_WATCHDOG_TIMEOUT
from localbench.progress import BenchProgressPlan, ProgressReporter
from localbench.monitoring import (
    MonitorDecision,
    MonitorMode,
    MonitorPolicy,
    MonitorSeverity,
    SampleContext,
    evaluate_sample,
    monitor_record,
)

SampleProvider = Callable[[MonitorPolicy], SampleContext]


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    command: Sequence[str]
    campaign_root: Path
    label: str
    sample_interval_seconds: float = 30.0
    policy: MonitorPolicy | None = None
    progress_plans: Sequence[BenchProgressPlan] = ()


def run_supervised(config: SupervisorConfig, sample_provider: SampleProvider | None = None) -> int:
    paths = _supervisor_paths(config.campaign_root)
    paths.monitor_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    policy = config.policy or MonitorPolicy(mode=MonitorMode.LOCAL, min_free_disk_gb=1.0)
    provider = sample_provider or _default_sample_provider(config.label, config.campaign_root)
    progress = ProgressReporter() if config.progress_plans else None
    if progress is not None:
        progress.start(config.progress_plans)
    with (paths.logs_dir / "run.log").open("ab") as log:
        process = _start_worker(config.command, log)
        try:
            return _watch_worker(
                process,
                paths.monitor_log,
                policy,
                provider,
                config.sample_interval_seconds,
                status_path=config.campaign_root / "run.status.json",
                progress_reporter=progress,
            )
        except KeyboardInterrupt:
            if progress is not None:
                progress.clear_line()
            _terminate_worker(process)
            return EXIT_USER_INTERRUPTED
        finally:
            if progress is not None:
                progress.finish()


@dataclass(frozen=True, slots=True)
class _SupervisorPaths:
    monitor_dir: Path
    logs_dir: Path
    monitor_log: Path


def _supervisor_paths(campaign_root: Path) -> _SupervisorPaths:
    monitor_dir = campaign_root / "monitor"
    return _SupervisorPaths(
        monitor_dir=monitor_dir,
        logs_dir=campaign_root / "logs",
        monitor_log=monitor_dir / "monitor.jsonl",
    )


def _start_worker(command: Sequence[str], log) -> subprocess.Popen[bytes]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    start_new_session = sys.platform != "win32"
    return subprocess.Popen(
        list(command),
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        start_new_session=start_new_session,
        shell=False,
    )


def _watch_worker(
    process: subprocess.Popen[bytes],
    monitor_log: Path,
    policy: MonitorPolicy,
    sample_provider: SampleProvider,
    interval_seconds: float,
    *,
    status_path: Path | None = None,
    progress_reporter: ProgressReporter | None = None,
) -> int:
    next_sample_at = 0.0
    last_completed = 0
    last_completion_at = time.monotonic()
    last_bench: str | None = None
    while process.poll() is None:
        now = time.monotonic()
        if now >= next_sample_at:
            decision = _append_monitor_sample(monitor_log, sample_provider(policy), policy)
            if decision.severity is MonitorSeverity.ABORT:
                _terminate_worker(process)
                return EXIT_WATCHDOG_TIMEOUT
            next_sample_at = now + max(interval_seconds, 0.1)
        if status_path is not None and progress_reporter is not None:
            last_completed, last_completion_at, last_bench = _mirror_progress_status(
                status_path,
                progress_reporter,
                last_completed=last_completed,
                last_completion_at=last_completion_at,
                last_bench=last_bench,
            )
        time.sleep(0.05)
    if status_path is not None and progress_reporter is not None:
        _mirror_progress_status(
            status_path,
            progress_reporter,
            last_completed=last_completed,
            last_completion_at=last_completion_at,
            last_bench=last_bench,
        )
    _append_monitor_sample(monitor_log, sample_provider(policy), policy)
    return process.returncode or 0


def _mirror_progress_status(
    status_path: Path,
    progress_reporter: ProgressReporter,
    *,
    last_completed: int,
    last_completion_at: float,
    last_bench: str | None,
) -> tuple[int, float, str | None]:
    status = _read_status(status_path)
    bench = status.get("current_bench")
    current_bench = bench if isinstance(bench, str) else last_bench
    completed = status.get("completed_items")
    if not isinstance(completed, int) or completed <= last_completed:
        return last_completed, last_completion_at, current_bench
    if current_bench is None:
        return completed, time.monotonic(), last_bench
    now = time.monotonic()
    delta_items = max(1, completed - last_completed)
    item_seconds = max(0.0, now - last_completion_at) / delta_items
    for _ in range(delta_items):
        progress_reporter.item_complete(bench=current_bench, item_seconds=item_seconds)
    return completed, now, current_bench


def _read_status(path: Path) -> dict[str, object]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _append_monitor_sample(
    monitor_log: Path,
    sample: SampleContext,
    policy: MonitorPolicy,
) -> MonitorDecision:
    decision = evaluate_sample(sample, policy)
    with monitor_log.open("a", encoding="utf-8") as handle:
        json.dump(monitor_record(sample, policy, decision), handle, sort_keys=True)
        handle.write("\n")
    return decision


def _default_sample_provider(label: str, disk_path: Path) -> SampleProvider:
    def sample(policy: MonitorPolicy) -> SampleContext:
        usage = shutil.disk_usage(disk_path if disk_path.exists() else Path.cwd())
        return SampleContext(
            label=label,
            gpus=(),
            free_disk_gb=usage.free / (1024**3),
        )

    return sample


def _terminate_worker(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
