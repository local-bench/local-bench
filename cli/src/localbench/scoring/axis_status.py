from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final, Literal, NotRequired, TypeAlias, TypedDict

from localbench._types import JsonObject, JsonValue
from localbench.scoring.axes import AXES

AXIS_STATUS_SCHEMA_VERSION: Final = "localbench.axis-status.v1"

AxisMeasurementState: TypeAlias = Literal["measured", "not_measured"]
AxisMeasurementReason: TypeAlias = Literal[
    "ok",
    "sandbox_unavailable",
    "scorer_unavailable",
    "not_run",
]


class AxisStatusParseError(ValueError):
    pass


class AxisMeasurementStatus(TypedDict):
    axis: str
    status: AxisMeasurementState
    reason: AxisMeasurementReason
    detail: NotRequired[str]


class AxisStatusBlock(TypedDict):
    schema_version: str
    axes: dict[str, AxisMeasurementStatus]


def measured_axis(axis: str) -> AxisMeasurementStatus:
    return {"axis": axis, "status": "measured", "reason": "ok"}


def not_measured_axis(
    axis: str,
    *,
    reason: AxisMeasurementReason,
    detail: str | None = None,
) -> AxisMeasurementStatus:
    if reason == "ok":
        raise AxisStatusParseError("not_measured axis requires a non-ok reason")
    status: AxisMeasurementStatus = {
        "axis": axis,
        "status": "not_measured",
        "reason": reason,
    }
    if detail is not None:
        status["detail"] = detail
    return status


def mark_axis_not_measured(
    block: AxisStatusBlock,
    axis: str,
    *,
    reason: AxisMeasurementReason,
    detail: str | None = None,
) -> None:
    block["axes"][axis] = not_measured_axis(axis, reason=reason, detail=detail)


def axis_status_for_benches(
    benches: Iterable[str],
    suite_axes: Mapping[str, JsonValue] | None = None,
) -> AxisStatusBlock:
    bench_names = set(benches)
    axes = {
        axis: (
            measured_axis(axis)
            if bench_names.intersection(axis_benches)
            else not_measured_axis(axis, reason="not_run")
        )
        for axis, axis_benches in _axis_bench_map(suite_axes).items()
    }
    return {"schema_version": AXIS_STATUS_SCHEMA_VERSION, "axes": axes}


def axis_key_for_bench(
    bench: str,
    suite_axes: Mapping[str, JsonValue] | None = None,
) -> str:
    for axis, axis_benches in _axis_bench_map(suite_axes).items():
        if bench in axis_benches:
            return axis
    return bench


def bench_is_measured(
    bench: str,
    axis_status: AxisStatusBlock | None,
    suite_axes: Mapping[str, JsonValue] | None = None,
) -> bool:
    if axis_status is None:
        return True
    axis = axis_key_for_bench(bench, suite_axes)
    status = axis_status["axes"].get(axis)
    if status is None:
        return True
    return status["status"] == "measured"


def serialize_axis_status(status: AxisMeasurementStatus) -> JsonObject:
    serialized: JsonObject = {
        "axis": status["axis"],
        "status": status["status"],
        "reason": status["reason"],
    }
    detail = status.get("detail")
    if detail is not None:
        serialized["detail"] = detail
    return serialized


def parse_axis_status(raw: Mapping[str, JsonValue]) -> AxisMeasurementStatus:
    axis = _required_string(raw, "axis")
    state = _state(raw.get("status"))
    reason = _reason(raw.get("reason"))
    _validate_state_reason(state, reason)
    status: AxisMeasurementStatus = {"axis": axis, "status": state, "reason": reason}
    detail = raw.get("detail")
    if detail is not None:
        if not isinstance(detail, str):
            raise AxisStatusParseError("axis status detail must be a string")
        status["detail"] = detail
    return status


def parse_axis_status_block(raw: Mapping[str, JsonValue]) -> AxisStatusBlock:
    if raw.get("schema_version") != AXIS_STATUS_SCHEMA_VERSION:
        raise AxisStatusParseError(
            f"axis_status schema_version must be {AXIS_STATUS_SCHEMA_VERSION}",
        )
    raw_axes = raw.get("axes")
    if not isinstance(raw_axes, dict):
        raise AxisStatusParseError("axis_status axes must be an object")
    axes: dict[str, AxisMeasurementStatus] = {}
    for key, value in raw_axes.items():
        if not isinstance(value, dict):
            raise AxisStatusParseError(f"axis_status axes.{key} must be an object")
        parsed = parse_axis_status(value)
        if parsed["axis"] != key:
            raise AxisStatusParseError(f"axis_status key {key} does not match axis field")
        axes[key] = parsed
    return {"schema_version": AXIS_STATUS_SCHEMA_VERSION, "axes": axes}


def _axis_bench_map(suite_axes: Mapping[str, JsonValue] | None) -> dict[str, tuple[str, ...]]:
    axis_benches = {
        axis.key: (*axis.benches, *axis.legacy_benches)
        for axis in AXES
    }
    if suite_axes is None:
        return axis_benches
    suite_axis_benches: dict[str, tuple[str, ...]] = {}
    for axis, raw_spec in suite_axes.items():
        if not isinstance(raw_spec, dict):
            continue
        raw_benches = raw_spec.get("benches")
        if not isinstance(raw_benches, list):
            continue
        suite_axis_benches[axis] = tuple(
            bench for bench in raw_benches if isinstance(bench, str)
        )
    suite_bench_names = {
        bench
        for suite_benches in suite_axis_benches.values()
        for bench in suite_benches
    }
    for axis, existing in axis_benches.items():
        axis_benches[axis] = tuple(
            bench for bench in existing if bench not in suite_bench_names
        )
    for axis, suite_benches in suite_axis_benches.items():
        existing = axis_benches.get(axis, ())
        axis_benches[axis] = _dedupe((*existing, *suite_benches))
    return axis_benches


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return tuple(deduped)


def _required_string(raw: Mapping[str, JsonValue], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise AxisStatusParseError(f"axis status {key} must be a string")
    return value


def _state(value: JsonValue | None) -> AxisMeasurementState:
    match value:
        case "measured":
            return "measured"
        case "not_measured":
            return "not_measured"
        case _:
            raise AxisStatusParseError("axis status must be measured or not_measured")


def _reason(value: JsonValue | None) -> AxisMeasurementReason:
    match value:
        case "ok":
            return "ok"
        case "sandbox_unavailable":
            return "sandbox_unavailable"
        case "scorer_unavailable":
            return "scorer_unavailable"
        case "not_run":
            return "not_run"
        case _:
            raise AxisStatusParseError("axis status reason is not supported")


def _validate_state_reason(
    state: AxisMeasurementState,
    reason: AxisMeasurementReason,
) -> None:
    if state == "measured" and reason != "ok":
        raise AxisStatusParseError("measured axis reason must be ok")
    if state == "not_measured" and reason == "ok":
        raise AxisStatusParseError("not_measured axis reason cannot be ok")
