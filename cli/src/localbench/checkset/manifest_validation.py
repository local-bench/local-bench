from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from localbench.checkset.models import (
    ChecksetBuildError,
    JsonObject,
    JsonValue,
    ModuleRecord,
)
from localbench.checkset.sources import CODING_EXCLUSIONS
from localbench.checkset.upstream import (
    GPQA_CONFIG,
    GPQA_REPO,
    GPQA_REVISION,
    OLYMMATH_AIME_CONFIG,
    OLYMMATH_REPO,
    OLYMMATH_REVISION,
)

LOCKED_COUNTS = {
    "knowledge": 198,
    "coding": 96,
    "instruction": 120,
    "math": 60,
    "tools-single": 54,
    "tools-stateful": 48,
    "sanity-gates": 18,
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def validate_manifest_inputs(
    *,
    modules: Sequence[ModuleRecord],
    stateful: JsonObject,
    source_metadata: JsonObject,
    pool_exclusions: Sequence[JsonObject],
) -> None:
    counts = {module.name: module.scored for module in modules}
    scored = sum(counts.get(name, 0) for name in LOCKED_COUNTS if name != "sanity-gates")
    gates = counts.get("sanity-gates", 0)
    spares = stateful.get("spares_ordered")
    spare_count = len(spares) if isinstance(spares, list) else -1
    if len(modules) != len(LOCKED_COUNTS) or counts != LOCKED_COUNTS or (scored, gates, spare_count) != (576, 18, 6):
        raise ChecksetBuildError("Manifest must contain 576 scored + 18 gates + 6 spares = 600 authored items.")
    module_ids = _validate_modules(modules)
    _validate_stateful(stateful, modules=modules, module_ids=module_ids)
    knowledge = next(module for module in modules if module.name == "knowledge")
    math = next(module for module in modules if module.name == "math")
    _validate_source_metadata(
        source_metadata,
        knowledge_ids={item.item_id for item in knowledge.items},
        math_items={(item.item_id, item.content_sha256) for item in math.items},
    )
    _validate_exclusions(pool_exclusions)


def _validate_modules(modules: Sequence[ModuleRecord]) -> list[str]:
    module_ids: list[str] = []
    for module in modules:
        if len(module.items) != module.scored:
            raise ChecksetBuildError(
                f"Manifest module item list {module.name!r} has {len(module.items)} records, expected {module.scored}."
            )
        for item in module.items:
            if not item.item_id or not _is_sha256(item.content_sha256):
                raise ChecksetBuildError(f"Manifest module {module.name!r} contains an invalid authored record.")
            module_ids.append(item.item_id)
        _validate_module_contract(module)
    if len(set(module_ids)) != len(module_ids):
        raise ChecksetBuildError("Manifest module item ids must be globally unique.")
    return module_ids


def _validate_module_contract(module: ModuleRecord) -> None:
    source = module.source
    scorer = module.scorer
    selection = module.selection
    if not isinstance(source, dict) or set(source) != {"dataset", "revision", "split"}:
        raise ChecksetBuildError(f"Manifest module {module.name!r} must carry source provenance.")
    if not all(isinstance(source.get(key), str) and source[key] for key in ("dataset", "revision", "split")):
        raise ChecksetBuildError(f"Manifest module {module.name!r} has invalid source provenance.")
    revision = source["revision"]
    if not isinstance(revision, str) or _REVISION.fullmatch(revision) is None:
        raise ChecksetBuildError(f"Manifest module {module.name!r} has an invalid source revision.")
    if not isinstance(scorer, dict) or set(scorer) != {"name", "version"}:
        raise ChecksetBuildError(f"Manifest module {module.name!r} must carry scorer provenance.")
    if not all(isinstance(scorer.get(key), str) and scorer[key] for key in ("name", "version")):
        raise ChecksetBuildError(f"Manifest module {module.name!r} has invalid scorer provenance.")
    if not isinstance(selection, dict) or set(selection) != {"algorithm", "inputs_sha256", "seed"}:
        raise ChecksetBuildError(f"Manifest module {module.name!r} must carry selection provenance.")
    if not isinstance(selection.get("algorithm"), str) or not selection["algorithm"]:
        raise ChecksetBuildError(f"Manifest module {module.name!r} has an invalid selection algorithm.")
    if selection.get("seed") != 20260802 or not _is_sha256(selection.get("inputs_sha256")):
        raise ChecksetBuildError(f"Manifest module {module.name!r} has invalid selection provenance.")


def _validate_stateful(stateful: JsonObject, *, modules: Sequence[ModuleRecord], module_ids: list[str]) -> None:
    templates = stateful.get("templates")
    if not isinstance(templates, list) or len(templates) != 12 or len(set(_strings(templates))) != 12:
        raise ChecksetBuildError("Manifest stateful templates must contain exactly 12 unique names.")
    template_names = _strings(templates)
    if len(template_names) != 12:
        raise ChecksetBuildError("Manifest stateful templates must be strings.")
    instance_ids = _authored_ids(stateful.get("instances"), label="stateful instances", expected=48)
    stateful_module = next(module for module in modules if module.name == "tools-stateful")
    if set(instance_ids) != {item.item_id for item in stateful_module.items}:
        raise ChecksetBuildError("Manifest stateful authored records must match the tools-stateful module items.")
    cluster_map = stateful.get("cluster_map")
    if not isinstance(cluster_map, dict) or set(cluster_map) != set(instance_ids):
        raise ChecksetBuildError("Manifest stateful cluster map must cover every instance exactly once.")
    clusters = [cluster_map[item_id] for item_id in instance_ids]
    if any(not isinstance(cluster, str) or cluster not in template_names for cluster in clusters):
        raise ChecksetBuildError("Manifest stateful cluster map references an unknown template.")
    if Counter(clusters) != Counter({template: 4 for template in template_names}):
        raise ChecksetBuildError("Manifest stateful cluster map must assign four instances per template.")
    spare_ids = _authored_ids(stateful.get("spares_ordered"), label="stateful spares", expected=6)
    if set(module_ids) & set(spare_ids) or len(set(spare_ids)) != len(spare_ids):
        raise ChecksetBuildError("Manifest authored item and spare ids must be globally unique.")


def _validate_source_metadata(
    source_metadata: JsonObject,
    *,
    knowledge_ids: set[str],
    math_items: set[tuple[str, str]],
) -> None:
    if set(source_metadata) != {"gpqa", "gpqa_canary_strip_log", "math_aime"}:
        raise ChecksetBuildError("Manifest source metadata contains unallowlisted fields.")
    gpqa = source_metadata.get("gpqa")
    if gpqa != {"repository": GPQA_REPO, "config": GPQA_CONFIG, "revision": GPQA_REVISION}:
        raise ChecksetBuildError("Manifest source metadata has invalid GPQA provenance.")
    math_aime = source_metadata.get("math_aime")
    if not isinstance(math_aime, dict) or set(math_aime) != {"repository", "config", "revision", "selected"}:
        raise ChecksetBuildError("Manifest source metadata has invalid math AIME-band provenance.")
    if {key: math_aime[key] for key in ("repository", "config", "revision")} != {
        "repository": OLYMMATH_REPO,
        "config": OLYMMATH_AIME_CONFIG,
        "revision": OLYMMATH_REVISION,
    }:
        raise ChecksetBuildError("Manifest source metadata has invalid math AIME-band provenance.")
    _validate_math_selection(math_aime.get("selected"), math_items=math_items)
    canary_log = source_metadata.get("gpqa_canary_strip_log")
    if not isinstance(canary_log, list) or len(canary_log) != 198:
        raise ChecksetBuildError("Manifest must carry the 198-entry GPQA canary-removal log.")
    logged_ids: list[str] = []
    for record in canary_log:
        if not isinstance(record, dict) or set(record) != {"field", "item_id", "removed_sha256"}:
            raise ChecksetBuildError("Manifest source metadata has an invalid GPQA canary-removal record.")
        item_id = record.get("item_id")
        if record.get("field") != "Canary String" or not isinstance(item_id, str) or not _is_sha256(record.get("removed_sha256")):
            raise ChecksetBuildError("Manifest source metadata has an invalid GPQA canary-removal record.")
        logged_ids.append(item_id)
    if len(set(logged_ids)) != 198 or set(logged_ids) != knowledge_ids:
        raise ChecksetBuildError("GPQA canary-removal log must cover every knowledge item exactly once.")


def _validate_math_selection(raw: JsonValue, *, math_items: set[tuple[str, str]]) -> None:
    if not isinstance(raw, list) or len(raw) != 30:
        raise ChecksetBuildError("Manifest source metadata must carry 30 math AIME-band selections.")
    indices: list[int] = []
    for record in raw:
        if not isinstance(record, dict) or set(record) != {"content_sha256", "subject", "upstream_index"}:
            raise ChecksetBuildError("Manifest source metadata has an invalid math AIME-band selection.")
        index = record.get("upstream_index")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ChecksetBuildError("Manifest source metadata has an invalid math AIME-band selection.")
        if not isinstance(record.get("subject"), str) or not record["subject"] or not _is_sha256(record.get("content_sha256")):
            raise ChecksetBuildError("Manifest source metadata has an invalid math AIME-band selection.")
        indices.append(index)
    if len(set(indices)) != 30:
        raise ChecksetBuildError("Manifest source metadata has duplicate math AIME-band selections.")
    expected = {
        (f"olymmath-en-easy-{record['upstream_index']:05d}", record["content_sha256"])
        for record in raw
        if isinstance(record, dict)
        and isinstance(record.get("upstream_index"), int)
        and isinstance(record.get("content_sha256"), str)
    }
    published = {item for item in math_items if item[0].startswith("olymmath-en-easy-")}
    if expected != published or len(math_items - published) != 30:
        raise ChecksetBuildError("Manifest math AIME-band selections must match the published math module items.")


def _validate_exclusions(pool_exclusions: Sequence[JsonObject]) -> None:
    expected = tuple(
        {"item_id": item_id, "module": "coding", "reason": "sandbox-unscoreable"}
        for item_id in CODING_EXCLUSIONS
    )
    if tuple(pool_exclusions) != expected:
        raise ChecksetBuildError("Manifest must carry the seven pinned coding pool exclusions.")


def _authored_ids(raw: JsonValue, *, label: str, expected: int) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) != expected:
        count = len(raw) if isinstance(raw, list) else 0
        raise ChecksetBuildError(f"Manifest {label} has {count} records, expected {expected}.")
    item_ids: list[str] = []
    for record in raw:
        if not isinstance(record, dict) or set(record) != {"content_sha256", "item_id"}:
            raise ChecksetBuildError(f"Manifest {label} must contain authored records.")
        item_id = record.get("item_id")
        if not isinstance(item_id, str) or not item_id or not _is_sha256(record.get("content_sha256")):
            raise ChecksetBuildError(f"Manifest {label} contains an invalid authored record.")
        item_ids.append(item_id)
    return tuple(item_ids)


def _is_sha256(value: JsonValue) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _strings(values: list[JsonValue]) -> list[str]:
    return [value for value in values if isinstance(value, str)]
