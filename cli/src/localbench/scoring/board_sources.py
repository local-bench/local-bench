"""Curation loading for board_v1 generation."""

from __future__ import annotations

from pathlib import Path

from localbench._types import JsonValue
from localbench.scoring.board_support import (
    GEMMA_FALLBACK_FILE,
    bool_or_false,
    list_value,
    object_value,
    read_json,
    string_value,
    text_value,
)
from localbench.scoring.board_types import BoardBuildError, CuratedSource


def load_sources(path: Path) -> list[CuratedSource]:
    raw = read_json(path)
    sources: list[CuratedSource] = []
    for index, item in enumerate(list_value(raw, str(path))):
        source = _source(item, index)
        if source is not None:
            sources.append(source)
    if not any(source["file"].replace("\\", "/").endswith(GEMMA_FALLBACK_FILE) for source in sources):
        sources.append({
            "agentic_file": "cli/runs/agentic/gemma4-31b-Q4_K_M.scored.run1.json",
            "kind": "community",
            "family": "Gemma 4",
            "model_id": "google/gemma-4-31B-it",
            "model_label": "Gemma 4 31B IT",
            "publisher": None,
            "gguf_repo": None,
            "quant_label": "Q4_K_M",
            "recommended": False,
            "file": GEMMA_FALLBACK_FILE,
            # v1-era fallback run: keep its own era's lane, not the current board scope.
            "reasoning_lane": "capped-thinking",
            "independent_replication": False,
        })
    _validate_recommended(sources)
    return sources


def _source(value: JsonValue, index: int) -> CuratedSource | None:
    item = object_value(value, f"curation[{index}]")
    file_name = text_value(item.get("file"))
    if file_name is None:
        return None
    kind = string_value(item.get("kind"), f"curation[{index}].kind")
    if kind not in {"anchor", "community"}:
        raise BoardBuildError(f"curation[{index}].kind must be anchor or community")
    return {
        "agentic_file": text_value(item.get("agentic_file")),
        "family": string_value(item.get("family"), f"curation[{index}].family"),
        "file": file_name,
        "independent_replication": bool_or_false(item.get("independent_replication")),
        "kind": kind,
        "model_id": text_value(item.get("model_id")),
        "model_label": string_value(item.get("model_label"), f"curation[{index}].model_label"),
        "publisher": text_value(item.get("publisher")),
        "gguf_repo": text_value(item.get("gguf_repo")),
        "quant_label": text_value(item.get("quant_label")),
        "recommended": bool_or_false(item.get("recommended")),
        "reasoning_lane": text_value(item.get("reasoning_lane")),
    }


def _validate_recommended(sources: list[CuratedSource]) -> None:
    groups: dict[str, int] = {}
    for source in sources:
        if source["recommended"]:
            key = (source["model_id"] or source["model_label"]).lower()
            groups[key] = groups.get(key, 0) + 1
            if groups[key] > 1:
                raise BoardBuildError(f"{source['family']} must have at most one recommended quant")
