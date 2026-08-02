from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from localbench.checkset.models import (
    ChecksetBuildError,
    JsonObject,
    JsonValue,
    ModuleRecord,
)
from localbench.submissions.canon import canonical_json_bytes

SPEC_SHA256: Final = "0c97d3ab679b99fc07506067d777e5ff14d13c887cbcf7617ceba57b4f196168"
LOCKED_UTC: Final = "2026-08-02T00:00:00Z"
LOCKED_COUNTS: Final = {
    "knowledge": 198,
    "coding": 96,
    "instruction": 120,
    "math": 60,
    "tools-single": 54,
    "tools-stateful": 48,
    "sanity-gates": 18,
}


def _policy_blocks() -> JsonObject:
    return {
        "aggregation": {
            "id": "check-weights-v1",
            "weights": {"knowledge": 0.25, "coding": 0.25, "instruction": 0.20, "tools": 0.20, "math": 0.10},
            "tools_subweights": {"single": 0.12, "stateful": 0.08},
            "chance_correction": "signed-mcq-v1",
            "report_worst_axis": True,
        },
        "determinism_canaries": {
            "count": 3,
            "classes": ["short-form", "tool-or-stateful", "long-context"],
            "independent_server_restarts": True,
            "tolerance": 0,
        },
        "drop_bounds": {"formula": "max(0.03, 1.5 * max_good_quant_drop)", "equality_passes": True},
        "failure_policy": {
            "model_or_protocol": "score_wrong",
            "infrastructure": "invalidate_or_resume_without_altering_prior_records",
            "outcome_conditioned_reruns": False,
            "denominator_reduction": False,
        },
        "gate_taxonomy": {
            "validity": ["stop-token", "budget-control", "template-canary", "determinism"],
            "behavioral": ["repetition", "long-context-needle"],
        },
        "kld": {
            "direction": "KL(reference||candidate)",
            "corpus": "sha-pinned-wikitext-2-test",
            "tokens": 262144,
            "context_tokens": 4096,
            "overlap": 0,
            "fresh_context_per_segment": True,
            "accumulation": "fp32",
            "reported": ["mean", "p95", "p99", "top-token-agreement-rate"],
            "significant_figures": 4,
            "band_comparison": "exact-on-rounded-values",
            "verdict_effect": "none",
        },
        "unsupported_policy": "reference-family-policy-only; candidate-only inability is failure; no silent renormalization",
    }


def build_t2_scaffold(
    output: Path,
    *,
    modules: Sequence[ModuleRecord],
    knowledge_status: str,
    knowledge_error: str | None,
    pool_exclusions: Sequence[JsonObject] = (),
    pending_dependencies: Sequence[str] = ("tools-stateful", "sanity-gates"),
    source_metadata: JsonObject | None = None,
) -> JsonObject:
    document = _policy_blocks()
    document.update(
        {
            "schema_version": "localbench-check-set-manifest-v1",
            "edition": "check-set-v1",
            "draft": True,
            "status": "pending_dependencies",
            "pending_dependencies": list(pending_dependencies),
            "modules": [module.as_json() for module in modules],
            "knowledge": {"status": knowledge_status, "error": knowledge_error},
            "pool_exclusions": list(pool_exclusions),
            "stateful": {"status": "pending_t3", "templates": [], "instances": [], "spares_ordered": [], "cluster_map": {}},
            "preregistration": {"spec_sha256": SPEC_SHA256, "locked_utc": LOCKED_UTC},
            "source_metadata": source_metadata or {},
        }
    )
    _write_canonical(output, document, sidecar=False)
    return document


def emit_manifest(
    output: Path,
    *,
    modules: Sequence[ModuleRecord],
    stateful: JsonObject,
    pool_exclusions: Sequence[JsonObject] = (),
) -> JsonObject:
    counts = {module.name: module.scored for module in modules}
    scored = sum(counts.get(name, 0) for name in LOCKED_COUNTS if name != "sanity-gates")
    gates = counts.get("sanity-gates", 0)
    raw_spares = stateful.get("spares_ordered")
    spares = len(raw_spares) if isinstance(raw_spares, list) else -1
    if counts != LOCKED_COUNTS or (scored, gates, spares) != (576, 18, 6):
        raise ChecksetBuildError("Manifest must contain 576 scored + 18 gates + 6 spares = 600 authored items.")
    document = _policy_blocks()
    document.update(
        {
            "schema_version": "localbench-check-set-manifest-v1",
            "edition": "check-set-v1",
            "draft": True,
            "status": "complete-draft",
            "modules": [module.as_json() for module in modules],
            "pool_exclusions": list(pool_exclusions),
            "stateful": stateful,
            "preregistration": {"spec_sha256": SPEC_SHA256, "locked_utc": LOCKED_UTC},
        }
    )
    _write_canonical(output, document, sidecar=True)
    return document


def _write_canonical(output: Path, document: JsonValue, *, sidecar: bool) -> None:
    data = canonical_json_bytes(document) + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    if sidecar:
        digest = hashlib.sha256(data).hexdigest()
        output.with_name(f"{output.name}.sha256").write_text(
            f"{digest}  {output.name}\n",
            encoding="ascii",
            newline="\n",
        )
