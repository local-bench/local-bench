"""Deterministic season-1 to season-2 editorial bridge artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.scoring.editorial import (
    INDEX_VERSION_V3,
    INDEX_VERSION_V4,
    record_index_version,
)

BRIDGE_SCHEMA_VERSION: Final = "localbench.season_bridge.v1"
DEFAULT_BRIDGE_PATH: Final = (
    Path(__file__).resolve().parents[3] / "runs" / "board" / "season-1-to-2-bridge.json"
)
_FACET_MAPPING: Final[tuple[tuple[str | None, str], ...]] = (
    ("agentic", "agentic"),
    (None, "multi_turn_tool_control"),
    ("tool_calling", "call_formatting"),
)


def build_bridge_entry(
    season_1: Mapping[str, JsonValue],
    season_2: Mapping[str, JsonValue],
) -> JsonObject:
    """Build the one explicit structure permitted to contain a mixed-season pair."""
    if record_index_version(season_1) != INDEX_VERSION_V3:
        raise ValueError("season-1 bridge input must carry index-v3.0")
    if record_index_version(season_2) != INDEX_VERSION_V4:
        raise ValueError("season-2 bridge input must carry index-v4.0")
    identity_1 = _model_identity(season_1)
    identity_2 = _model_identity(season_2)
    if not identity_1 or identity_1 != identity_2:
        raise ValueError("bridge inputs must carry the same non-empty model identity")
    axes_1 = _object(season_1.get("axes"), "season_1.axes")
    axes_2 = _object(season_2.get("axes"), "season_2.axes")
    facets = _object(
        _object(axes_2.get("tool_use"), "season_2.axes.tool_use").get("facets"),
        "season_2.axes.tool_use.facets",
    )
    mappings: list[JsonObject] = []
    for old_axis, facet in _FACET_MAPPING:
        old_score = None if old_axis is None else axes_1.get(old_axis)
        new_score = facets.get(facet)
        mappings.append(
            {
                "season_1_axis": old_axis,
                "season_2_axis": "tool_use",
                "season_2_facet": facet,
                "season_1_score": old_score,
                "season_2_score": new_score,
                "delta": _optional_delta(new_score, old_score),
            },
        )
    common_axes = sorted(
        (set(axes_1) & set(axes_2)) - {"agentic", "tool_calling", "tool_use"}
    )
    per_axis = {
        axis: {
            "season_1_score": axes_1[axis],
            "season_2_score": axes_2[axis],
            "delta": _optional_delta(axes_2[axis], axes_1[axis]),
        }
        for axis in common_axes
    }
    return {
        "model_identity": identity_1,
        "season_1": {
            "index_version": INDEX_VERSION_V3,
            "composite_v3": _score(season_1, ("composite_v3", "composite")),
        },
        "season_2": {
            "index_version": INDEX_VERSION_V4,
            "composite_v4": _score(season_2, ("composite_v4", "composite")),
        },
        "axis_mapping": mappings,
        "per_axis_deltas": per_axis,
    }


def build_bridge_artifact(
    pairs: Sequence[tuple[Mapping[str, JsonValue], Mapping[str, JsonValue]]],
) -> JsonObject:
    entries = [build_bridge_entry(season_1, season_2) for season_1, season_2 in pairs]
    entries.sort(
        key=lambda entry: json.dumps(
            entry["model_identity"], sort_keys=True, separators=(",", ":")
        )
    )
    return {"schema_version": BRIDGE_SCHEMA_VERSION, "entries": entries}


def write_bridge_artifact(
    pairs: Sequence[tuple[Mapping[str, JsonValue], Mapping[str, JsonValue]]],
    *,
    output_path: Path = DEFAULT_BRIDGE_PATH,
) -> JsonObject:
    artifact = build_bridge_artifact(pairs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return artifact


def _model_identity(record: Mapping[str, JsonValue]) -> JsonObject:
    value = record.get("model_identity")
    if isinstance(value, dict):
        return dict(value)
    model = record.get("model")
    if isinstance(model, dict):
        return {
            key: item
            for key in (
                "model_system_key",
                "file_sha256",
                "declared_name",
                "family",
                "quant_label",
            )
            if (item := model.get(key)) is not None
        }
    return {
        key: item
        for key in ("catalog_id", "model_label", "quant_label")
        if (item := record.get(key)) is not None
    }


def _score(record: Mapping[str, JsonValue], fields: Sequence[str]) -> JsonValue:
    for field in fields:
        if field in record:
            return record[field]
    raise ValueError(f"bridge input is missing score field(s): {', '.join(fields)}")


def _optional_delta(new: JsonValue | None, old: JsonValue | None) -> float | None:
    new_point = _point(new)
    old_point = _point(old)
    return None if new_point is None or old_point is None else new_point - old_point


def _point(value: JsonValue | None) -> float | None:
    if isinstance(value, dict):
        value = value.get("point_raw", value.get("point"))
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _object(value: JsonValue | None, context: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value
