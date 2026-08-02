from __future__ import annotations

from localbench.checkset.kld import KLD_CORPUS
from localbench.checkset.models import JsonObject
from localbench.checkset.select import SELECTION_SEED


def policy_blocks() -> JsonObject:
    margins: JsonObject = {"knowledge": 3.0, "instruction": 4.0, "coding": 5.0, "math": 6.0, "tools": 4.0}
    disagreement_floors: JsonObject = {
        "knowledge": 0.03,
        "instruction": 0.03,
        "coding": 0.03,
        "math": 0.03,
        "tools": 0.06,
    }
    drop_floors: JsonObject = {area: 0.03 for area in margins}
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
        "disagreement_bounds": {
            "formula": "max(area_floor, 1.5 * max_good_quant_disagreement)",
            "floors": disagreement_floors,
            "good_quant_set": [],
            "status": "uncalibrated",
            "equality_passes": True,
        },
        "drop_bounds": {
            "formula": "max(0.03, 1.5 * max_good_quant_drop)",
            "floors": drop_floors,
            "good_quant_set": [],
            "status": "uncalibrated",
            "equality_passes": True,
        },
        "execution": {
            "edition": "LCE-1",
            "llama_cpp_build": "b10076",
            "llama_cpp_commit": "305ba51",
            "cuda_version": "13.3",
            "server_flags": ["-ctk", "f16", "-ctv", "f16", "--fit", "off", "-lv", "4"],
            "batch_size": 1,
            "context_tokens": 32768,
            "temperature": 0,
            "seed": 1234,
            "think_budget_tokens": 4096,
            "answer_budgets": {
                "mcq": 512,
                "ifbench": 1024,
                "math": 1536,
                "coding": 2048,
                "tools-single": 512,
                "tools-stateful-per-turn": 512,
            },
            "headroom_tokens": 256,
            "prompt_rendering": "cli-owned",
        },
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
            "corpus": dict(KLD_CORPUS),
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
        "statistics": {
            "paired_measures": ["drop", "leapfrog", "delta", "disagreement"],
            "margins_pp": margins,
            "bounds": {
                "disagreement": "disagreement_bounds",
                "drop": "drop_bounds",
            },
            "bootstrap": {
                "method": "centered-studentized-two-sided-simultaneous-max-statistic",
                "resamples": 100000,
                "seed": SELECTION_SEED,
                "cluster_resampling": {"stateful": "template", "instruction": "prompt", "coding": "task"},
                "fallback": "all-five-areas-bonferroni-tango-on-zero-variance-or-discordance",
            },
            "practical_margin_pp": 2.0,
        },
        "unsupported_policy": "reference-family-policy-only; candidate-only inability is failure; no silent renormalization",
    }
