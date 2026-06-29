from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._requests import utc_now
from localbench._suite import RenderedBench
from localbench._types import JsonObject
from localbench.campaign_records import CampaignConfig, campaign_record
from localbench.persistence import atomic_write_json

STATUS_SCHEMA_VERSION: Final = "localbench-run-status-v1"


@dataclass(frozen=True, slots=True)
class CampaignPaths:
    root: Path
    final_run: Path
    benchmarks_dir: Path
    monitor_dir: Path
    logs_dir: Path


@dataclass(frozen=True, slots=True)
class StatusUpdate:
    state: str
    current_bench: str | None
    current_item_index: int | None
    current_item_id: str | None
    completed_items: int
    total_items: int
    started_at: str
    exit_code: int | None = None
    failure_reason: str | None = None


def campaign_paths(output_path: Path) -> CampaignPaths:
    root = output_path.parent
    return CampaignPaths(
        root=root,
        final_run=output_path,
        benchmarks_dir=root / "benchmarks",
        monitor_dir=root / "monitor",
        logs_dir=root / "logs",
    )


def initialize_campaign(
    paths: CampaignPaths,
    config: CampaignConfig,
    suite: JsonObject,
    suite_dir: Path,
    benches: list[RenderedBench],
    *,
    started_at: str,
) -> JsonObject:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.benchmarks_dir.mkdir(parents=True, exist_ok=True)
    paths.monitor_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    _write_lock(paths.root / "campaign.lock", started_at)
    campaign = campaign_record(config, suite, suite_dir, benches, started_at=started_at)
    campaign_path = paths.root / "campaign.json"
    if not campaign_path.exists():
        atomic_write_json(campaign, campaign_path)
    write_status(
        paths,
        StatusUpdate(
            state="running",
            current_bench=None,
            current_item_index=None,
            current_item_id=None,
            completed_items=0,
            total_items=_total_items(benches),
            started_at=started_at,
        ),
    )
    return campaign


def write_status(paths: CampaignPaths, update: StatusUpdate) -> None:
    status: JsonObject = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "state": update.state,
        "current_bench": update.current_bench,
        "current_item_index": update.current_item_index,
        "current_item_id": update.current_item_id,
        "completed_items": update.completed_items,
        "total_items": update.total_items,
        "started_at": update.started_at,
        "updated_at": utc_now(),
        "exit_code": update.exit_code,
        "failure_reason": update.failure_reason,
    }
    atomic_write_json(status, paths.root / "run.status.json")


def _total_items(benches: list[RenderedBench]) -> int:
    return sum(len(bench.benchmark_items) for bench in benches)


def _write_lock(path: Path, started_at: str) -> None:
    lock: JsonObject = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started_at": started_at,
    }
    atomic_write_json(lock, path)

