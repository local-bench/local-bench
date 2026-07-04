from __future__ import annotations

import json
import sys
from pathlib import Path

from localbench.monitoring import GpuTelemetry, MonitorMode, MonitorPolicy, SampleContext
from localbench.supervisor import EXIT_WATCHDOG_TIMEOUT, SupervisorConfig, run_supervised


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
