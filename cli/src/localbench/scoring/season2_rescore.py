"""Post-hoc season-2 axis math for existing run records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.scoring import bootstrap, score_interval
from localbench.scoring.axes import (
    axis_for_key,
    headline_web_axes,
    web_composite_weights,
)
from localbench.scoring.board_scoring import _axes_and_samples, _strict_composite
from localbench.scoring.board_support import (
    object_or_empty,
    object_value,
    objects_value,
)
from localbench.scoring.editorial import (
    INDEX_VERSION_V4,
    SEASON_2_COVERAGE_PROFILE_ID,
    record_index_version,
)
from localbench.scoring.scorecard import scorecard_identity
from localbench.scoring.signed_score import signed_score
from localbench.suite_release import coverage_profile_for_id

SEASON_2_RESCORE_SCHEMA_VERSION: Final = "localbench.season2_rescore.v1"


def rescore_record_season2(
    record: Mapping[str, JsonValue],
    *,
    bootstrap_iters: int = 10_000,
) -> JsonObject:
    """Recompute axes and a strict season-2 composite from carried item verdicts.

    Missing Agentic (`tool_use`) facet benches mechanically omit the macro-axis through the
    registry's existing fail-closed facet materialization.  Consequently the
    strict composite is ``None`` when any season-2 headline axis is absent.
    """
    if bootstrap_iters <= 0:
        raise ValueError("bootstrap_iters must be positive")
    profile = coverage_profile_for_id(SEASON_2_COVERAGE_PROFILE_ID)
    benches = object_value(record.get("benches"), "record.benches")
    items = objects_value(record.get("items"), "record.items")
    conformance = object_or_empty(record.get("conformance"))
    axes, samples = _axes_and_samples(
        benches,
        items,
        object_or_empty(conformance.get("per_bench")),
        bootstrap_iters,
        pad_missing_items=True,
    )
    _attach_tool_use_facets(axes, samples, bootstrap_iters=bootstrap_iters)
    required_axes = frozenset(headline_web_axes())
    composite_v4 = _strict_composite(
        samples,
        axes,
        bootstrap_iters,
        required_axes=required_axes,
        weights=web_composite_weights(),
    )
    scorecard = scorecard_identity()
    return {
        "schema_version": SEASON_2_RESCORE_SCHEMA_VERSION,
        "model_identity": _model_identity(record),
        "source_index_version": record_index_version(record),
        "index_version": INDEX_VERSION_V4,
        "coverage_profile_id": profile.profile_id,
        "scorecard_id": scorecard["scorecard_id"],
        "registry_digest": scorecard["registry_digest"],
        "axes": axes,
        "missing_headline_axes": sorted(required_axes - set(axes)),
        "composite_v4": composite_v4,
    }


def _attach_tool_use_facets(
    axes: JsonObject,
    samples: Mapping[str, bootstrap.BenchSample],
    *,
    bootstrap_iters: int,
) -> None:
    axis = axis_for_key("tool_use")
    tool_use = axes.get("tool_use")
    if axis is None or not isinstance(tool_use, dict):
        return
    facets: JsonObject = {}
    for facet in axis.facets:
        sample = samples.get(facet.bench)
        if sample is None:
            return
        values = [
            signed_score(1.0 if correct else 0.0, chance=sample["chance"])
            for correct in sample["correct"]
        ]
        ci = bootstrap.stratified_mean_ci(
            values,
            sample["strata"],
            clusters=sample["clusters"],
            seed=0,
            iters=bootstrap_iters,
        )
        facets[facet.key] = score_interval(ci["point"], ci["lo"], ci["hi"]) | {
            "bench": facet.bench,
            "weight": facet.weight,
            "raw_accuracy": _mean_bool(sample["correct"]),
            "n": len(sample["correct"]),
        }
    tool_use["facets"] = facets


def _model_identity(record: Mapping[str, JsonValue]) -> JsonObject:
    explicit = record.get("model_identity")
    if isinstance(explicit, dict):
        return dict(explicit)
    model = record.get("model")
    if isinstance(model, dict):
        return {
            key: value
            for key in (
                "model_system_key",
                "file_sha256",
                "declared_name",
                "family",
                "quant_label",
            )
            if (value := model.get(key)) is not None
        }
    return {
        key: value
        for key in ("catalog_id", "model_label", "quant_label")
        if (value := record.get(key)) is not None
    }


def _mean_bool(values: Sequence[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0
