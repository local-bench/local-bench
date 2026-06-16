from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from localbench._types import JsonValue

# Capability axes. Benches in the same domain pool at the item level, so the
# axis (not the bench count) is the unit of weight: suite-v1 Math = olymmath_hard
# + amo pooled, which keeps Math at one axis-share instead of two bench-shares.
BENCH_DOMAINS: Final[dict[str, str]] = {
    # suite-v0 (retained for back-compat)
    "mmlu_pro": "Knowledge",
    "ifeval": "Instruction-Following",
    "genmath": "Math",
    # suite-v1 (5 capability axes)
    "supergpqa": "Knowledge",
    "ifbench": "Instruction-Following",
    "bfcl": "Agentic",
    "bfcl_multi_turn": "Agentic",
    "toolhop": "Agentic",
    "lcb": "Coding",
    "ruler_32k": "Long-Context",
    "olymmath_hard": "Math",
    "amo": "Math",
}

# Equal per-axis. Weights are normalized over the domains actually present, so a
# suite-v0 run (3 axes) gets 1/3 each and suite-v1 runs normalize over the axes
# selected for that run.
DOMAIN_WEIGHTS: Final[dict[str, float]] = {
    "Knowledge": 0.25,
    "Instruction-Following": 0.25,
    "Agentic": 0.25,
    "Coding": 0.25,
    "Long-Context": 0.25,
    "Math": 0.25,
}


@dataclass(frozen=True, slots=True)
class ItemMetadata:
    category: str | None = None
    difficulty: str | None = None
    template: str | None = None


def domain_for_bench(bench: str) -> str:
    """Return the capability domain for a benchmark."""
    return BENCH_DOMAINS.get(bench, bench)


def stratum_for_item(
    bench: str,
    item_id: str,
    item: Mapping[str, JsonValue],
) -> str:
    """Return the subject/template/difficulty stratum for an item."""
    fallback = _metadata_from_item(item)
    metadata = _suite_metadata().get((bench, item_id), fallback)
    category = fallback.category or metadata.category or "uncategorized"
    difficulty = fallback.difficulty or metadata.difficulty or "unspecified"
    template = fallback.template or metadata.template or "unspecified"
    match bench:
        case "mmlu_pro":
            return f"subject={category}"
        case "genmath":
            return f"category={category}|difficulty={difficulty}|template={template}"
        case "ifeval":
            return f"template={template}"
        case _:
            return f"bench={bench}|category={category}|difficulty={difficulty}|template={template}"


def cluster_for_item(
    bench: str,
    item_id: str,
    item: Mapping[str, JsonValue],
) -> str:
    """Return the resampling cluster for an item."""
    if "cluster" in item:
        return str(item["cluster"])
    return item_id


def _metadata_from_item(item: Mapping[str, JsonValue]) -> ItemMetadata:
    return ItemMetadata(
        category=_string(item.get("category")),
        difficulty=_string(item.get("difficulty")),
        template=_string(item.get("template")),
    )


@cache
def _suite_metadata() -> dict[tuple[str, str], ItemMetadata]:
    suite_dir = Path(__file__).resolve().parents[4] / "suite" / "v0"
    metadata: dict[tuple[str, str], ItemMetadata] = {}
    for bench, file_names in _suite_files(suite_dir).items():
        for file_name in file_names:
            for item in _read_jsonl(suite_dir / file_name):
                item_id = _item_id(item)
                if item_id is None:
                    continue
                metadata[(bench, item_id)] = _metadata_for_suite_item(bench, item)
    return metadata


def _suite_files(suite_dir: Path) -> dict[str, list[str]]:
    suite_path = suite_dir / "suite.json"
    if not suite_path.exists():
        return {}
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    benches = data.get("benches")
    if not isinstance(benches, dict):
        return {}
    files: dict[str, list[str]] = {}
    for bench, raw_config in benches.items():
        if not isinstance(bench, str) or not isinstance(raw_config, dict):
            continue
        itemsets = raw_config.get("itemsets")
        if not isinstance(itemsets, dict):
            continue
        files[bench] = []
        for raw_itemset in itemsets.values():
            if isinstance(raw_itemset, dict) and isinstance(raw_itemset.get("file"), str):
                files[bench].append(raw_itemset["file"])
    return files


def _read_jsonl(path: Path) -> list[Mapping[str, JsonValue]]:
    if not path.exists():
        return []
    items: list[Mapping[str, JsonValue]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if isinstance(data, dict):
            items.append(data)
    return items


def _metadata_for_suite_item(
    bench: str,
    item: Mapping[str, JsonValue],
) -> ItemMetadata:
    match bench:
        case "mmlu_pro":
            return ItemMetadata(category=_string(item.get("category")))
        case "genmath":
            return ItemMetadata(
                category=_string(item.get("category")),
                difficulty=_string(item.get("difficulty")),
                template=_string(item.get("template")),
            )
        case "ifeval":
            return ItemMetadata(template=_ifeval_template(item))
        case _:
            return ItemMetadata(
                category=_string(item.get("category")),
                difficulty=_string(item.get("difficulty")),
                template=_string(item.get("template")),
            )


def _ifeval_template(item: Mapping[str, JsonValue]) -> str | None:
    instruction_ids = item.get("instruction_id_list")
    if not isinstance(instruction_ids, list):
        return None
    return "+".join(str(value) for value in instruction_ids)


def _item_id(item: Mapping[str, JsonValue]) -> str | None:
    for key in ("id", "question_id", "key"):
        value = item.get(key)
        if isinstance(value, str | int):
            return str(value)
    return None


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None
