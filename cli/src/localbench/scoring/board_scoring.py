"""Run scoring and model-row assembly for board_v1."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.scoring import bootstrap, cluster_for_item, score_interval, stratum_for_item
from localbench.scoring.axes import web_display_axes, web_source_bench_groups
from localbench.scoring.board_support import (
    DEFAULT_BOOTSTRAP_SEED,
    LANE_SCOPE,
    bool_value,
    int_value,
    is_superseded,
    number_or_none,
    number_value,
    object_or_empty,
    object_value,
    objects_value,
    percentile,
    read_json,
    run_path,
    slugify,
    string_value,
    text_value,
)
from localbench.scoring.board_systems import best_system, system_fields
from localbench.scoring.board_types import BoardBuildError, CuratedSource, ScoredRun
from localbench.scoring.signed_score import chance_for_bench, signed_score
from localbench.scoring.tc_json_conformance import GATE_ID, tc_json_conformance_gate

APPWORLD_C_BENCH = "appworld_c"


def scored_runs(
    sources: Sequence[CuratedSource],
    *,
    runs_dir: Path,
    bootstrap_iters: int,
    weights: Mapping[str, float],
) -> tuple[list[ScoredRun], list[JsonObject]]:
    scored: list[ScoredRun] = []
    skipped: list[JsonObject] = []
    for order, source in enumerate(sources):
        path = run_path(source["file"], runs_dir)
        if is_superseded(path) or not path.exists():
            skipped.append({"file": path.name, "reason": "missing"})
            continue
        try:
            run = object_value(read_json(path), path.name)
            scored.append(_scored_run(source, run, path, runs_dir=runs_dir, order=order, bootstrap_iters=bootstrap_iters, weights=weights))
        except (BoardBuildError, json.JSONDecodeError, OSError) as error:
            skipped.append({"file": path.name, "reason": f"incomplete: {error}"})
    return scored, skipped


def model_rows(scored: Sequence[ScoredRun]) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for group in _groups(scored).values():
        best = best_system(group)
        row = {
            "slug": best["slug"],
            "catalog_id": best["catalog_id"],
            "model_label": best["model_label"],
            "family": best["family"],
            "kind": best["kind"],
            "best_run_id": best["best_run_id"],
            "composite": best["composite"],
            "axes": best["axes"],
            "tier": best["tier"],
            "lane": best["lane"],
            "n_runs": len(group),
            "ranked": best["ranked"],
            "tokens_to_answer_median": best["tokens_to_answer_median"],
            "tokens_to_answer_p95": best["tokens_to_answer_p95"],
            "latency_s_median": best["latency_s_median"],
            "wall_time_seconds": best["wall_time_seconds"],
            "est_cost_usd": best["est_cost_usd"],
            "replicated": any(run["replicated"] for run in group),
            "score_status": best["score_status"],
            "demo": False,
        } | system_fields(group, best)
        publisher = best.get("publisher")
        if publisher is not None:
            row["publisher"] = publisher
        gguf_repo = best.get("gguf_repo")
        if gguf_repo is not None:
            row["gguf_repo"] = gguf_repo
        if "conformance_gates" in best:
            row["conformance_gates"] = best["conformance_gates"]
        if "agentic_run" in best:
            row["agentic_run"] = best["agentic_run"]
        rows.append(row)
    return sorted(rows, key=lambda row: (not bool_value(row["ranked"], "ranked"), -(_model_point(row) or 0.0), text_value(row.get("model_label")) or ""))


def suite_version(scored: Sequence[ScoredRun]) -> str:
    versions = sorted({run["suite_version"] for run in scored if run["suite_version"] is not None})
    if len(versions) == 1:
        return versions[0]
    return "mixed" if versions else "unknown"


def item_set_hashes(scored: Sequence[ScoredRun]) -> JsonObject:
    rendered: JsonObject = {}
    for run in scored:
        for key, value in run["item_set_hashes"].items():
            if isinstance(value, str):
                rendered[key] = value
    return rendered


def _scored_run(
    source: CuratedSource,
    run: JsonObject,
    path: Path,
    *,
    runs_dir: Path,
    order: int,
    bootstrap_iters: int,
    weights: Mapping[str, float],
) -> ScoredRun:
    benches = dict(object_value(run.get("benches"), f"{path.name}.benches"))
    items = list(objects_value(run.get("items"), f"{path.name}.items"))
    _inject_appworld_c(source, benches, items, runs_dir)
    totals = object_value(run.get("totals"), f"{path.name}.totals")
    manifest = object_or_empty(run.get("manifest"))
    suite = object_or_empty(manifest.get("suite"))
    conformance = object_or_empty(run.get("conformance"))
    lane = source["reasoning_lane"] or text_value(suite.get("lane"))
    slug = slugify(source["model_label"])
    axes, samples = _axes_and_samples(benches, items, object_or_empty(conformance.get("per_bench")), bootstrap_iters)
    composite = _composite(samples, axes, bootstrap_iters, weights)
    tokens = _completion_token_stats(items)
    tok_s = number_or_none(totals.get("completion_tokens_per_second"))
    run_id = f"{slug}__{path.stem}"
    scored: ScoredRun = {
        "axes": axes,
        "best_run_id": run_id,
        "catalog_id": source["model_id"],
        "composite": composite,
        "composite_raw": number_value(composite["point_raw"], "composite.point_raw"),
        "est_cost_usd": number_or_none(run.get("estimated_cost_usd")),
        "family": source["family"],
        "kind": source["kind"],
        "lane": lane,
        "model_label": source["model_label"],
        "order": order,
        "quant_label": source["quant_label"],
        "ranked": _ranked(source, lane, text_value(conformance.get("status")), axes),
        "recommended": source["recommended"],
        "replicated": source["independent_replication"],
        "run_id": run_id,
        "run_path_stem": path.stem,
        "score_status": "measured",
        "slug": slug,
        "tier": text_value(suite.get("tier")),
        "tokens_to_answer_median": tokens["median"],
        "tokens_to_answer_p95": tokens["p95"],
        "latency_s_median": round(tokens["median"] / tok_s, 3) if tokens["median"] is not None and tok_s else None,
        "wall_time_seconds": number_or_none(totals.get("wall_time_seconds")),
        "suite_version": text_value(suite.get("suite_version")),
        "item_set_hashes": object_or_empty(suite.get("item_set_hashes")),
    }
    publisher = source.get("publisher")
    if publisher is not None:
        scored["publisher"] = publisher
    gguf_repo = source.get("gguf_repo")
    if gguf_repo is not None:
        scored["gguf_repo"] = gguf_repo
    agentic_run = run.get("agentic_run")
    if isinstance(agentic_run, dict):
        # Surface the inline campaign provenance (asr_series / mean_asr / drift / subset_hash) so the
        # board can show how the agentic axis was measured. Absent for sidecar/pre-inline runs, so
        # this key is omitted there (parity-preserving for the frozen board_v1).
        scored["agentic_run"] = agentic_run
    conformance_gate = _tc_json_gate(path, runs_dir, slug)
    if conformance_gate is not None:
        scored["conformance_gates"] = {GATE_ID: conformance_gate}
    return scored


def _inject_appworld_c(source: CuratedSource, benches: JsonObject, items: list[JsonObject], runs_dir: Path) -> None:
    # Inline campaign agentic (Stage 4b) WINS: when the run record already carries appworld_c
    # (localbench run --bench all ran the rerun campaign inline), keep it and do NOT overwrite from
    # the agentic_file sidecar — overwriting would also double-count the per-task items. The sidecar
    # is the FALLBACK only for pre-inline runs that have no inline appworld_c bench.
    if APPWORLD_C_BENCH in benches:
        return
    agentic_file = source["agentic_file"]
    if agentic_file is None:
        return
    path = run_path(agentic_file, runs_dir)
    if not path.exists():
        return
    report = object_value(object_value(read_json(path), path.name).get("report"), f"{path.name}.report")
    successes = [
        (
            string_value(result.get("task_id"), f"{path.name}.report.results.task_id"),
            bool_value(result.get("success"), f"{path.name}.report.results.success"),
        )
        for result in objects_value(report.get("results"), f"{path.name}.report.results")
    ]
    asr = sum(1 for _task_id, success in successes if success) / len(successes) if successes else 0.0
    benches[APPWORLD_C_BENCH] = {
        "n": len(successes),
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": asr,
        "chance_corrected": asr,
        "conditional_accuracy": asr,
        "termination_rate": 1.0,
    }
    items.extend({"id": task_id, "bench": APPWORLD_C_BENCH, "correct": success, "error": None} for task_id, success in successes)


def _tc_json_gate(path: Path, runs_dir: Path, slug: str) -> JsonObject | None:
    tc_json_dir = runs_dir / "tc-json"
    for key in (path.stem, slug):
        tc_json_path = tc_json_dir / f"{key}.json"
        if tc_json_path.exists():
            record = object_value(read_json(tc_json_path), str(tc_json_path))
            aggregate = object_value(record.get("aggregate"), f"{tc_json_path}.aggregate")
            return tc_json_conformance_gate(aggregate)
    return None


def _axes_and_samples(
    benches: JsonObject,
    items: Sequence[JsonObject],
    conformance: JsonObject,
    bootstrap_iters: int,
) -> tuple[JsonObject, dict[str, bootstrap.BenchSample]]:
    axes: JsonObject = {}
    samples: dict[str, bootstrap.BenchSample] = {}
    item_groups = _items_by_bench(items)
    for axis in web_display_axes():
        source_names = _source_benches_for_axis(axis, benches)
        if not source_names:
            continue
        axis_values, axis_strata, no_answer = _axis_samples(source_names, item_groups, samples)
        aggregates = [object_value(benches.get(bench), f"benches.{bench}") for bench in source_names]
        axis_ci = bootstrap.stratified_mean_ci(axis_values, axis_strata, seed=DEFAULT_BOOTSTRAP_SEED, iters=bootstrap_iters)
        axis_score = score_interval(_weighted(aggregates, source_names, "chance_corrected"), axis_ci["lo"], axis_ci["hi"])
        axis_score |= {
            "raw_accuracy": _weighted(aggregates, source_names, "raw_accuracy"),
            "n": sum(int_value(aggregate.get("n"), "bench.n") for aggregate in aggregates),
            "n_errors": sum(int_value(aggregate.get("n_errors"), "bench.n_errors") for aggregate in aggregates),
            "n_no_answer": sum(int_value(aggregate.get("n_extraction_failures"), "bench.n_extraction_failures") for aggregate in aggregates) + no_answer,
        }
        _copy_optional_weighted(axis_score, aggregates, source_names, ("termination_rate", "conditional_accuracy"))
        _copy_conformance_rates(axis_score, conformance, source_names)
        axes[axis] = axis_score
    return axes, samples


def _axis_samples(source_names: Sequence[str], item_groups: Mapping[str, Sequence[JsonObject]], samples: dict[str, bootstrap.BenchSample]) -> tuple[list[float], list[str], int]:
    values: list[float] = []
    strata: list[str] = []
    no_answer = 0
    for bench in source_names:
        correct, bench_strata, clusters, missing = _sample_parts(bench, item_groups.get(bench, ()))
        no_answer += missing
        chance = chance_for_bench(bench)
        values.extend(signed_score(1.0 if value else 0.0, chance=chance) for value in correct)
        strata.extend(bench_strata)
        samples[bench] = {"correct": correct, "strata": bench_strata, "clusters": clusters, "chance": chance}
    return values, strata, no_answer


def _composite(samples: Mapping[str, bootstrap.BenchSample], axes: Mapping[str, JsonValue], bootstrap_iters: int, weights: Mapping[str, float]) -> JsonObject:
    source_weights = {
        bench: weights[axis]
        for axis in web_display_axes()
        if axis in axes and weights.get(axis, 0.0) > 0.0
        for bench in _source_benches_for_axis(axis, {name: {} for name in samples})
    }
    present = {bench: sample for bench, sample in samples.items() if source_weights.get(bench, 0.0) > 0.0}
    if not present:
        return score_interval(0.0, 0.0, 0.0)
    ci = bootstrap.composite_ci(present, source_weights, seed=DEFAULT_BOOTSTRAP_SEED, iters=bootstrap_iters)
    return score_interval(ci["point"], ci["lo"], ci["hi"])


def _sample_parts(bench: str, items: Sequence[JsonObject]) -> tuple[list[bool], list[str], list[str], int]:
    correct: list[bool] = []
    strata: list[str] = []
    clusters: list[str] = []
    missing = 0
    for item in items:
        item_id = string_value(item.get("id"), f"{bench}.item.id")
        value = item.get("correct")
        is_correct = bool(value) if isinstance(value, bool) and item.get("error") is None else False
        missing += 1 if not isinstance(value, bool) and item.get("error") is None else 0
        correct.append(is_correct)
        strata.append(stratum_for_item(bench, item_id, item))
        clusters.append(cluster_for_item(bench, item_id, item))
    return correct, strata, clusters, missing


def _completion_token_stats(items: Sequence[JsonObject]) -> dict[str, float | None]:
    values = sorted(
        token
        for item in items
        if (token := number_or_none(object_or_empty(item.get("usage")).get("completion_tokens"))) is not None
    )
    return {"median": percentile(values, 0.5), "p95": percentile(values, 0.95)} if values else {"median": None, "p95": None}


def _groups(scored: Sequence[ScoredRun]) -> dict[str, list[ScoredRun]]:
    groups: dict[str, list[ScoredRun]] = {}
    for run in scored:
        groups.setdefault((run["catalog_id"] or run["slug"]).lower(), []).append(run)
    return groups


def _items_by_bench(items: Sequence[JsonObject]) -> dict[str, list[JsonObject]]:
    groups: dict[str, list[JsonObject]] = {}
    for item in items:
        bench = text_value(item.get("bench"))
        if bench is not None:
            groups.setdefault(bench, []).append(item)
    return groups


def _source_benches_for_axis(axis: str, benches: Mapping[str, JsonValue]) -> tuple[str, ...]:
    for group in web_source_bench_groups().get(axis, ((axis,),)):
        if all(bench in benches for bench in group):
            return group
    return ()


def _copy_optional_weighted(target: JsonObject, aggregates: Sequence[JsonObject], names: Sequence[str], keys: Sequence[str]) -> None:
    for key in keys:
        if all(isinstance(aggregate.get(key), int | float) for aggregate in aggregates):
            target[key] = _weighted(aggregates, names, key)


def _copy_conformance_rates(target: JsonObject, conformance: JsonObject, names: Sequence[str]) -> None:
    for key in ("leaked_reasoning_rate", "truncation_rate", "no_final_answer_rate"):
        values = [number_or_none(object_or_empty(conformance.get(name)).get(key)) for name in names]
        target[key] = sum(value for value in values if value is not None) / len(values) if all(value is not None for value in values) and values else None


def _weighted(aggregates: Sequence[JsonObject], names: Sequence[str], key: str) -> float:
    counts = [int_value(aggregate.get("n"), f"{name}.n") for name, aggregate in zip(names, aggregates, strict=True)]
    total = sum(counts)
    return sum(number_value(aggregate.get(key), f"{name}.{key}") * count for name, aggregate, count in zip(names, aggregates, counts, strict=True)) / total if total else 0.0


def _ranked(source: CuratedSource, lane: str | None, conformance_status: str | None, axes: Mapping[str, JsonValue]) -> bool:
    return source["kind"] != "anchor" and lane == LANE_SCOPE and conformance_status == "headline-comparable" and bool(axes)


def _model_point(model: Mapping[str, JsonValue]) -> float | None:
    return number_or_none(object_or_empty(model.get("composite")).get("point"))
