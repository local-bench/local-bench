"""Suite loading and prompt rendering helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import BenchmarkItem, JsonObject, JsonValue
from localbench.scorers.bfcl import build_bfcl_prompt
from localbench.scorers.bfcl_multi_turn import build_bfcl_multi_turn_prompt
from localbench.scorers.lcb import build_lcb_prompt
from localbench.scorers.ruler import build_ruler_prompt

_LETTERS: Final = "ABCDEFGHIJ"


@dataclass(frozen=True, slots=True)
class RenderedBench:
    name: str
    source_items: list[Mapping[str, JsonValue]]
    benchmark_items: list[BenchmarkItem]
    baseline: float
    decoding: JsonObject
    item_file: str


def render_benches(
    bench_choice: str,
    tier: str,
    max_items: int | None,
    suite_dir: Path,
    suite: JsonObject,
    warnings: list[str],
) -> list[RenderedBench]:
    """Render selected suite benches into runner-ready items."""
    benches = suite.get("benches")
    if not isinstance(benches, dict):
        return []
    names = (
        list(benches)
        if bench_choice == "all"
        else [name.strip() for name in bench_choice.split(",") if name.strip()]
    )
    rendered: list[RenderedBench] = []
    for name in names:
        bench_config = benches.get(name)
        if not isinstance(bench_config, dict):
            warnings.append(f"Skipping {name}: bench is not listed in suite.json")
            continue
        bench = _render_bench(name, bench_config, suite_dir, tier, max_items, warnings)
        if bench is not None:
            rendered.append(bench)
    return rendered


def read_json_object(path: Path) -> JsonObject:
    """Read a JSON object from disk, returning an empty object for non-object JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def item_hashes(suite_dir: Path, item_files: list[str]) -> dict[str, str]:
    """Read item-set hashes from itemsets.lock.json for the files that ran."""
    lock_path = suite_dir / "itemsets.lock.json"
    if not lock_path.exists():
        return {}
    lock = read_json_object(lock_path)
    files = lock.get("files")
    if not isinstance(files, dict):
        return {}
    hashes: dict[str, str] = {}
    for item_file in sorted(item_files):
        entry = files.get(item_file)
        if isinstance(entry, dict) and isinstance(entry.get("sha256"), str):
            hashes[item_file] = entry["sha256"]
    return hashes


def suite_version(suite: JsonObject) -> str:
    """Return the declared suite version."""
    return _string(suite.get("version")) or "v0"


def first_prompt(rendered_benches: list[RenderedBench]) -> BenchmarkItem | None:
    """Return the first rendered prompt sample, if any."""
    for bench in rendered_benches:
        if bench.benchmark_items:
            return bench.benchmark_items[0]
    return None


def _render_bench(
    name: str,
    bench_config: Mapping[str, JsonValue],
    suite_dir: Path,
    tier: str,
    max_items: int | None,
    warnings: list[str],
) -> RenderedBench | None:
    itemset = _tier_itemset(bench_config, tier)
    if itemset is None:
        warnings.append(f"Skipping {name}: tier is not listed: {tier}")
        return None
    item_file = _string(itemset.get("file"))
    if item_file is None:
        warnings.append(f"Skipping {name}: item file is not configured")
        return None
    item_path = suite_dir / item_file
    if not item_path.exists():
        warnings.append(f"Skipping {name}: item file is missing: {item_file}")
        return None
    template = _template(suite_dir, bench_config, name, warnings)
    if template is None:
        return None
    source_items = _read_jsonl(item_path)
    if max_items is not None:
        source_items = source_items[: max(0, max_items)]
    decoding = _decoding(bench_config)
    return RenderedBench(
        name=name,
        source_items=source_items,
        benchmark_items=[
            _benchmark_item(name, item, template, decoding) for item in source_items
        ],
        baseline=_number(bench_config.get("chance_correction_baseline")),
        decoding=decoding,
        item_file=item_file,
    )


def _benchmark_item(
    bench: str,
    item: Mapping[str, JsonValue],
    template: str,
    decoding: JsonObject,
) -> BenchmarkItem:
    benchmark_item: BenchmarkItem = {
        "id": _item_id(item),
        "messages": [{"role": "user", "content": _prompt(bench, item, template)}],
        "sampling_params": {
            key: value for key, value in decoding.items() if key != "max_tokens"
        },
    }
    max_tokens = decoding.get("max_tokens")
    if isinstance(max_tokens, int):
        benchmark_item["max_tokens"] = max_tokens
    return benchmark_item


def _prompt(bench: str, item: Mapping[str, JsonValue], template: str) -> str:
    match bench:
        case "mmlu_pro" | "supergpqa":
            return template.format(
                question=_string(item.get("question")) or "",
                options=_options(item.get("options")),
            )
        case "ifeval" | "ifbench":
            return _string(item.get("prompt")) or ""
        case "genmath" | "amo" | "olymmath_hard":
            return template.format(statement=_string(item.get("statement")) or "")
        case "bfcl":
            return build_bfcl_prompt(item)
        case "bfcl_multi_turn":
            return build_bfcl_multi_turn_prompt(item)
        case "lcb":
            return build_lcb_prompt(item, template)
        case "ruler_32k":
            return build_ruler_prompt(item, template)
        case _:
            return _string(item.get("prompt")) or _string(item.get("question")) or ""


def _read_jsonl(path: Path) -> list[Mapping[str, JsonValue]]:
    items: list[Mapping[str, JsonValue]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if isinstance(data, dict):
            items.append(data)
    return items


def _tier_itemset(
    bench_config: Mapping[str, JsonValue],
    tier: str,
) -> Mapping[str, JsonValue] | None:
    itemsets = bench_config.get("itemsets")
    if not isinstance(itemsets, dict):
        return None
    itemset = itemsets.get(tier)
    return itemset if isinstance(itemset, dict) else None


def _template(
    suite_dir: Path,
    bench_config: Mapping[str, JsonValue],
    bench: str,
    warnings: list[str],
) -> str | None:
    template_name = _string(bench_config.get("template"))
    if template_name is None:
        warnings.append(f"Skipping {bench}: template is not configured")
        return None
    template_path = suite_dir / template_name
    if not template_path.exists():
        warnings.append(f"Skipping {bench}: template is missing: {template_name}")
        return None
    return template_path.read_text(encoding="utf-8")


def _decoding(bench_config: Mapping[str, JsonValue]) -> JsonObject:
    decoding = bench_config.get("decoding")
    return dict(decoding) if isinstance(decoding, dict) else {}


def _item_id(item: Mapping[str, JsonValue]) -> str:
    for key in ("id", "question_id", "key"):
        value = item.get(key)
        if isinstance(value, str | int):
            return str(value)
    return "unknown"


def _options(value: JsonValue | None) -> str:
    options = _list(value)
    return "\n".join(
        f"{_LETTERS[index]}. {option}"
        for index, option in enumerate(options[: len(_LETTERS)])
    )


def _list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _number(value: JsonValue | None) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0
