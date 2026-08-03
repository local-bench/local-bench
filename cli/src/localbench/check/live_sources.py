from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.check.live_runner import LiveItem
from localbench.check.live_upstream import load_upstream_sources
from localbench.check.types import CheckError
from localbench.checkset.input_runs import read_json, read_jsonl
from localbench.submissions.canon import canonical_json_bytes

PINNED_SMOKE_ITEMS: Final = (
    "ifbench-066",
    "amo-016",
    "tc-json-bfcl-025",
    "stateful-booking-ledger-000",
)
_SMOKE_MODULES: Final = {
    "ifbench-066": "instruction",
    "amo-016": "math",
    "tc-json-bfcl-025": "tools-single",
    "stateful-booking-ledger-000": "tools-stateful",
}


def load_smoke_items(repo_root: Path, manifest_path: Path) -> tuple[LiveItem, ...]:
    root = repo_root.resolve()
    manifest = read_json(manifest_path)
    published = _published_items(manifest)
    local = _local_sources(root, manifest)
    selected: list[LiveItem] = []
    for item_id in PINNED_SMOKE_ITEMS:
        module = _SMOKE_MODULES[item_id]
        source = local.get(item_id)
        if source is None:
            raise CheckError(f"pinned smoke source item is missing: {item_id}")
        _verify_published(module, item_id, source, published)
        selected.append(LiveItem(item_id, module, source))
    gates = manifest.get("sanity_gates")
    definitions = gates.get("definitions") if isinstance(gates, dict) else None
    if not isinstance(definitions, list) or len(definitions) != 18:
        raise CheckError("manifest must contain all 18 sanity-gate definitions")
    for definition in definitions:
        if not isinstance(definition, dict):
            raise CheckError("manifest sanity-gate definition is invalid")
        item_id = _required_str(definition, "item_id")
        _verify_published("sanity-gates", item_id, definition, published)
        selected.append(LiveItem(item_id, "sanity-gates", definition))
    return tuple(selected)


def load_live_items(repo_root: Path, manifest_path: Path) -> tuple[LiveItem, ...]:
    manifest = read_json(manifest_path)
    published = _published_items(manifest)
    sources = _all_local_sources(repo_root.resolve(), manifest)
    sources.update(load_upstream_sources(manifest))
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise CheckError("manifest modules are missing")
    items: list[LiveItem] = []
    for module in modules:
        if not isinstance(module, dict):
            raise CheckError("manifest contains an invalid module")
        module_name = _required_str(module, "name")
        raw_items = module.get("items")
        if not isinstance(raw_items, list):
            raise CheckError(f"manifest module {module_name!r} has no items")
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise CheckError(f"manifest module {module_name!r} has an invalid item")
            item_id = _required_str(raw_item, "item_id")
            source = sources.get(item_id)
            if source is None:
                raise CheckError(f"live source item is missing: {module_name}/{item_id}")
            _verify_published(module_name, item_id, source, published)
            items.append(LiveItem(item_id, module_name, source))
    if len(items) != 594:
        raise CheckError(f"full live item resolution produced {len(items)} items, expected 594")
    return tuple(items)


def _local_sources(repo_root: Path, manifest: JsonObject) -> dict[str, JsonObject]:
    sources: dict[str, JsonObject] = {}
    for relative in (
        "suite/v2/ifbench.jsonl",
        "suite/v2/amo.jsonl",
        "suite/v2/olymmath_hard.jsonl",
        "suite/v2/tc_json_v1.jsonl",
    ):
        path = repo_root / relative
        if not path.is_file():
            raise CheckError(f"live check source file is missing: {path}")
        for row in read_jsonl(path):
            item_id = row.get("id")
            if isinstance(item_id, str):
                sources[item_id] = row
    stateful = manifest.get("stateful")
    instances = stateful.get("instances") if isinstance(stateful, dict) else None
    if not isinstance(instances, list):
        raise CheckError("manifest stateful instances are missing")
    for instance in instances:
        if isinstance(instance, dict):
            sources[_required_str(instance, "item_id")] = instance
    return sources


def _all_local_sources(repo_root: Path, manifest: JsonObject) -> dict[str, JsonObject]:
    sources: dict[str, JsonObject] = {}
    for name in ("bigcodebench_hard", "ifbench", "olymmath_hard", "amo", "tc_json_v1"):
        path = repo_root / "suite" / "v2" / f"{name}.jsonl"
        if not path.is_file():
            raise CheckError(f"live check source file is missing: {path}")
        for row in read_jsonl(path):
            item_id = row.get("id")
            if isinstance(item_id, str):
                sources[item_id] = row
    stateful = manifest.get("stateful")
    instances = stateful.get("instances") if isinstance(stateful, dict) else None
    gates = manifest.get("sanity_gates")
    definitions = gates.get("definitions") if isinstance(gates, dict) else None
    for records, label in ((instances, "stateful instances"), (definitions, "sanity gates")):
        if not isinstance(records, list):
            raise CheckError(f"manifest {label} are missing")
        for record in records:
            if isinstance(record, dict):
                sources[_required_str(record, "item_id")] = record
    return sources


def _published_items(manifest: JsonObject) -> dict[tuple[str, str], str]:
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise CheckError("manifest modules are missing")
    published: dict[tuple[str, str], str] = {}
    for module in modules:
        if not isinstance(module, dict):
            continue
        name = module.get("name")
        items = module.get("items")
        if not isinstance(name, str) or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id")
            digest = item.get("content_sha256")
            if isinstance(item_id, str) and isinstance(digest, str):
                published[(name, item_id)] = digest
    return published


def _verify_published(
    module: str,
    item_id: str,
    source: JsonObject,
    published: dict[tuple[str, str], str],
) -> None:
    expected = published.get((module, item_id))
    if expected is None:
        raise CheckError(f"pinned smoke item is absent from the manifest: {module}/{item_id}")
    embedded = source.get("content_sha256")
    actual = embedded if isinstance(embedded, str) else hashlib.sha256(canonical_json_bytes(source)).hexdigest()
    if actual != expected:
        raise CheckError(f"pinned smoke item content hash mismatch: {module}/{item_id}")


def _required_str(source: JsonObject, key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"live source field {key!r} is missing")
    return value
