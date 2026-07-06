from __future__ import annotations

from typing import Final

from build_data_support import (
    JsonObject,
    JsonValue,
    bool_value,
    list_value,
    number_or_none,
    object_or_empty,
    object_value,
    string_value,
    text_value,
)

CATALOG_FILENAME: Final = "model_catalog.json"
SHELL_KIND: Final = "community"
SHELL_LANE: Final = "answer-only"
SHELL_SCORE_STATUS: Final = "missing"


def catalog_entries(raw: JsonValue) -> list[JsonObject]:
    return [_catalog_entry(entry, index) for index, entry in enumerate(_catalog_items(raw))]


def _catalog_items(raw: JsonValue) -> list[JsonValue]:
    if isinstance(raw, list):
        return raw
    catalog = object_value(raw, "model_catalog")
    return list_value(catalog.get("models"), "model_catalog.models")


def catalog_index_row(entry: JsonObject) -> JsonObject:
    return {
        "axes": {},
        "best_run_id": None,
        "catalog_id": entry["id"],
        "composite": None,
        "demo": False,
        "est_cost_usd": None,
        "family": entry["family"],
        "kind": SHELL_KIND,
        "lane": SHELL_LANE,
        "model_label": entry["display_name"],
        "n_runs": 0,
        "ranked": False,
        "replicated": False,
        "score_status": SHELL_SCORE_STATUS,
        "slug": entry["slug"],
        "tier": None,
        "tokens_to_answer_median": None,
        "tokens_to_answer_p95": None,
    }


def catalog_model_payload(entry: JsonObject, runs: list[JsonObject]) -> JsonObject:
    quant_rows = [catalog_quant_row(entry, quant, runs) for quant in list_value(entry["quants"], "catalog.quants")]
    catalog_labels = {text_value(row.get("quant_label")) for row in quant_rows}
    extra_rows = [
        object_value(run["model_row"], "run.model_row").copy()
        for run in runs
        if text_value(object_value(run["model_row"], "run.model_row").get("quant_label")) not in catalog_labels
    ]
    return {
        "catalog_id": entry["id"],
        "base_model": entry["base_model"],
        "demo": False,
        "family": entry["family"],
        "gguf_repo": entry["gguf_repo"],
        "kind": SHELL_KIND,
        "license": entry["license"],
        "model_kind": entry["model_kind"],
        "model_label": entry["display_name"],
        "org": entry["org"],
        "runs": quant_rows + extra_rows,
        "slug": entry["slug"],
    }


def catalog_quant_row(entry: JsonObject, quant: JsonValue, runs: list[JsonObject]) -> JsonObject:
    quant_entry = object_value(quant, "catalog.quant")
    label = string_value(quant_entry.get("label"), "catalog.quant.label")
    attached = _run_for_quant(runs, label)
    if attached is not None:
        row = object_value(attached["model_row"], "run.model_row").copy()
        row["bpw"] = number_or_none(quant_entry.get("bpw"))
        row["file_gb"] = number_or_none(quant_entry.get("file_gb"))
        row["vram_required_gb_8k"] = number_or_none(quant_entry.get("vram_gb_8k"))
        row["score_status"] = "measured"
        return row
    return {
        "axes": {},
        "bpw": number_or_none(quant_entry.get("bpw")),
        "composite": None,
        "demo": False,
        "est_cost_usd": None,
        "file_gb": number_or_none(quant_entry.get("file_gb")),
        "hardware": {"cpu": None, "gpu": None, "os": None, "ram_gb": None},
        "lane": SHELL_LANE,
        "n_errors": 0,
        "n_items": 0,
        "quant_label": label,
        "ranked": False,
        "run_id": None,
        "runtime": {
            "ctx_len_configured": None,
            "kv_cache_quant": None,
            "name": None,
            "parallel_slots": None,
            "version": None,
        },
        "score_status": SHELL_SCORE_STATUS,
        "tier": None,
        "tok_s": None,
        "tokens_to_answer_median": None,
        "tokens_to_answer_p95": None,
        "vram_footprint_gb": number_or_none(quant_entry.get("file_gb")),
        "vram_required_gb_8k": number_or_none(quant_entry.get("vram_gb_8k")),
        "wall_time_seconds": None,
    }


def catalog_key(entry: JsonObject) -> str:
    return string_value(entry.get("id"), "catalog.id").lower()


def catalog_slug(entry: JsonObject) -> str:
    return string_value(entry.get("slug"), "catalog.slug")


def run_catalog_key(run: JsonObject) -> str | None:
    value = text_value(run.get("catalog_id"))
    return value.lower() if value is not None else None


def _catalog_entry(value: JsonValue, index: int) -> JsonObject:
    item = object_value(value, f"model_catalog[{index}]")
    return {
        "base_model": text_value(item.get("base_model")),
        "display_name": string_value(item.get("display_name"), f"model_catalog[{index}].display_name"),
        "family": string_value(item.get("family"), f"model_catalog[{index}].family"),
        "gguf_repo": text_value(item.get("gguf_repo")),
        "id": string_value(item.get("id"), f"model_catalog[{index}].id"),
        "is_moe": bool_value(item.get("is_moe"), f"model_catalog[{index}].is_moe"),
        "license": text_value(item.get("license")),
        "model_kind": text_value(item.get("model_kind")) or "base",
        "org": text_value(item.get("org")),
        "popularity": object_or_empty(item.get("popularity")),
        "quants": list_value(item.get("quants"), f"model_catalog[{index}].quants"),
        "reasoning_capable": bool_value(item.get("reasoning_capable"), f"model_catalog[{index}].reasoning_capable"),
        "slug": string_value(item.get("slug"), f"model_catalog[{index}].slug"),
    }


def _run_for_quant(runs: list[JsonObject], quant_label: str) -> JsonObject | None:
    for run in runs:
        row = object_value(run["model_row"], "run.model_row")
        if text_value(row.get("quant_label")) == quant_label:
            return run
    return None
