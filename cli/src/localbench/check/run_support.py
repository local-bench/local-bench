from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from localbench._types import JsonObject, JsonValue
from localbench.check.budget import generation_parameters
from localbench.check.types import CheckError


def mock_items(manifest: JsonObject) -> list[JsonObject]:
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise CheckError("check-set manifest has no modules")
    results: list[JsonObject] = []
    for module in modules:
        if not isinstance(module, dict):
            raise CheckError("check-set manifest contains an invalid module")
        module_name = _required_str(module, "name")
        raw_items = module.get("items")
        if not isinstance(raw_items, list):
            raise CheckError(f"manifest module {module_name!r} has no items")
        params = generation_parameters(module_name)
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise CheckError(f"manifest module {module_name!r} has an invalid item")
            item_id = _required_str(raw_item, "item_id")
            digest = hashlib.sha256(f"{module_name}:{item_id}".encode()).digest()
            token_ids: list[JsonValue] = [value for value in digest[:4]]
            generation: JsonObject = {
                "finish_reason": "stop",
                "parsed_tool_calls": [],
                "protocol_flag": None,
                "text": f"mock:{item_id}",
                "token_ids": token_ids,
            }
            results.append(
                {
                    "candidate": {
                        **generation,
                        "mock_correct": True if module_name == "sanity-gates" else digest[0] % 17 != 0,
                    },
                    "generation_parameters": params,
                    "item_id": item_id,
                    "module": module_name,
                    "reference": {**generation, "mock_correct": True},
                }
            )
    return results


def read_items(path: Path) -> list[JsonObject]:
    return [read_json_line(line) for line in path.read_text(encoding="utf-8").splitlines()]


def read_json_line(line: str) -> JsonObject:
    parsed = cast(object, json.loads(line))
    if not isinstance(parsed, dict):
        raise CheckError("run item row must be a JSON object")
    return cast(JsonObject, parsed)


def live_repo_root(manifest_path: Path) -> Path:
    resolved = manifest_path.resolve()
    candidates = (resolved.parent.parent, Path.cwd().resolve())
    for candidate in candidates:
        if (candidate / "suite" / "v2").is_dir() and (candidate / "checkset").is_dir():
            return candidate
    raise CheckError("live checks require a repository checkout containing suite/v2 and checkset")


def _required_str(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"required check field {key!r} is missing")
    return value
