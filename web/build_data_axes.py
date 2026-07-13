from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final, TypeAlias

from build_data_support import (
    JsonObject,
    JsonValue,
    ensure_cli_src_path,
    bool_value as _bool,
    int_value as _int,
    number_value as _number,
    object_value as _object,
    text_value as _text,
)

ensure_cli_src_path()

from localbench.scoring import bootstrap, score_interval  # noqa: E402
from localbench.scoring.axes import (  # noqa: E402
    web_composite_weights as season_2_web_composite_weights,
    web_display_axes as season_2_web_display_axes,
    web_source_bench_groups as season_2_web_source_bench_groups,
)
from localbench.coding_exec.score import BENCH as CODING_BENCH, SANDBOX_UNSCOREABLE_BCBH  # noqa: E402

StratumForItem: TypeAlias = Callable[[str, str | None, Mapping[str, JsonValue]], str]

# Web display axes, source-bench groups, and composite weights use the frozen
# season-1 contract below. Explicit v4 records opt into the live CLI
# registry through the SEASON_2_* constants, so registry upgrades cannot silently
# reinterpret live v1 site data.
BENCHES: Final = ("knowledge", "instruction", "math", "long_context", "agentic", "tool_calling", "coding")
SOURCE_BENCH_GROUPS_BY_AXIS: Final = {
    "knowledge": (("mmlu_pro",), ("supergpqa",)),
    "instruction": (("ifbench",), ("ifeval",)),
    "math": (("olymmath_hard", "amo"), ("genmath",)),
    "long_context": (("ruler_32k",),),
    "agentic": (("appworld_c",),),
    "tool_calling": (("tc_json_v1",),),
    "coding": (("bigcodebench_hard",), ("lcb",)),
}
COMPOSITE_WEIGHTS: Final = {
    "knowledge": 0.15,
    "instruction": 0.15,
    "math": 0.05,
    "long_context": 0.0,
    "agentic": 0.40,
    "tool_calling": 0.10,
    "coding": 0.15,
}
SEASON_2_BENCHES: Final = season_2_web_display_axes()
SEASON_2_SOURCE_BENCH_GROUPS_BY_AXIS: Final = season_2_web_source_bench_groups()
SEASON_2_COMPOSITE_WEIGHTS: Final = season_2_web_composite_weights()
SEED: Final = 20260612


def scored_inputs(
    items: list[JsonValue],
    stratum_for_item: StratumForItem,
    source_benches: JsonObject,
) -> tuple[dict[str, list[float]], dict[str, list[str]], dict[str, int]]:
    values = {bench: [] for bench in source_benches}
    strata = {bench: [] for bench in source_benches}
    no_answer = {bench: 0 for bench in source_benches}
    for value in items:
        item = _object(value, "item")
        bench = _text(item.get("bench"))
        if bench not in values:
            continue
        item_id = _text(item.get("id"))
        if bench == CODING_BENCH and item_id in SANDBOX_UNSCOREABLE_BCBH:
            continue
        chance = _chance_baseline(_object(source_benches.get(bench), f"benches.{bench}"), bench)
        strata[bench].append(stratum_for_item(bench, item_id, item) if item_id else bench)
        if item.get("error") is not None:
            values[bench].append(_signed_item_score(False, chance))
            continue
        if item.get("correct") is None:
            no_answer[bench] += 1
            values[bench].append(_signed_item_score(False, chance))
            continue
        values[bench].append(_signed_item_score(_bool(item.get("correct"), f"{bench}.correct"), chance))
    return values, strata, no_answer


def build_axes(
    source_benches: JsonObject,
    values: dict[str, list[float]],
    strata: dict[str, list[str]],
    no_answer: dict[str, int],
    iters: int,
    benches: tuple[str, ...],
    source_bench_groups_by_axis: Mapping[str, tuple[tuple[str, ...], ...]] = SOURCE_BENCH_GROUPS_BY_AXIS,
) -> tuple[JsonObject, list[JsonValue]]:
    axes: JsonObject = {}
    warnings: list[JsonValue] = []
    for axis in benches:
        source_names = _source_benches_for_axis(axis, source_benches, source_bench_groups_by_axis)
        if source_names:
            axes[axis] = _axis_from_benches(axis, source_names, source_benches, values, strata, no_answer, iters, warnings)
        else:
            # No source bench measured this axis in this run -> emit NO axis (never a
            # fabricated/synthesized score). The site hides absent axes and renders
            # "not measured" (METHODOLOGY-v2.1: only measured axes are displayed; missing
            # headline axes make the row diagnostic rather than ranked).
            warnings.append(f"{axis} not measured in this run; axis omitted")
    return axes, warnings


def build_composite(run: JsonObject, axes: JsonObject, benches: tuple[str, ...], weights: dict[str, float]) -> JsonObject:
    point = _weighted_axis_value(axes, benches, weights, "point_raw")
    lo = _weighted_axis_value(axes, benches, weights, "lo_raw")
    hi = _weighted_axis_value(axes, benches, weights, "hi_raw")
    stored_raw = run.get("composite")
    stored = None if isinstance(stored_raw, bool) else float(stored_raw) if isinstance(stored_raw, int | float) else None
    warnings: list[JsonValue] = (
        [f"composite point {point:.12f} differs from stored composite {stored:.12f}"]
        if stored is not None and abs(point - stored) > 1e-6
        else []
    )
    return {"interval": score_interval(point, lo, hi), "raw_point": point, "warnings": warnings}


def display_sampling(
    sampling: JsonObject,
    source_bench_groups_by_axis: Mapping[str, tuple[tuple[str, ...], ...]] = SOURCE_BENCH_GROUPS_BY_AXIS,
) -> JsonObject:
    by_bench = sampling.get("by_bench")
    if not isinstance(by_bench, dict):
        return sampling
    return sampling | {"by_bench": _display_axis_map(by_bench, source_bench_groups_by_axis)}


def display_item_set_hashes(
    item_set_hashes: JsonObject,
    source_bench_groups_by_axis: Mapping[str, tuple[tuple[str, ...], ...]] = SOURCE_BENCH_GROUPS_BY_AXIS,
) -> JsonObject:
    rendered: JsonObject = {}
    for raw_name, hash_value in item_set_hashes.items():
        name = _display_source_name(raw_name, rendered, source_bench_groups_by_axis)
        rendered[name] = hash_value
    return rendered


def _axis_from_benches(
    axis: str,
    source_names: tuple[str, ...],
    source_benches: JsonObject,
    values: dict[str, list[float]],
    strata: dict[str, list[str]],
    no_answer: dict[str, int],
    iters: int,
    warnings: list[JsonValue],
) -> JsonObject:
    aggregates = [_object(source_benches.get(bench), f"benches.{bench}") for bench in source_names]
    n_by_bench = [_int(aggregate.get("n"), f"{bench}.n") for bench, aggregate in zip(source_names, aggregates, strict=True)]
    point = _weighted_bench_value(source_names, aggregates, n_by_bench, "chance_corrected")
    axis_values = [value for bench in source_names for value in values.get(bench, [])]
    if axis_values and abs((sum(axis_values) / len(axis_values)) - point) > 1e-9:
        warnings.append(f"{axis} chance_corrected differs from item-derived mean; stale/inconsistent run JSON")
    ci = bootstrap.stratified_mean_ci(axis_values, [value for bench in source_names for value in strata.get(bench, [])], iters=iters, seed=SEED)
    axis_score: JsonObject = score_interval(point, ci["lo"], ci["hi"]) | {
        "n": sum(n_by_bench),
        "n_errors": sum(_int(aggregate.get("n_errors"), f"{bench}.n_errors") for bench, aggregate in zip(source_names, aggregates, strict=True)),
        "n_no_answer": sum(_int(aggregate.get("n_extraction_failures"), f"{bench}.n_extraction_failures") + no_answer.get(bench, 0) for bench, aggregate in zip(source_names, aggregates, strict=True)),
        "raw_accuracy": _weighted_bench_value(source_names, aggregates, n_by_bench, "raw_accuracy"),
    }
    # Pass the IFBench strict decomposition (raw_accuracy is already strict) through ONLY when every
    # source bench carries it, so legacy run JSONs (pre strict re-score) still build. The site reads
    # these flat off the axis. See docs/SITE-DATA-CONTRACT.md.
    for key in ("termination_rate", "conditional_accuracy"):
        if all(key in aggregate for aggregate in aggregates):
            axis_score[key] = _weighted_bench_value(source_names, aggregates, n_by_bench, key)
    if any("n_unscoreable" in aggregate for aggregate in aggregates):
        axis_score["n_unscoreable"] = sum(
            _int(aggregate.get("n_unscoreable", 0), f"{bench}.n_unscoreable")
            if "n_unscoreable" in aggregate
            else 0
            for bench, aggregate in zip(source_names, aggregates, strict=True)
        )
    return axis_score


def _source_benches_for_axis(
    axis: str,
    source_benches: JsonObject,
    source_bench_groups_by_axis: Mapping[str, tuple[tuple[str, ...], ...]],
) -> tuple[str, ...]:
    for group in source_bench_groups_by_axis.get(axis, ((axis,),)):
        if all(bench in source_benches for bench in group):
            return group
    return ()


def _weighted_bench_value(source_names: tuple[str, ...], aggregates: list[JsonObject], n_by_bench: list[int], key: str) -> float:
    n_total = sum(n_by_bench)
    return sum(_number(aggregate.get(key), f"{bench}.{key}") * n for bench, aggregate, n in zip(source_names, aggregates, n_by_bench, strict=True)) / n_total if n_total else 0.0


def _weighted_axis_value(axes: JsonObject, benches: tuple[str, ...], weights: dict[str, float], key: str) -> float:
    # Only axes actually present contribute. Unmeasured display axes (e.g. math/agentic
    # with no source bench) are now absent and carry weight 0.0, so skipping them leaves
    # the headline composite identical while avoiding a KeyError on the omitted axis.
    present = [bench for bench in benches if bench in axes]
    total = sum(weights[bench] for bench in present)
    if total == 0.0:
        return 0.0
    return sum(_number(_object(axes[bench], f"axes.{bench}").get(key), f"axes.{bench}.{key}") * weights[bench] for bench in present) / total


def _chance_baseline(aggregate: JsonObject, bench: str) -> float:
    raw = _number(aggregate.get("raw_accuracy"), f"{bench}.raw_accuracy")
    corrected = _number(aggregate.get("chance_corrected"), f"{bench}.chance_corrected")
    return 0.0 if abs(1.0 - corrected) < 1e-12 else (raw - corrected) / (1.0 - corrected)


def _signed_item_score(correct: bool, chance: float) -> float:
    return ((1.0 if correct else 0.0) - chance) / (1.0 - chance)


def _display_axis_map(
    source_map: Mapping[str, JsonValue],
    source_bench_groups_by_axis: Mapping[str, tuple[tuple[str, ...], ...]],
) -> JsonObject:
    rendered: JsonObject = {}
    for key, value in source_map.items():
        axis = _axis_for_source(key, source_bench_groups_by_axis)
        rendered[axis if axis is not None else key] = value
    return rendered


def _display_source_name(
    raw_name: str,
    rendered: JsonObject,
    source_bench_groups_by_axis: Mapping[str, tuple[tuple[str, ...], ...]],
) -> str:
    axis = _axis_for_source(raw_name.split(".", maxsplit=1)[0].split("_quick", maxsplit=1)[0], source_bench_groups_by_axis)
    stem, suffix = raw_name.rsplit(".", maxsplit=1) if "." in raw_name else (raw_name, "")
    candidate = f"{axis or stem}.{suffix}" if suffix else axis or stem
    while candidate in rendered:
        candidate = f"{candidate.rsplit('.', maxsplit=1)[0]}-part{len(rendered) + 1}.{suffix}" if suffix else f"{candidate}-part{len(rendered) + 1}"
    return candidate


def _axis_for_source(
    source_name: str,
    source_bench_groups_by_axis: Mapping[str, tuple[tuple[str, ...], ...]],
) -> str | None:
    for axis, groups in source_bench_groups_by_axis.items():
        if any(source_name in group for group in groups):
            return axis
    return None
