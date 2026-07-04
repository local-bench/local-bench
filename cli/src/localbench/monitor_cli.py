from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final, assert_never

from localbench.monitoring import (
    MonitorDecision,
    MonitorMode,
    MonitorPolicy,
    MonitorSeverity,
    SampleContext,
    TelemetryParseError,
    evaluate_sample,
    monitor_record,
    parse_df_pk,
    parse_nvidia_smi_csv,
    parse_vast_occupancy_json,
)

_NVIDIA_QUERY: Final[tuple[str, ...]] = (
    "nvidia-smi",
    "--query-gpu=uuid,index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
    "--format=csv,noheader,nounits",
)
_REMOTE_DF_COMMAND: Final = "df -Pk / /var/lib/docker /workspace 2>/dev/null || df -Pk / /var/lib/docker"


class MonitorCollectionError(RuntimeError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (MonitorCollectionError, TelemetryParseError, OSError) as error:
        print(f"error {error}")
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localbench-monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_common_args(subparsers.add_parser("local", help="monitor a local benchmark GPU"))
    vast = subparsers.add_parser("vast-host", help="monitor a Michael-owned Vast host without renter access")
    _add_common_args(vast)
    vast.add_argument("--protected-gpu-uuid", required=True)
    vast.add_argument("--protected-min-memory-mib", type=int)
    vast.add_argument("--expected-available-gpus", type=int, default=1)
    vast.add_argument("--occupancy")
    vast.add_argument("--machine-id", type=int)
    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--nvidia-smi-file", type=Path)
    parser.add_argument("--df-file", type=Path)
    parser.add_argument("--ssh-target")
    parser.add_argument("--disk-path", type=Path, default=Path.cwd())
    parser.add_argument("--target-gpu-uuid")
    parser.add_argument("--target-name-contains")
    parser.add_argument("--min-free-disk-gb", type=float, default=50.0)
    parser.add_argument("--max-target-temp-c", type=int, default=88)
    parser.add_argument("--max-protected-temp-c", type=int, default=85)


def _run(args: argparse.Namespace) -> int:
    policy = _policy(args)
    while True:
        sample = _collect_sample(args, policy.mode)
        decision = evaluate_sample(sample, policy)
        _append_record(args.out, sample, policy, decision)
        _print_decision(sample, decision)
        match decision.severity:
            case MonitorSeverity.OK | MonitorSeverity.WARN:
                if args.once:
                    return 0 if decision.severity is MonitorSeverity.OK else 1
            case MonitorSeverity.ABORT:
                return 2
            case unreachable:
                assert_never(unreachable)
        time.sleep(args.interval_seconds)


def _policy(args: argparse.Namespace) -> MonitorPolicy:
    mode = _mode(args.command)
    match mode:
        case MonitorMode.LOCAL:
            return MonitorPolicy(
                mode=mode,
                target_gpu_uuid=args.target_gpu_uuid,
                target_name_contains=args.target_name_contains,
                min_free_disk_gb=args.min_free_disk_gb,
                max_target_temp_c=args.max_target_temp_c,
            )
        case MonitorMode.VAST_HOST:
            return MonitorPolicy(
                mode=mode,
                target_gpu_uuid=args.target_gpu_uuid,
                target_name_contains=args.target_name_contains,
                protected_gpu_uuid=args.protected_gpu_uuid,
                protected_min_memory_mib=args.protected_min_memory_mib,
                expected_available_gpus=args.expected_available_gpus,
                min_free_disk_gb=args.min_free_disk_gb,
                max_target_temp_c=args.max_target_temp_c,
                max_protected_temp_c=args.max_protected_temp_c,
            )
        case unreachable:
            assert_never(unreachable)


def _mode(command: str) -> MonitorMode:
    match command:
        case "local":
            return MonitorMode.LOCAL
        case "vast-host":
            return MonitorMode.VAST_HOST
        case _:
            raise MonitorCollectionError(f"unsupported monitor command {command!r}")


def _collect_sample(args: argparse.Namespace, mode: MonitorMode) -> SampleContext:
    gpus = parse_nvidia_smi_csv(_nvidia_smi_text(args))
    free_disk_gb = _free_disk_gb(args, mode)
    return SampleContext(
        label=args.label,
        gpus=gpus,
        free_disk_gb=free_disk_gb,
        occupancy=_occupancy(args, mode),
    )


def _nvidia_smi_text(args: argparse.Namespace) -> str:
    if args.nvidia_smi_file is not None:
        return args.nvidia_smi_file.read_text(encoding="utf-8")
    if args.ssh_target:
        return _run_command(_ssh_command(args.ssh_target, " ".join(_NVIDIA_QUERY)))
    return _run_command(_NVIDIA_QUERY)


def _free_disk_gb(args: argparse.Namespace, mode: MonitorMode) -> float:
    if args.df_file is not None:
        return parse_df_pk(args.df_file.read_text(encoding="utf-8"))
    match mode:
        case MonitorMode.LOCAL:
            usage = shutil.disk_usage(args.disk_path)
            return usage.free / (1024**3)
        case MonitorMode.VAST_HOST:
            if not args.ssh_target:
                return shutil.disk_usage(args.disk_path).free / (1024**3)
            return parse_df_pk(_run_command(_ssh_command(args.ssh_target, _REMOTE_DF_COMMAND)))
        case unreachable:
            assert_never(unreachable)


def _occupancy(args: argparse.Namespace, mode: MonitorMode) -> str | None:
    if not hasattr(args, "occupancy"):
        return None
    if args.occupancy is not None:
        return args.occupancy
    match mode:
        case MonitorMode.LOCAL:
            return None
        case MonitorMode.VAST_HOST:
            if args.machine_id is None:
                return None
            return parse_vast_occupancy_json(_vast_status_text(args))
        case unreachable:
            assert_never(unreachable)


def _vast_status_text(args: argparse.Namespace) -> str:
    machine_id = str(args.machine_id)
    if args.ssh_target:
        return _run_command(
            _ssh_command(args.ssh_target, f"~/.local/bin/vastai show machine {machine_id} --raw"),
        )
    return _run_command(("vastai", "show", "machine", machine_id, "--raw"))


def _ssh_command(target: str, remote_command: str) -> tuple[str, ...]:
    return ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", target, remote_command)


def _run_command(command: tuple[str, ...]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise MonitorCollectionError(f"{command[0]} exited {completed.returncode}: {stderr}")
    return completed.stdout


def _append_record(
    out: Path,
    sample: SampleContext,
    policy: MonitorPolicy,
    decision: MonitorDecision,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as handle:
        json.dump(monitor_record(sample, policy, decision), handle, sort_keys=True)
        handle.write("\n")


def _print_decision(sample: SampleContext, decision: MonitorDecision) -> None:
    print(f"{sample.label} {decision.severity.value} gpus={len(sample.gpus)}")
    for breach in decision.breaches:
        print(f"{breach.severity.value} {breach.code}: {breach.detail}")


if __name__ == "__main__":
    sys.exit(main())
