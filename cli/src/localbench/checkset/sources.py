from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from localbench.checkset.input_runs import (
    BENCHES,
    RUN_NAMES,
    load_verified_runs,
    read_json,
    read_jsonl,
    required_str,
)
from localbench.checkset.models import (
    ChecksetBuildError,
    ItemRecord,
    JsonObject,
    ModuleRecord,
)
from localbench.checkset.select import (
    SELECTION_SEED,
    SourceItem,
    select_cost_aware,
    select_ifbench,
)

CODING_EXCLUSIONS: Final = (
    "bcbh-006",
    "bcbh-007",
    "bcbh-014",
    "bcbh-035",
    "bcbh-074",
    "bcbh-096",
    "bcbh-104",
)
IFBENCH_QUOTAS: Final = {
    "format": 35,
    "words": 30,
    "count": 23,
    "ratio": 16,
    "sentence": 10,
    "custom": 4,
    "repeat": 2,
}


def build_local_modules(repo_root: Path) -> tuple[tuple[ModuleRecord, ...], tuple[JsonObject, ...]]:
    suite_root = repo_root / "suite" / "v2"
    suite_rows = {bench: read_jsonl(suite_root / f"{bench}.jsonl") for bench in BENCHES}
    suite_hashes = {
        bench: hashlib.sha256((suite_root / f"{bench}.jsonl").read_bytes()).hexdigest()
        for bench in BENCHES
    }
    manifest = read_json(repo_root / "docs" / "v2" / "inputs" / "inputs-manifest.json")
    correctness, latency = load_verified_runs(manifest, suite_root=suite_root)
    source_items = {
        bench: _source_items(bench, rows, correctness, latency)
        for bench, rows in suite_rows.items()
    }
    coding_pool = tuple(
        item for item in source_items["bigcodebench_hard"] if item.item_id not in CODING_EXCLUSIONS
    )
    if len(coding_pool) != 141:
        raise ChecksetBuildError(f"Coding usable pool is {len(coding_pool)}, expected 141 after exclusions.")
    coding_informative = tuple(item for item in coding_pool if item.informative)
    coding_complement = tuple(item for item in coding_pool if not item.informative)
    coding = tuple(sorted(coding_informative, key=lambda item: item.item_id)) + select_cost_aware(
        coding_complement,
        quota=58,
        median_pool=coding_pool,
    )
    if len(coding_informative) != 38 or len(coding) != 96:
        raise ChecksetBuildError(f"Coding selection mismatch: {len(coding_informative)} informative, {len(coding)} total.")

    instruction = select_ifbench(source_items["ifbench"], IFBENCH_QUOTAS)
    informative_count = sum(item.informative for item in instruction)
    if informative_count != 72 or len(instruction) != 120:
        raise ChecksetBuildError(f"IFBench selection mismatch: {informative_count} informative, {len(instruction)} total.")

    legacy_pool = tuple(
        item
        for bench in ("olymmath_hard", "amo")
        for item in source_items[bench]
        if item.informative
    )
    if len(legacy_pool) != 55:
        raise ChecksetBuildError(f"Legacy math informative pool is {len(legacy_pool)}, expected 55.")
    math_legacy = select_cost_aware(legacy_pool, quota=30)

    tools_pool = source_items["tc_json_v1"]
    fresh_ids = {
        required_str(row, "id")
        for row in suite_rows["tc_json_v1"]
        if row.get("stratum") == "fresh_common_tools"
    }
    fresh = tuple(item for item in tools_pool if item.item_id in fresh_ids)
    informative_bfcl = tuple(
        item for item in tools_pool if item.item_id not in fresh_ids and item.informative
    )
    selected_ids = fresh_ids | {item.item_id for item in informative_bfcl}
    complement = min(
        (item for item in tools_pool if item.item_id not in selected_ids and item.tool_count > 1),
        key=lambda item: item.item_id,
    )
    tools = tuple(sorted(fresh + informative_bfcl + (complement,), key=lambda item: item.item_id))
    if len(fresh) != 30 or len(informative_bfcl) != 23 or len(tools) != 54:
        raise ChecksetBuildError(
            f"Tools selection mismatch: {len(fresh)} fresh, {len(informative_bfcl)} informative, {len(tools)} total."
        )

    modules = (
        _module(
            "coding",
            coding,
            source={"dataset": "suite/v2/bigcodebench_hard", "revision": suite_hashes["bigcodebench_hard"], "split": "pool"},
            scorer="coding_exec",
            algorithm="all-informative-plus-cost-aware-complement-v1",
            selection_pool=coding_pool,
        ),
        _module(
            "instruction",
            instruction,
            source={"dataset": "suite/v2/ifbench", "revision": suite_hashes["ifbench"], "split": "pool"},
            scorer="ifbench",
            algorithm="primary-stratum-informative-preferred-v1",
            selection_pool=source_items["ifbench"],
        ),
        _module(
            "math-legacy",
            math_legacy,
            source={
                "dataset": "suite/v2/olymmath_hard+amo",
                "revision": _content_sha256(
                    {"amo": suite_hashes["amo"], "olymmath_hard": suite_hashes["olymmath_hard"]}
                ),
                "split": "informative-pools",
            },
            scorer="math_symbolic_numeric",
            algorithm="legacy-informative-cost-aware-v1",
            selection_pool=legacy_pool,
        ),
        _module(
            "tools-single",
            tools,
            source={"dataset": "suite/v2/tc_json_v1", "revision": suite_hashes["tc_json_v1"], "split": "pool"},
            scorer="tc_json_v1",
            algorithm="fresh-plus-informative-plus-lowest-multitool-v1",
            selection_pool=tools_pool,
        ),
    )
    exclusions = tuple(_coding_exclusion(item_id) for item_id in CODING_EXCLUSIONS)
    return modules, exclusions


def _coding_exclusion(item_id: str) -> JsonObject:
    return {
        "item_id": item_id,
        "module": "coding",
        "reason": "sandbox-unscoreable",
    }


def _module(
    name: str,
    items: tuple[SourceItem, ...],
    *,
    source: JsonObject,
    scorer: str,
    algorithm: str,
    selection_pool: tuple[SourceItem, ...],
) -> ModuleRecord:
    records = tuple(ItemRecord(item.item_id, item.content_sha256) for item in items)
    return ModuleRecord(
        name=name,
        scored=len(records),
        items=records,
        source=source,
        scorer={"name": scorer, "version": "localbench-v1"},
        selection={
            "algorithm": algorithm,
            "inputs_sha256": _selection_inputs_sha256(selection_pool),
            "seed": SELECTION_SEED,
        },
    )


def _selection_inputs_sha256(items: tuple[SourceItem, ...]) -> str:
    payload = [
        {
            "content_sha256": item.content_sha256,
            "informative": item.informative,
            "instruction_ids": list(item.instruction_ids),
            "item_id": item.item_id,
            "latency_seconds": item.latency_seconds,
            "tool_count": item.tool_count,
        }
        for item in items
    ]
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _source_items(
    bench: str,
    rows: tuple[JsonObject, ...],
    correctness: dict[str, dict[str, dict[str, bool]]],
    latency: dict[str, dict[str, float | None]],
) -> tuple[SourceItem, ...]:
    items: list[SourceItem] = []
    for row in rows:
        item_id = required_str(row, "id")
        correct_count = sum(correctness[run][bench][item_id] for run in RUN_NAMES)
        raw_instruction_ids = row.get("instruction_id_list", [])
        instruction_ids = tuple(value for value in raw_instruction_ids if isinstance(value, str)) if isinstance(raw_instruction_ids, list) else ()
        raw_tools = row.get("tools", [])
        tool_count = len(raw_tools) if isinstance(raw_tools, list) else 0
        items.append(
            SourceItem(
                item_id=item_id,
                content_sha256=_content_sha256(row),
                informative=0 < correct_count < 4,
                latency_seconds=latency[bench][item_id],
                instruction_ids=instruction_ids,
                tool_count=tool_count,
            )
        )
    return tuple(items)


def _content_sha256(row: JsonObject) -> str:
    data = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
