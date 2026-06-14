from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final

from build_data_support import (
    JsonObject,
    bool_value as _bool,
    number_or_none as _number_or_none,
    number_value as _number,
    object_value as _object,
    string_value as _string,
    text_value as _text,
)

ROOT: Final = Path(__file__).resolve().parents[1]
CLI_SRC: Final = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from localbench.scoring import (  # noqa: E402
    raw_accuracy_from_signed_percent,
    score_interval_from_percent_ci,
    worst_axis,
)

INDEX_VERSION: Final = "index-v0"
DEMO_WARNING: Final = "Synthetic demo data - not real measurements. Track 2 will replace this preview run."
DEMO_HASH: Final = "SYNTHETIC-DEMO-NOT-A-MEASUREMENT"
DEFAULT_AXIS_N: Final = {"genmath": 40, "ifeval": 100, "mmlu_pro": 112}
AXIS_OFFSETS: Final = {"genmath": 0.4, "ifeval": 0.8, "mmlu_pro": -1.2}


def build_demo_run(source: JsonObject, *, order: int, benches: tuple[str, ...]) -> JsonObject:
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
    slug = _slugify(model_label)
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
        "index_version": INDEX_VERSION,
        "item_set_hashes": {"synthetic-demo": DEMO_HASH},
        "kind": kind,
        "manifest_summary": summary,
        "model_label": model_label,
        "run_id": run_id,
        "suite_version": "suite-v0",
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
        "suite_version": "suite-v0",
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
            "file_name": f"{_slugify(model_label)}.{(quant or 'unknown').lower()}.demo",
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
                "genmath": {"max_tokens": 8192, "temperature": 0},
                "ifeval": {"max_tokens": 1280, "temperature": 0},
                "mmlu_pro": {"max_tokens": 4096, "temperature": 0},
            },
            "temperature": 0,
            "thinking_mode": "n/a",
        },
        "thinking_mode": "n/a",
    }


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "model"


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))
