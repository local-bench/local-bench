from __future__ import annotations

from typing import Final

# Per-bench chance baselines for the paired-comparison/bootstrap default path. These MUST match the
# corresponding suite.json `chance_correction_baseline` (run scoring uses the suite value directly; only
# paired_delta defaults read here). mmlu_pro = selected-set mean 1/n_options over the emitted suite-v1 set.
CHANCE_BASELINES: Final[dict[str, float]] = {
    "mmlu_pro": 0.10918253968253969,
    "ifeval": 0.0,
    "genmath": 0.0,
}


class ChanceBaselineError(ValueError):
    pass


def signed_score(raw: float, *, chance: float) -> float:
    """Return (raw - chance) / (1 - chance), without inference clamping.

    Inference and CIs use this signed value; display_clamp is cosmetic only.
    """
    if chance >= 1.0:
        raise ChanceBaselineError("chance baseline must be less than 1")
    return (raw - chance) / (1.0 - chance)


def display_clamp(score: float) -> float:
    return min(1.0, max(0.0, score))


def chance_for_bench(bench: str) -> float:
    return CHANCE_BASELINES.get(bench, 0.0)


def signed_delta(raw_delta: float, *, chance: float) -> float:
    """Return the chance-corrected difference for a raw accuracy delta.

    A signed score difference is ((a - c) / (1 - c)) - ((b - c) / (1 - c)),
    so the chance terms cancel and leave (a - b) / (1 - c). Applying this
    per item is therefore equivalent to differencing aggregate signed scores.
    """
    if chance >= 1.0:
        raise ChanceBaselineError("chance baseline must be less than 1")
    return raw_delta / (1.0 - chance)
