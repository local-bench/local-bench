from __future__ import annotations

from pathlib import Path
from typing import Final

from build_data_support import (
    JsonObject,
    ensure_cli_src_path,
    slugify,
    bool_value as _bool,
    number_or_none as _number_or_none,
    number_value as _number,
    object_value as _object,
    string_value as _string,
    text_value as _text,
)

ensure_cli_src_path()

from localbench.scoring import (  # noqa: E402
    raw_accuracy_from_signed_percent,
    score_interval_from_percent_ci,
    worst_axis,
)

DEMO_WARNING: Final = "Synthetic demo data - not real measurements. Track 2 will replace this preview run."
DEMO_HASH: Final = "SYNTHETIC-DEMO-NOT-A-MEASUREMENT"
DEFAULT_AXIS_N: Final = {"knowledge": 80, "instruction": 80, "agentic": 80, "math": 119}
AXIS_OFFSETS: Final = {"knowledge": -1.2, "instruction": 0.8, "agentic": 0.0, "math": 0.4}


def build_demo_run(source: JsonObject, *, order: int, benches: tuple[str, ...], index_version: str) -> JsonObject:
    score = _object(source.get("demo_score"), "source.demo_score")
    point = _number(score.get("quality"), "demo_score.quality")
    ci = _number(score.get("ci"), "demo_score.ci")
    tok_s = _number(score.get("tok_s"), "demo_score.tok_s")
    tokens_median = _number_or_none(score.get("tokens_to_answer_median"))
    tokens_p95 = _number_or_none(score.get("tokens_to_answer_p95"))
    n_items = sum(DEFAULT_AXIS_N.get(bench, 80) for bench in benches)
    completion_tokens = int(round((tokens_median or 700.0) * n_items))
    wall_time = completion_tokens / tok_s if tok_s > 0 else None
    family = _string(source["family"], "source.family")
    model_label = _string(source["model_label"], "source.model_label")
    kind = _string(source["kind"], "source.kind")
    quant = _text(source.get("quant_label"))
    lane = _text(source.get("reasoning_lane")) or "answer-only"
    slug = slugify(model_label)
    run_id = f"{slug}__demo-{Path(_string(source['file'], 'source.file')).stem}"
    axes = _demo_axes(point, ci, benches)
    composite = score_interval_from_percent_ci(point, ci)
    totals = {
        "completion_tokens": completion_tokens,
        "completion_tokens_per_second": tok_s,
        "n_errors": 0,
        "n_items": n_items,
        "prompt_tokens": n_items * 80,
        "total_tokens": completion_tokens + n_items * 80,
        "wall_time_seconds": wall_time,
    }
    summary = _demo_manifest_summary(family, model_label, quant, lane)
    detail = {
        "axes": axes,
        "composite": composite,
        "data_warnings": [DEMO_WARNING],
        "demo": True,
        "est_cost_usd": None,
        "index_version": index_version,
        "item_set_hashes": {"synthetic-demo": DEMO_HASH},
        "kind": kind,
        "manifest_summary": summary,
        "model_label": model_label,
        "run_id": run_id,
        "suite_version": "suite-v1",
        "tier": "quick",
        "tokens_to_answer_median": tokens_median,
        "tokens_to_answer_p95": tokens_p95,
        "totals": totals,
        "worst_axis": worst_axis(axes, benches),
    }
    model_row = {
        "axes": axes,
        "composite": composite,
        "demo": True,
        "est_cost_usd": None,
        "hardware": summary["hardware"],
        "lane": lane,
        "n_errors": 0,
        "n_items": n_items,
        "quant_label": quant,
        "run_id": run_id,
        "runtime": summary["runtime"],
        "tier": "quick",
        "tokens_to_answer_median": tokens_median,
        "tokens_to_answer_p95": tokens_p95,
        "tok_s": tok_s,
        "vram_footprint_gb": source["vram_footprint_gb"],
        "wall_time_seconds": wall_time,
    }
    index_row = {
        "axes": axes,
        "best_run_id": run_id,
        "composite": composite,
        "demo": True,
        "est_cost_usd": None,
        "family": family,
        "kind": kind,
        "lane": lane,
        "model_label": model_label,
        "n_runs": 1,
        "ranked": False,
        "replicated": _bool(source["independent_replication"], "source.independent_replication"),
        "slug": slug,
        "tier": "quick",
        "tokens_to_answer_median": tokens_median,
        "tokens_to_answer_p95": tokens_p95,
    }
    return {
        "composite_raw": point / 100.0,
        "detail": detail,
        "family": family,
        "index_row": index_row,
        "kind": kind,
        "model_label": model_label,
        "model_row": model_row,
        "order": order,
        "run_id": run_id,
        "slug": slug,
        "suite_version": "suite-v1",
    }


def _demo_axes(point: float, ci: float, benches: tuple[str, ...]) -> JsonObject:
    axes: JsonObject = {}
    for bench in benches:
        axis_point = _clamp(point + AXIS_OFFSETS.get(bench, 0.0))
        axes[bench] = score_interval_from_percent_ci(axis_point, ci + 0.4) | {
            "n": DEFAULT_AXIS_N.get(bench, 80),
            "n_errors": 0,
            "n_no_answer": 0,
            "raw_accuracy": raw_accuracy_from_signed_percent(bench, axis_point),
        }
    return axes


def _demo_manifest_summary(family: str, model_label: str, quant: str | None, lane: str) -> JsonObject:
    return {
        "caps": {"max_tokens_math": 8192, "max_tokens_mcq": 4096, "thinking_budget": 0},
        "hardware": {
            "cpu": "SYNTHETIC DEMO",
            "gpu": {"driver": None, "name": "SYNTHETIC DEMO footprint estimate", "vram_gb": None, "vram_mb": None},
            "os": "SYNTHETIC DEMO",
            "ram_gb": None,
        },
        "lane": lane,
        "model": {
            "family": family,
            "file_name": f"{slugify(model_label)}.{(quant or 'unknown').lower()}.demo",
            "file_sha256": DEMO_HASH,
            "file_size_bytes": None,
            "format": "synthetic-demo",
            "runtime_reported_model": model_label,
        },
        "quant": quant,
        "runtime": {
            "ctx_len_configured": 8192,
            "kv_cache_quant": None,
            "name": "synthetic-demo-estimate",
            "parallel_slots": None,
            "version": "phase-3-preview",
        },
        "sampling": {
            "by_bench": {
                "agentic": {"max_tokens": 4096, "temperature": 0},
                "instruction": {"max_tokens": 1280, "temperature": 0},
                "knowledge": {"max_tokens": 4096, "temperature": 0},
                "math": {"max_tokens": 8192, "temperature": 0},
            },
            "temperature": 0,
            "thinking_mode": "n/a",
        },
        "thinking_mode": "n/a",
    }


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))
