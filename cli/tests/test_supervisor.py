from __future__ import annotations

import json
import sys
from pathlib import Path

from localbench.monitoring import GpuTelemetry, MonitorMode, MonitorPolicy, SampleContext
from localbench.reasoning_registry import GENERIC_THINK_TAGS_32768_PROFILE
from localbench.supervisor import (
    EXIT_WATCHDOG_TIMEOUT,
    SupervisorConfig,
    _watch_worker,
    run_supervised,
)
from localbench.timeout_budgets import derive_timeout_budget


def test_supervisor_runs_worker_and_writes_monitor_record(tmp_path: Path) -> None:
    # Given: a short worker command and a monitor sample provider.
    campaign = tmp_path / "campaign"
    command = [sys.executable, "-c", "print('worker complete')"]

    def sample(policy: MonitorPolicy) -> SampleContext:
        return SampleContext(label="test-campaign", gpus=(), free_disk_gb=128.0)

    # When: the supervisor runs the worker.
    code = run_supervised(
        SupervisorConfig(
            command=command,
            campaign_root=campaign,
            label="test-campaign",
            sample_interval_seconds=0.01,
        ),
        sample_provider=sample,
    )

    # Then: the worker exits cleanly and the existing monitor record schema is used.
    monitor_rows = (campaign / "monitor" / "monitor.jsonl").read_text(encoding="utf-8").splitlines()
    run_log = (campaign / "logs" / "run.log").read_text(encoding="utf-8")
    record = json.loads(monitor_rows[-1])
    assert code == 0
    assert record["label"] == "test-campaign"
    assert record["mode"] == "local"
    assert record["status"] == "ok"
    assert "worker complete" in run_log


def test_supervisor_aborts_worker_when_monitor_decision_aborts(tmp_path: Path) -> None:
    # Given: a long-running worker and a policy-breaching monitor sample.
    campaign = tmp_path / "campaign"
    command = [sys.executable, "-c", "import time; time.sleep(30)"]

    def hot_gpu_sample(policy: MonitorPolicy) -> SampleContext:
        return SampleContext(
            label="test-campaign",
            gpus=(
                GpuTelemetry(
                    uuid="GPU-hot",
                    index=0,
                    name="Test GPU",
                    temperature_c=95,
                    utilization_pct=10,
                    memory_used_mib=1,
                    memory_total_mib=2,
                    power_draw_w=None,
                ),
            ),
            free_disk_gb=128.0,
        )

    # When: the monitor reports an abort-level breach.
    code = run_supervised(
        SupervisorConfig(
            command=command,
            campaign_root=campaign,
            label="test-campaign",
            sample_interval_seconds=0.01,
            policy=MonitorPolicy(mode=MonitorMode.LOCAL, max_target_temp_c=80),
        ),
        sample_provider=hot_gpu_sample,
    )

    # Then: the supervisor terminates the worker and returns the watchdog exit code.
    record = json.loads((campaign / "monitor" / "monitor.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert code == EXIT_WATCHDOG_TIMEOUT
    assert record["status"] == "abort"
    assert any(breach["code"] == "target_gpu_hot" for breach in record["breaches"])


def test_profile_watchdog_waits_through_threshold_then_releases_lease(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0
            self.observed: list[float] = []
            self.increments = iter((5006.0, 1.0))

        def monotonic(self) -> float:
            self.observed.append(self.now)
            return self.now

        def sleep(self, _seconds: float) -> None:
            self.now += next(self.increments)

    class FakeProcess:
        returncode = None

        def poll(self) -> None:
            return None

    class FakeLease:
        def __init__(self) -> None:
            self.events: list[tuple[str, float | None]] = []

        def acquire(self, seconds: float) -> None:
            self.events.append(("acquire", seconds))

        def renew(self, seconds: float) -> None:
            self.events.append(("renew", seconds))

        def release(self) -> None:
            self.events.append(("release", None))

    derived = derive_timeout_budget(
        GENERIC_THINK_TAGS_32768_PROFILE.budget,
        remaining_static_items=1,
        remaining_agentic_tasks=0,
    )
    clock = FakeClock()
    clock.increments = iter((derived.no_progress_seconds, 1.0))
    process = FakeProcess()
    lease = FakeLease()
    terminated: list[float] = []
    monkeypatch.setattr(
        "localbench.supervisor._terminate_worker",
        lambda _process: terminated.append(clock.now),
    )

    # Given: no observable progress and a renewable lease at the deep-profile allowance.
    # When: fake time reaches the threshold exactly and then advances one second beyond it.
    code = _watch_worker(
        process,
        tmp_path / "monitor.jsonl",
        MonitorPolicy(mode=MonitorMode.LOCAL),
        lambda policy: SampleContext(label="test", gpus=(), free_disk_gb=128.0),
        99999.0,
        timeout_budget=derived,
        keepawake_lease=lease,
        clock=clock,
    )

    # Then: equality is allowed, the next instant aborts, and the finite lease is released.
    assert code == EXIT_WATCHDOG_TIMEOUT
    assert terminated == [derived.no_progress_seconds + 1]
    assert derived.no_progress_seconds in clock.observed
    assert lease.events == [
        ("acquire", derived.keepawake_lease_seconds),
        ("release", None),
    ]


def test_progress_renews_keepawake_and_expired_renewal_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "run.status.json"

    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, _seconds: float) -> None:
            self.now = 100.0
            status_path.write_text(json.dumps({"completed_items": 1}), encoding="utf-8")

    class FakeProcess:
        returncode = None

        def poll(self) -> None:
            return None

    class ExpiredLease:
        def __init__(self) -> None:
            self.events: list[str] = []

        def acquire(self, _seconds: float) -> None:
            self.events.append("acquire")

        def renew(self, _seconds: float) -> None:
            self.events.append("renew")
            raise RuntimeError("lease expired")

        def release(self) -> None:
            self.events.append("release")

    lease = ExpiredLease()
    monkeypatch.setattr("localbench.supervisor._terminate_worker", lambda _process: None)
    derived = derive_timeout_budget(
        GENERIC_THINK_TAGS_32768_PROFILE.budget,
        remaining_static_items=1,
        remaining_agentic_tasks=0,
    )

    # Given: a campaign reports progress after acquisition but its lease cannot be renewed.
    # When: the supervisor observes that progress at the real status-file boundary.
    code = _watch_worker(
        FakeProcess(),
        tmp_path / "monitor.jsonl",
        MonitorPolicy(mode=MonitorMode.LOCAL),
        lambda policy: SampleContext(label="test", gpus=(), free_disk_gb=128.0),
        99999.0,
        status_path=status_path,
        timeout_budget=derived,
        keepawake_lease=lease,
        clock=FakeClock(),
    )

    # Then: renewal is attempted and lease failure aborts before continuing unprotected.
    assert code == EXIT_WATCHDOG_TIMEOUT
    assert lease.events == ["acquire", "renew", "release"]
