"""KLD quant-drift measurement (METHODOLOGY-v1.2 §6).

`localbench kld` runs the two-pass llama.cpp llama-perplexity ladder, parses the
KL-divergence panels, pairs them with task churn, and emits one model-page drift
record. KLD is a distribution-DRIFT signal vs a full-precision reference, NOT a
task score — always shown beside accuracy + churn + VRAM + speed.
"""

from __future__ import annotations

from localbench.kld.churn import ChurnResult, compute_churn
from localbench.kld.parse import KldParseError, KldStats, parse_kld_log
from localbench.kld.run import (
    SCHEMA,
    LlamaPerplexityError,
    build_drift,
    default_runner,
    run_kld_ladder,
)

__all__ = [
    "SCHEMA",
    "ChurnResult",
    "KldParseError",
    "KldStats",
    "LlamaPerplexityError",
    "build_drift",
    "compute_churn",
    "default_runner",
    "parse_kld_log",
    "run_kld_ladder",
]
