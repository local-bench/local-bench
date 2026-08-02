from __future__ import annotations

import math
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.check.types import CheckError
from localbench.kld.parse import parse_kld_log
from localbench.submissions.canon import sha256_file, write_json_file

KLD_TOKENS: Final = 262_144
KLD_CONTEXT_TOKENS: Final = 4_096
KLD_SEGMENTS: Final = KLD_TOKENS // KLD_CONTEXT_TOKENS
_REQUIRED_HELP_FLAGS: Final = (
    "--kl-divergence",
    "--kl-divergence-base",
    "--ctx-size",
    "--chunks",
    "--ppl-stride",
)

Runner = Callable[[list[str]], str]


@dataclass(frozen=True, slots=True)
class KldRequest:
    binary: Path
    reference: Path | None
    candidate: Path
    corpus: Path
    work_dir: Path
    bands: Mapping[str, float] | None


def first_reference_tokens(tokens: Sequence[int], *, count: int = KLD_TOKENS) -> tuple[int, ...]:
    if count <= 0:
        raise ValueError("KLD token count must be positive")
    if len(tokens) < count:
        raise ValueError(f"reference-tokenized corpus has {len(tokens)} tokens, requires {count}")
    return tuple(tokens[:count])


def build_kld_command(
    binary: Path,
    *,
    model: Path,
    corpus: Path,
    logits: Path,
    reference: bool,
) -> list[str]:
    command = [
        str(binary),
        "--model",
        str(model),
        "--file",
        str(corpus),
        "--ctx-size",
        str(KLD_CONTEXT_TOKENS),
        "--batch-size",
        str(KLD_CONTEXT_TOKENS),
        "--chunks",
        str(KLD_SEGMENTS),
        "--ppl-stride",
        str(KLD_CONTEXT_TOKENS),
        "--no-warmup",
        "--kl-divergence-base",
        str(logits),
    ]
    if not reference:
        command.append("--kl-divergence")
    return command


def run_kld_subpass(request: KldRequest, *, runner: Runner | None = None) -> JsonObject:
    if request.reference is None or not request.reference.is_file():
        return unavailable_kld("pinned reference weights are not local")
    for path, label in (
        (request.binary, "llama-perplexity binary"),
        (request.candidate, "candidate artifact"),
        (request.corpus, "pinned KLD corpus"),
    ):
        if not path.is_file():
            raise CheckError(f"{label} is missing: {path}")
    invoke = runner or _default_runner
    help_text = invoke([str(request.binary), "--help"])
    missing = [flag for flag in _REQUIRED_HELP_FLAGS if flag not in help_text]
    if missing:
        raise CheckError(f"llama-perplexity lacks required b10076 KLD flags: {', '.join(missing)}")

    request.work_dir.mkdir(parents=True, exist_ok=True)
    logits = request.work_dir / "reference.kld"
    reference_command = build_kld_command(
        request.binary,
        model=request.reference,
        corpus=request.corpus,
        logits=logits,
        reference=True,
    )
    candidate_command = build_kld_command(
        request.binary,
        model=request.candidate,
        corpus=request.corpus,
        logits=logits,
        reference=False,
    )
    _ = invoke(reference_command)
    candidate_log = invoke(candidate_command)
    _ = (request.work_dir / "candidate.log").write_text(candidate_log, encoding="utf-8", newline="\n")
    parsed = parse_kld_log(candidate_log)
    metrics: JsonObject = {
        "mean_kld": _four_significant(parsed.mean_kld),
        "p95_kld": _four_significant(parsed.q95_kld),
        "p99_kld": _four_significant(parsed.q99_kld),
        "top_token_agreement_rate": _four_significant(parsed.same_top_p),
    }
    status, comparison = _compare_bands(metrics, request.bands)
    parameters = kld_parameters()
    candidate_command_values: list[JsonValue] = [value for value in candidate_command]
    reference_command_values: list[JsonValue] = [value for value in reference_command]
    commands: JsonObject = {
        "candidate": candidate_command_values,
        "reference": reference_command_values,
    }
    provenance: JsonObject = {
        "artifact_sha256s": {
            "candidate": sha256_file(request.candidate),
            "reference": sha256_file(request.reference),
        },
        "binary_sha256": sha256_file(request.binary),
        "commands": commands,
        "corpus_sha256": sha256_file(request.corpus),
        "parameters": parameters,
    }
    result: JsonObject = {
        "band_comparison": comparison,
        "metrics": metrics,
        "provenance": provenance,
        "schema_version": "localbench-check-kld-v1",
        "status": status,
        "verdict_effect": "none",
    }
    write_json_file(request.work_dir / "kld.json", result)
    return result


def unavailable_kld(reason: str) -> JsonObject:
    return {
        "parameters": kld_parameters(),
        "reason": reason,
        "schema_version": "localbench-check-kld-v1",
        "status": "unavailable",
        "verdict_effect": "none",
    }


def kld_parameters() -> JsonObject:
    return {
        "accumulation": "fp32",
        "context_tokens": KLD_CONTEXT_TOKENS,
        "direction": "KL(reference||candidate)",
        "fresh_context_per_segment": True,
        "overlap": 0,
        "segments": KLD_SEGMENTS,
        "tokens": KLD_TOKENS,
    }


def _compare_bands(metrics: JsonObject, bands: Mapping[str, float] | None) -> tuple[str, JsonObject]:
    if bands is None:
        return "unavailable", {"reason": "per-family calibrated bands are unavailable"}
    required = {"mean_kld_max", "p95_kld_max", "p99_kld_max", "top_token_agreement_min"}
    if set(bands) != required:
        raise CheckError("KLD bands must define mean/p95/p99 maxima and top-token agreement minimum")
    rounded_bands = {key: _four_significant(value) for key, value in bands.items()}
    checks = {
        "mean_kld": _metric(metrics, "mean_kld") <= rounded_bands["mean_kld_max"],
        "p95_kld": _metric(metrics, "p95_kld") <= rounded_bands["p95_kld_max"],
        "p99_kld": _metric(metrics, "p99_kld") <= rounded_bands["p99_kld_max"],
        "top_token_agreement_rate": _metric(metrics, "top_token_agreement_rate")
        >= rounded_bands["top_token_agreement_min"],
    }
    comparison: JsonObject = {
        "bands": {key: value for key, value in rounded_bands.items()},
        "checks": {key: value for key, value in checks.items()},
        "rule": "exact-on-four-significant-figure-rounded-values",
    }
    return ("in-band" if all(checks.values()) else "out-of-band"), comparison


def _four_significant(value: float) -> float:
    if not math.isfinite(value):
        raise CheckError("KLD metrics must be finite")
    return float(f"{value:.4g}")


def _metric(metrics: JsonObject, key: str) -> float:
    value = metrics.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CheckError(f"KLD metric {key!r} is missing")
    return float(value)


def _default_runner(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise CheckError(f"llama-perplexity exited {completed.returncode}: {output[-2000:]}")
    return output
