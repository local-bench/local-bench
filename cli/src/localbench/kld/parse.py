"""Parse the panels emitted by llama.cpp `llama-perplexity --kl-divergence`.

The KLD pass prints a `KL divergence statistics` panel (Mean/Median/percentile/
Min/Max KLD) and a `Token probability statistics` panel (Same-top-p, RMS Δp). This
module turns that text into a `KldStats` record. See METHODOLOGY-v1.2 §6: the model
page headlines median + q99 KLD + Same-top-p (drift, NOT a task score).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_FLOAT = r"(-?\d+(?:\.\d+)?)"


class KldParseError(ValueError):
    """Raised when the llama-perplexity KLD panels cannot be parsed."""


@dataclass(frozen=True, slots=True)
class KldStats:
    """One quant's distribution-drift vs a full-precision reference.

    KLD values are nats; `same_top_p` and `rms_dp` are percentages (0-100), as
    printed by llama-perplexity. Lower = more faithful to the reference.
    """

    mean_kld: float
    median_kld: float
    q90_kld: float
    q95_kld: float
    q99_kld: float
    q999_kld: float
    max_kld: float
    min_kld: float
    same_top_p: float
    rms_dp: float
    mean_kld_stderr: float | None = None
    same_top_p_stderr: float | None = None
    mean_ppl_quant: float | None = None
    mean_ppl_base: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


def parse_kld_log(text: str) -> KldStats:
    """Parse a full llama-perplexity `--kl-divergence` pass into KldStats."""
    percentiles = _kld_percentiles(text)
    mean_kld, mean_kld_stderr = _value_with_stderr(text, r"Mean\s+KLD")
    same_top_p, same_top_p_stderr = _percent_with_stderr(text, r"Same\s+top\s+p")
    rms_dp, _ = _percent_with_stderr(text, r"RMS[^:\n]*")
    return KldStats(
        mean_kld=mean_kld,
        median_kld=_value(text, r"Median\s+KLD"),
        q90_kld=_require_percentile(percentiles, 90.0),
        q95_kld=_require_percentile(percentiles, 95.0),
        q99_kld=_require_percentile(percentiles, 99.0),
        q999_kld=_require_percentile(percentiles, 99.9),
        max_kld=_value(text, r"Maximum\s+KLD"),
        min_kld=_value(text, r"Minimum\s+KLD"),
        same_top_p=same_top_p,
        rms_dp=rms_dp,
        mean_kld_stderr=mean_kld_stderr,
        same_top_p_stderr=same_top_p_stderr,
        mean_ppl_quant=_optional_value(text, r"Mean\s+PPL\(Q\)"),
        mean_ppl_base=_optional_value(text, r"Mean\s+PPL\(base\)"),
    )


def _kld_percentiles(text: str) -> dict[float, float]:
    return {
        float(label): float(value)
        for label, value in re.findall(rf"(\d+(?:\.\d+)?)%\s+KLD:\s*{_FLOAT}", text)
    }


def _require_percentile(percentiles: dict[float, float], label: float) -> float:
    if label not in percentiles:
        raise KldParseError(f"missing {label}% KLD percentile in llama-perplexity output")
    return percentiles[label]


def _value(text: str, label: str) -> float:
    match = re.search(rf"{label}:\s*{_FLOAT}", text)
    if match is None:
        raise KldParseError(f"missing '{label}' in llama-perplexity output")
    return float(match.group(1))


def _optional_value(text: str, label: str) -> float | None:
    match = re.search(rf"{label}\s*:\s*{_FLOAT}", text)
    return float(match.group(1)) if match else None


def _value_with_stderr(text: str, label: str) -> tuple[float, float | None]:
    match = re.search(rf"{label}:\s*{_FLOAT}(?:\s*±\s*{_FLOAT})?", text)
    if match is None:
        raise KldParseError(f"missing '{label}' in llama-perplexity output")
    stderr = match.group(2)
    return float(match.group(1)), (float(stderr) if stderr is not None else None)


def _percent_with_stderr(text: str, label: str) -> tuple[float, float | None]:
    match = re.search(rf"{label}:\s*{_FLOAT}(?:\s*±\s*{_FLOAT})?\s*%", text)
    if match is None:
        raise KldParseError(f"missing '{label}' percent in llama-perplexity output")
    stderr = match.group(2)
    return float(match.group(1)), (float(stderr) if stderr is not None else None)
