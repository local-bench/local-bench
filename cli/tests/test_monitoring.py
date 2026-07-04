from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.monitor_cli import main as monitor_main
from localbench.monitoring import (
    MonitorMode,
    MonitorPolicy,
    MonitorSeverity,
    SampleContext,
    evaluate_sample,
    parse_df_pk,
    parse_nvidia_smi_csv,
    parse_vast_occupancy_json,
)


def test_parse_nvidia_smi_csv_when_query_output_has_two_gpus() -> None:
    # Given: nvidia-smi CSV from the fixed monitor query.
    text = "\n".join(
        [
            "GPU-5090, 0, NVIDIA GeForce RTX 5090, 54, 82, 24576, 32768, 312.50",
            "GPU-6000, 1, NVIDIA RTX PRO 6000 Blackwell, 63, 41, 96145, 98304, 255.00",
        ],
    )

    # When: parsing the sample.
    gpus = parse_nvidia_smi_csv(text)

    # Then: every field needed by the guard is preserved.
    assert len(gpus) == 2
    assert gpus[0].uuid == "GPU-5090"
    assert gpus[0].temperature_c == 54
    assert gpus[0].memory_total_mib == 32768
    assert gpus[1].name == "NVIDIA RTX PRO 6000 Blackwell"
    assert gpus[1].power_draw_w == 255.0


def test_parse_nvidia_smi_csv_when_captured_file_has_utf8_bom() -> None:
    # Given: a PowerShell-captured sample with a leading UTF-8 BOM.
    text = "\ufeffGPU-5090, 0, NVIDIA GeForce RTX 5090, 54, 82, 24576, 32768, 312.50"

    # When: parsing the sample.
    gpus = parse_nvidia_smi_csv(text)

    # Then: the UUID is clean enough to compare against live guard arguments.
    assert gpus[0].uuid == "GPU-5090"


def test_vast_policy_aborts_when_benchmark_gpu_overlaps_protected_renter() -> None:
    # Given: a Vast host policy where the proposed benchmark GPU is also protected.
    gpus = parse_nvidia_smi_csv(
        "GPU-renter, 1, NVIDIA RTX PRO 6000 Blackwell, 62, 42, 96145, 98304, 255.00",
    )
    sample = SampleContext(
        label="vast-host",
        gpus=gpus,
        free_disk_gb=128.0,
        occupancy="x D",
    )
    policy = MonitorPolicy(
        mode=MonitorMode.VAST_HOST,
        target_gpu_uuid="GPU-renter",
        protected_gpu_uuid="GPU-renter",
        protected_min_memory_mib=90_000,
    )

    # When: evaluating the guard.
    decision = evaluate_sample(sample, policy)

    # Then: the monitor fails closed before any benchmark can use the rented GPU.
    assert decision.severity is MonitorSeverity.ABORT
    assert any(breach.code == "protected_gpu_targeted" for breach in decision.breaches)


def test_vast_policy_passes_when_one_free_gpu_and_renter_stays_healthy() -> None:
    # Given: one free benchmark GPU plus one protected renter GPU.
    gpus = parse_nvidia_smi_csv(
        "\n".join(
            [
                "GPU-free, 0, NVIDIA RTX PRO 6000 Blackwell, 48, 0, 0, 98304, 38.00",
                "GPU-renter, 1, NVIDIA RTX PRO 6000 Blackwell, 64, 40, 96145, 98304, 260.00",
            ],
        ),
    )
    sample = SampleContext(
        label="vast-host",
        gpus=gpus,
        free_disk_gb=140.0,
        occupancy="x D",
    )
    policy = MonitorPolicy(
        mode=MonitorMode.VAST_HOST,
        target_gpu_uuid="GPU-free",
        protected_gpu_uuid="GPU-renter",
        protected_min_memory_mib=90_000,
        expected_available_gpus=1,
    )

    # When: evaluating the guard.
    decision = evaluate_sample(sample, policy)

    # Then: the sample is safe to continue monitoring.
    assert decision.severity is MonitorSeverity.OK
    assert decision.breaches == ()


def test_monitor_cli_once_writes_jsonl_record_from_captured_local_sample(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: captured RTX 5090 telemetry and enough local disk.
    nvidia_sample = tmp_path / "nvidia.csv"
    nvidia_sample.write_text(
        "GPU-5090, 0, NVIDIA GeForce RTX 5090, 51, 72, 18432, 32768, 305.00\n",
        encoding="utf-8",
    )
    out = tmp_path / "monitor.jsonl"

    # When: running the monitor once against the captured sample.
    code = monitor_main(
        [
            "local",
            "--label",
            "rtx-5090",
            "--target-name-contains",
            "RTX 5090",
            "--nvidia-smi-file",
            str(nvidia_sample),
            "--disk-path",
            str(tmp_path),
            "--out",
            str(out),
            "--once",
        ],
    )

    # Then: it exits cleanly and appends one JSONL safety record.
    stdout = capsys.readouterr().out
    record = json.loads(out.read_text(encoding="utf-8").strip())
    assert code == 0
    assert "ok" in stdout
    assert record["label"] == "rtx-5090"
    assert record["status"] == "ok"
    assert record["gpus"][0]["uuid"] == "GPU-5090"


def test_monitor_cli_vast_once_exits_abort_on_hot_renter_gpu(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: captured Vast host telemetry with the protected renter GPU above the guard limit.
    nvidia_sample = tmp_path / "nvidia.csv"
    nvidia_sample.write_text(
        "\n".join(
            [
                "GPU-free, 0, NVIDIA RTX PRO 6000 Blackwell, 48, 0, 0, 98304, 38.00",
                "GPU-renter, 1, NVIDIA RTX PRO 6000 Blackwell, 88, 55, 96145, 98304, 290.00",
            ],
        ),
        encoding="utf-8",
    )
    df_sample = tmp_path / "df.txt"
    df_sample.write_text(
        "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
        "/dev/root 200000000 40000000 160000000 20% /\n",
        encoding="utf-8",
    )
    out = tmp_path / "vast-monitor.jsonl"

    # When: running the Vast guard once.
    code = monitor_main(
        [
            "vast-host",
            "--label",
            "vast-rtx6000-pro",
            "--target-gpu-uuid",
            "GPU-free",
            "--protected-gpu-uuid",
            "GPU-renter",
            "--protected-min-memory-mib",
            "90000",
            "--nvidia-smi-file",
            str(nvidia_sample),
            "--df-file",
            str(df_sample),
            "--out",
            str(out),
            "--once",
        ],
    )

    # Then: the guard emits a failing record that a wrapper can use to abort the campaign.
    stdout = capsys.readouterr().out
    record = json.loads(out.read_text(encoding="utf-8").strip())
    assert code == 2
    assert "abort" in stdout
    assert record["status"] == "abort"
    assert any(breach["code"] == "protected_gpu_hot" for breach in record["breaches"])


def test_parse_df_pk_uses_lowest_reported_mount_free_space() -> None:
    # Given: df output from several monitored host mounts.
    text = (
        "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
        "/dev/root 200000000 40000000 160000000 20% /\n"
        "/dev/docker 90000000 85000000 5000000 95% /var/lib/docker\n"
    )

    # When: parsing disk headroom.
    free_gb = parse_df_pk(text)

    # Then: the guard uses the tightest disk floor.
    assert free_gb == pytest.approx(4.768, rel=0.001)


def test_parse_vast_occupancy_json_when_machine_status_is_list_shaped() -> None:
    # Given: read-only Vast CLI JSON containing occupancy metadata.
    text = json.dumps([{"current_rentals_running": 1, "gpu_occupancy": "x D "}])

    # When: parsing occupancy for the monitor record.
    occupancy = parse_vast_occupancy_json(text)

    # Then: the live occupancy string is preserved for the safety log.
    assert occupancy == "x D "
