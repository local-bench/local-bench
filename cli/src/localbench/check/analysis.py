from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

from localbench._types import JsonObject, JsonValue
from localbench.check.statistics import AREA_NAMES, PairedOutcome, paired_measures, simultaneous_intervals
from localbench.check.verdict import aggregate_scores, quant_verdict, tune_area_outcome
from localbench.check.types import CheckError
from localbench.submissions.canon import write_json_file


def analyze_run(
    run_dir: Path,
    manifest: JsonObject,
    *,
    artifact_class: str,
    resamples: int = 100_000,
) -> tuple[JsonObject, JsonObject]:
    grades = _read_jsonl(run_dir / "grades.jsonl")
    outcomes = _paired_outcomes(grades, manifest=manifest)
    intervals = simultaneous_intervals(outcomes, resamples=resamples)
    measures: JsonObject = {area: paired_measures(outcomes[area]) for area in AREA_NAMES}
    interval_rows = intervals.get("areas")
    if not isinstance(interval_rows, dict):
        raise CheckError("statistics engine returned no area intervals")
    scores = _module_scores(grades)
    aggregation = aggregate_scores(scores, unsupported=())
    gate_status = _gate_status(grades, manifest=manifest)
    validity_gates_pass = gate_status.get("validity_pass") is True
    behavioral_gates_pass = gate_status.get("behavioral_pass") is True
    bounds = _manifest_bounds(manifest)
    verdict: JsonObject
    if artifact_class == "exact-quant":
        typed_intervals = _numeric_intervals(interval_rows)
        typed_measures = _numeric_measures(measures)
        verdict = quant_verdict(
            typed_intervals,
            typed_measures,
            bounds,
            validity_gates_pass=validity_gates_pass,
            behavioral_gates_pass=behavioral_gates_pass,
        )
    elif artifact_class in {"fine-tune", "distill", "merge"}:
        profile: JsonObject = {}
        for area in AREA_NAMES:
            row = interval_rows.get(area)
            if not isinstance(row, dict):
                raise CheckError(f"statistics interval missing for {area}")
            profile[area] = tune_area_outcome(_number(row.get("lower_pp")), _number(row.get("upper_pp")))
        verdict = {
            "area_profile": profile,
            "hard_functional_status": "pass" if validity_gates_pass else "broken",
            "record_type": "tune-delta-profile-v1",
            "verdict": "not-applicable",
        }
    else:
        verdict = {
            "label": "inconclusive — lineage is not verified",
            "record_type": "unverified-lineage-v1",
            "verdict": "inconclusive",
        }
    statistics_record: JsonObject = {
        "aggregation": aggregation,
        "bounds": bounds,
        "gates": gate_status,
        "intervals": intervals,
        "measures": measures,
        "resampling_design": _resampling_design(outcomes),
        "schema_version": "localbench-check-statistics-v1",
    }
    write_json_file(run_dir / "statistics.json", statistics_record)
    write_json_file(run_dir / "verdict.json", verdict)
    return statistics_record, verdict


def _paired_outcomes(grades: list[JsonObject], *, manifest: JsonObject) -> dict[str, list[PairedOutcome]]:
    areas: dict[str, list[PairedOutcome]] = {area: [] for area in AREA_NAMES}
    cluster_map = _cluster_map(manifest)
    stratum_map = _stratum_map(manifest)
    for grade in grades:
        module = _required_str(grade, "module")
        if module == "sanity-gates":
            continue
        area = "tools" if module in {"tools-single", "tools-stateful"} else module
        if area not in areas:
            raise CheckError(f"grade has unknown scored module {module!r}")
        item_id = _required_str(grade, "item_id")
        reference = _side_correct(grade, "reference")
        candidate = _side_correct(grade, "candidate")
        chance = 0.25 if module == "knowledge" else 0.0
        cluster = cluster_map.get(item_id, item_id)
        areas[area].append(
            PairedOutcome(
                item_id=item_id,
                reference_correct=reference,
                candidate_correct=candidate,
                stratum=stratum_map.get(item_id, module),
                cluster=cluster,
                chance=chance,
            )
        )
    return areas


def _resampling_design(outcomes: dict[str, list[PairedOutcome]]) -> JsonObject:
    design: JsonObject = {}
    for area in AREA_NAMES:
        rows = outcomes[area]
        design[area] = {
            "cluster_count": len({(row.stratum, row.cluster) for row in rows}),
            "strata": dict(sorted(Counter(row.stratum for row in rows).items())),
        }
    return design


def _module_scores(grades: list[JsonObject]) -> dict[str, float]:
    by_module: dict[str, list[float]] = {}
    for grade in grades:
        module = _required_str(grade, "module")
        if module == "sanity-gates":
            continue
        candidate = grade.get("candidate")
        if not isinstance(candidate, dict):
            raise CheckError("candidate grade must be an object")
        score = _number(candidate.get("chance_corrected"))
        by_module.setdefault(module, []).append(score)
    return {module: sum(values) / len(values) for module, values in by_module.items()}


def _gate_status(grades: list[JsonObject], *, manifest: JsonObject) -> JsonObject:
    validity: list[bool] = []
    behavioral: list[bool] = []
    kinds = _gate_kinds(manifest)
    for grade in grades:
        if grade.get("module") != "sanity-gates":
            continue
        candidate = grade.get("candidate")
        detail = candidate.get("detail") if isinstance(candidate, dict) else None
        correct = isinstance(candidate, dict) and candidate.get("correct") is True
        item_id = _required_str(grade, "item_id")
        kind = detail.get("gate_kind") if isinstance(detail, dict) else None
        if not isinstance(kind, str):
            kind = kinds.get(item_id)
        (behavioral if kind == "behavioral" else validity).append(correct)
    return {
        "behavioral_pass": bool(behavioral) and all(behavioral),
        "behavioral_total": len(behavioral),
        "validity_pass": bool(validity) and all(validity),
        "validity_total": len(validity),
    }


def _gate_kinds(manifest: JsonObject) -> dict[str, str]:
    sanity = manifest.get("sanity_gates")
    definitions = sanity.get("definitions") if isinstance(sanity, dict) else None
    if not isinstance(definitions, list):
        return {}
    result: dict[str, str] = {}
    for definition in definitions:
        if not isinstance(definition, dict):
            continue
        item_id = definition.get("item_id")
        kind = definition.get("gate_kind")
        if isinstance(item_id, str) and isinstance(kind, str):
            result[item_id] = kind
    return result


def _manifest_bounds(manifest: JsonObject) -> JsonObject:
    disagreement = manifest.get("disagreement_bounds")
    drop = manifest.get("drop_bounds")
    if not isinstance(disagreement, dict) or not isinstance(drop, dict):
        return {"disagreement": {}, "drop": {}, "status": "uncalibrated"}
    if disagreement.get("status") != "calibrated" or drop.get("status") != "calibrated":
        return {"disagreement": {}, "drop": {}, "status": "uncalibrated"}
    disagreement_values = disagreement.get("values")
    drop_values = drop.get("values")
    if not isinstance(disagreement_values, dict) or not isinstance(drop_values, dict):
        raise CheckError("calibrated manifest bounds require per-area values")
    return {"disagreement": disagreement_values, "drop": drop_values, "status": "calibrated"}


def _cluster_map(manifest: JsonObject) -> dict[str, str]:
    stateful = manifest.get("stateful")
    raw = stateful.get("cluster_map") if isinstance(stateful, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(value, str)}


def _stratum_map(manifest: JsonObject) -> dict[str, str]:
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise CheckError("check-set manifest has no modules")
    result: dict[str, str] = {}
    for module in modules:
        items = module.get("items") if isinstance(module, dict) else None
        if not isinstance(items, list):
            raise CheckError("check-set manifest module has no item list")
        for item in items:
            item_id = item.get("item_id") if isinstance(item, dict) else None
            stratum = item.get("selection_stratum") if isinstance(item, dict) else None
            if not isinstance(item_id, str) or not isinstance(stratum, str) or not stratum:
                raise CheckError("check-set manifest item has no frozen selection stratum")
            result[item_id] = stratum
    return result


def _numeric_intervals(rows: JsonObject) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for area in AREA_NAMES:
        row = rows.get(area)
        if not isinstance(row, dict):
            raise CheckError(f"statistics interval missing for {area}")
        result[area] = {"lower_pp": _number(row.get("lower_pp")), "upper_pp": _number(row.get("upper_pp"))}
    return result


def _numeric_measures(rows: JsonObject) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for area in AREA_NAMES:
        row = rows.get(area)
        if not isinstance(row, dict):
            raise CheckError(f"paired measures missing for {area}")
        result[area] = {
            "disagreement_rate": _number(row.get("disagreement_rate")),
            "drop_rate": _number(row.get("drop_rate")),
        }
    return result


def _read_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = cast(object, json.loads(line))
        if not isinstance(value, dict):
            raise CheckError(f"JSONL row is not an object: {path}")
        rows.append(cast(JsonObject, value))
    return rows


def _side_correct(row: JsonObject, side: str) -> bool:
    value = row.get(side)
    if not isinstance(value, dict) or not isinstance(value.get("correct"), bool):
        raise CheckError(f"grade side {side!r} has no correctness value")
    return value["correct"] is True


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"required field {key!r} is missing")
    return value


def _number(value: JsonValue) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CheckError("statistics field must be numeric")
    return float(value)
