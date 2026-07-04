from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypedDict


class MonitorMode(StrEnum):
    LOCAL = "local"
    VAST_HOST = "vast-host"


class MonitorSeverity(StrEnum):
    OK = "ok"
    WARN = "warn"
    ABORT = "abort"


class TelemetryParseError(ValueError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class GpuTelemetry:
    uuid: str
    index: int
    name: str
    temperature_c: int
    utilization_pct: int
    memory_used_mib: int
    memory_total_mib: int
    power_draw_w: float | None


@dataclass(frozen=True, slots=True)
class SampleContext:
    label: str
    gpus: tuple[GpuTelemetry, ...]
    free_disk_gb: float | None
    occupancy: str | None = None


@dataclass(frozen=True, slots=True)
class MonitorPolicy:
    mode: MonitorMode
    target_gpu_uuid: str | None = None
    target_name_contains: str | None = None
    protected_gpu_uuid: str | None = None
    protected_min_memory_mib: int | None = None
    expected_available_gpus: int | None = None
    min_free_disk_gb: float = 50.0
    max_target_temp_c: int = 88
    max_protected_temp_c: int = 85


@dataclass(frozen=True, slots=True)
class SafetyBreach:
    severity: MonitorSeverity
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class MonitorDecision:
    severity: MonitorSeverity
    breaches: tuple[SafetyBreach, ...]


class GpuRecord(TypedDict):
    uuid: str
    index: int
    name: str
    temperature_c: int
    utilization_pct: int
    memory_used_mib: int
    memory_total_mib: int
    power_draw_w: float | None


class BreachRecord(TypedDict):
    severity: str
    code: str
    detail: str


class MonitorRecord(TypedDict):
    label: str
    mode: str
    status: str
    occupancy: str | None
    free_disk_gb: float | None
    gpus: list[GpuRecord]
    breaches: list[BreachRecord]


_CSV_FIELD_COUNT: Final = 8
_KIB_PER_GIB: Final = 1024 * 1024


def parse_nvidia_smi_csv(text: str) -> tuple[GpuTelemetry, ...]:
    rows: list[GpuTelemetry] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip().lstrip("\ufeff")
        if line == "":
            continue
        cells = tuple(cell.strip() for cell in line.split(","))
        if len(cells) != _CSV_FIELD_COUNT:
            raise TelemetryParseError(
                f"nvidia-smi row {line_number} has {len(cells)} fields, expected {_CSV_FIELD_COUNT}",
            )
        rows.append(
            GpuTelemetry(
                uuid=_required_text(cells[0], "uuid", line_number),
                index=_int_cell(cells[1], "index", line_number),
                name=_required_text(cells[2], "name", line_number),
                temperature_c=_int_cell(cells[3], "temperature.gpu", line_number),
                utilization_pct=_int_cell(cells[4], "utilization.gpu", line_number),
                memory_used_mib=_int_cell(cells[5], "memory.used", line_number),
                memory_total_mib=_int_cell(cells[6], "memory.total", line_number),
                power_draw_w=_optional_float_cell(cells[7], "power.draw", line_number),
            ),
        )
    if not rows:
        raise TelemetryParseError("nvidia-smi output contained no GPU rows")
    return tuple(rows)


def parse_df_pk(text: str) -> float:
    free_gb_values: list[float] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if line == "" or line.startswith("Filesystem "):
            continue
        cells = line.split()
        if len(cells) < 6:
            raise TelemetryParseError(f"df row {line_number} is not parseable")
        free_gb_values.append(_int_cell(cells[3], "df.Available", line_number) / _KIB_PER_GIB)
    if not free_gb_values:
        raise TelemetryParseError("df output contained no mount rows")
    return min(free_gb_values)


def parse_vast_occupancy_json(text: str) -> str | None:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise TelemetryParseError(f"Vast status JSON is not parseable: {error.msg}") from error
    if isinstance(raw, dict):
        value = raw.get("gpu_occupancy")
        return value if isinstance(value, str) else None
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            value = item.get("gpu_occupancy")
            if isinstance(value, str):
                return value
    return None


def monitor_record(sample: SampleContext, policy: MonitorPolicy, decision: MonitorDecision) -> MonitorRecord:
    return {
        "label": sample.label,
        "mode": policy.mode.value,
        "status": decision.severity.value,
        "occupancy": sample.occupancy,
        "free_disk_gb": sample.free_disk_gb,
        "gpus": [_gpu_record(gpu) for gpu in sample.gpus],
        "breaches": [
            {"severity": breach.severity.value, "code": breach.code, "detail": breach.detail}
            for breach in decision.breaches
        ],
    }


def _gpu_record(gpu: GpuTelemetry) -> GpuRecord:
    return {
        "uuid": gpu.uuid,
        "index": gpu.index,
        "name": gpu.name,
        "temperature_c": gpu.temperature_c,
        "utilization_pct": gpu.utilization_pct,
        "memory_used_mib": gpu.memory_used_mib,
        "memory_total_mib": gpu.memory_total_mib,
        "power_draw_w": gpu.power_draw_w,
    }


def _required_text(value: str, field: str, line_number: int) -> str:
    if value == "":
        raise TelemetryParseError(f"nvidia-smi row {line_number} missing {field}")
    return value


def _int_cell(value: str, field: str, line_number: int) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise TelemetryParseError(f"row {line_number} field {field} is not an integer: {value!r}") from error


def _optional_float_cell(value: str, field: str, line_number: int) -> float | None:
    if value in {"", "N/A", "[N/A]", "Not Supported", "[Not Supported]"}:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise TelemetryParseError(f"row {line_number} field {field} is not a number: {value!r}") from error
