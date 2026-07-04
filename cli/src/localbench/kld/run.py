"""Two-pass KLD ladder runner (replaces the ad-hoc gemma_kld.sh).

Pass 1 runs the full-precision (or Q8-proxy) reference with `--kl-divergence-base`
to dump its logits; pass 2 scores each quant against that baseline with
`--kl-divergence`. Each quant's panel is parsed (parse.py) and paired with task
churn (churn.py) into one model-page drift record. See METHODOLOGY-v1.2 §6/§10.

The subprocess `runner` is injected so the orchestration + assembly are testable
against captured llama-perplexity output without the binary or GGUF weights.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from localbench.kld.churn import ChurnResult, compute_churn
from localbench.kld.parse import KldStats, parse_kld_log

Runner = Callable[[list[str]], str]

SCHEMA: str = "localbench-kld-v1"


class LlamaPerplexityError(RuntimeError):
    """Raised when a llama-perplexity invocation fails."""


def default_runner(cmd: list[str]) -> str:
    """Run a command, returning combined stdout+stderr; raise on non-zero exit."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise LlamaPerplexityError(
            f"llama-perplexity exited {result.returncode}: {' '.join(cmd)}\n{output[-2000:]}"
        )
    return output


def run_kld_ladder(
    *,
    llama_perplexity: Path,
    reference: Path,
    quants: dict[str, Path],
    calib: Path,
    model_label: str,
    reference_label: str,
    work_dir: Path,
    ngl: int = 99,
    churn_reference: Path | None = None,
    churn_quants: dict[str, Path] | None = None,
    runner: Runner = default_runner,
) -> dict[str, object]:
    """Run the reference baseline + each quant's KLD pass, assemble the drift record."""
    work_dir.mkdir(parents=True, exist_ok=True)
    base_kld = work_dir / "reference.kld"
    lp = str(llama_perplexity)
    runner([lp, "-m", str(reference), "-f", str(calib), "-ngl", str(ngl),
            "--kl-divergence-base", str(base_kld)])

    churn_ref_record = _load_json(churn_reference) if churn_reference else None
    quant_drifts: dict[str, _QuantDrift] = {}
    for label, quant_path in quants.items():
        text = runner([lp, "-m", str(quant_path), "-f", str(calib), "-ngl", str(ngl),
                       "--kl-divergence-base", str(base_kld), "--kl-divergence"])
        (work_dir / f"kld-{label}.log").write_text(text, encoding="utf-8")
        churn = _churn_for(label, churn_ref_record, churn_quants)
        quant_drifts[label] = _QuantDrift(parse_kld_log(text), churn)
    return build_drift(model_label, reference_label, _calib_info(calib), quant_drifts)


class _QuantDrift:
    __slots__ = ("kld", "churn")

    def __init__(self, kld: KldStats, churn: ChurnResult | None) -> None:
        self.kld = kld
        self.churn = churn


def build_drift(
    model_label: str,
    reference_label: str,
    calib: dict[str, object],
    quants: dict[str, _QuantDrift],
) -> dict[str, object]:
    """Assemble the model-page drift record (pure; given parsed stats + churn)."""
    return {
        "schema": SCHEMA,
        "model": model_label,
        "reference": reference_label,
        "calib": calib,
        "quants": {
            label: {
                "kld": drift.kld.to_dict(),
                "churn": drift.churn.to_dict() if drift.churn is not None else None,
            }
            for label, drift in quants.items()
        },
    }


def _churn_for(
    label: str,
    reference_record: dict[str, object] | None,
    churn_quants: dict[str, Path] | None,
) -> ChurnResult | None:
    if reference_record is None or churn_quants is None or label not in churn_quants:
        return None
    return compute_churn(reference_record, _load_json(churn_quants[label]))


def _calib_info(calib: Path) -> dict[str, object]:
    data = calib.read_bytes()
    return {
        "path": str(calib),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"run record is not a JSON object: {path}")
    return data
