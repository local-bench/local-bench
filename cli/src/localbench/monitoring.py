from __future__ import annotations

from typing import assert_never

from localbench.monitor_records import (
    GpuTelemetry,
    MonitorDecision,
    MonitorMode,
    MonitorPolicy,
    MonitorSeverity,
    SafetyBreach,
    SampleContext,
    TelemetryParseError,
    monitor_record,
    parse_df_pk,
    parse_nvidia_smi_csv,
    parse_vast_occupancy_json,
)

__all__ = [
    "MonitorDecision",
    "MonitorMode",
    "MonitorPolicy",
    "MonitorSeverity",
    "SafetyBreach",
    "SampleContext",
    "TelemetryParseError",
    "evaluate_sample",
    "monitor_record",
    "parse_df_pk",
    "parse_nvidia_smi_csv",
    "parse_vast_occupancy_json",
]


def evaluate_sample(sample: SampleContext, policy: MonitorPolicy) -> MonitorDecision:
    breaches: list[SafetyBreach] = []
    _append_common_breaches(sample, policy, breaches)
    match policy.mode:
        case MonitorMode.LOCAL:
            _append_local_breaches(sample, policy, breaches)
        case MonitorMode.VAST_HOST:
            _append_vast_breaches(sample, policy, breaches)
        case unreachable:
            assert_never(unreachable)
    return MonitorDecision(severity=_highest_severity(breaches), breaches=tuple(breaches))


def _append_common_breaches(
    sample: SampleContext,
    policy: MonitorPolicy,
    breaches: list[SafetyBreach],
) -> None:
    if sample.free_disk_gb is not None and sample.free_disk_gb < policy.min_free_disk_gb:
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "disk_floor",
                f"free disk {sample.free_disk_gb:.1f} GB is below {policy.min_free_disk_gb:.1f} GB",
            ),
        )
    if policy.target_gpu_uuid is not None and _gpu_by_uuid(sample.gpus, policy.target_gpu_uuid) is None:
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "target_gpu_missing",
                f"target GPU {policy.target_gpu_uuid} is not present",
            ),
        )
    for gpu in _selected_target_gpus(sample, policy):
        if gpu.temperature_c > policy.max_target_temp_c:
            breaches.append(
                SafetyBreach(
                    MonitorSeverity.ABORT,
                    "target_gpu_hot",
                    f"{gpu.uuid} is {gpu.temperature_c}C, above {policy.max_target_temp_c}C",
                ),
            )


def _append_local_breaches(
    sample: SampleContext,
    policy: MonitorPolicy,
    breaches: list[SafetyBreach],
) -> None:
    if policy.target_name_contains is None:
        return
    needle = policy.target_name_contains.lower()
    if not any(needle in gpu.name.lower() for gpu in sample.gpus):
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "target_name_missing",
                f"no GPU name contains {policy.target_name_contains!r}",
            ),
        )


def _append_vast_breaches(
    sample: SampleContext,
    policy: MonitorPolicy,
    breaches: list[SafetyBreach],
) -> None:
    if sample.occupancy is None:
        breaches.append(SafetyBreach(MonitorSeverity.WARN, "occupancy_unknown", "Vast occupancy was not recorded"))
    if policy.protected_gpu_uuid is None:
        breaches.append(
            SafetyBreach(MonitorSeverity.ABORT, "protected_gpu_missing_policy", "protected renter GPU UUID is required"),
        )
        return
    if policy.target_gpu_uuid == policy.protected_gpu_uuid:
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "protected_gpu_targeted",
                f"benchmark target {policy.target_gpu_uuid} is the protected renter GPU",
            ),
        )
    protected = _gpu_by_uuid(sample.gpus, policy.protected_gpu_uuid)
    if protected is None:
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "protected_gpu_absent",
                f"protected renter GPU {policy.protected_gpu_uuid} is not present",
            ),
        )
        return
    _append_protected_gpu_breaches(protected, policy, breaches)
    _append_available_gpu_breach(sample, policy, breaches)


def _append_protected_gpu_breaches(
    protected: GpuTelemetry,
    policy: MonitorPolicy,
    breaches: list[SafetyBreach],
) -> None:
    if protected.temperature_c > policy.max_protected_temp_c:
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "protected_gpu_hot",
                f"protected renter GPU is {protected.temperature_c}C, above {policy.max_protected_temp_c}C",
            ),
        )
    if (
        policy.protected_min_memory_mib is not None
        and protected.memory_used_mib < policy.protected_min_memory_mib
    ):
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "protected_gpu_memory_low",
                f"protected renter GPU memory {protected.memory_used_mib} MiB is below "
                f"{policy.protected_min_memory_mib} MiB",
            ),
        )


def _append_available_gpu_breach(
    sample: SampleContext,
    policy: MonitorPolicy,
    breaches: list[SafetyBreach],
) -> None:
    if policy.expected_available_gpus is None or policy.protected_gpu_uuid is None:
        return
    available = tuple(gpu for gpu in sample.gpus if gpu.uuid != policy.protected_gpu_uuid)
    if len(available) != policy.expected_available_gpus:
        breaches.append(
            SafetyBreach(
                MonitorSeverity.ABORT,
                "available_gpu_count",
                f"available GPU count {len(available)} does not match expected {policy.expected_available_gpus}",
            ),
        )


def _selected_target_gpus(sample: SampleContext, policy: MonitorPolicy) -> tuple[GpuTelemetry, ...]:
    if policy.target_gpu_uuid is not None:
        gpu = _gpu_by_uuid(sample.gpus, policy.target_gpu_uuid)
        return () if gpu is None else (gpu,)
    if policy.target_name_contains is None:
        return sample.gpus
    needle = policy.target_name_contains.lower()
    return tuple(gpu for gpu in sample.gpus if needle in gpu.name.lower())


def _gpu_by_uuid(gpus: tuple[GpuTelemetry, ...], uuid: str) -> GpuTelemetry | None:
    for gpu in gpus:
        if gpu.uuid == uuid:
            return gpu
    return None


def _highest_severity(breaches: list[SafetyBreach]) -> MonitorSeverity:
    severity = MonitorSeverity.OK
    for breach in breaches:
        if breach.severity is MonitorSeverity.ABORT:
            return MonitorSeverity.ABORT
        if breach.severity is MonitorSeverity.WARN:
            severity = MonitorSeverity.WARN
    return severity
