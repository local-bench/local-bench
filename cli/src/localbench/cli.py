"""Command-line interface for localbench."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import anyio

from localbench.orchestrate import (
    LaneChoice,
    LocalbenchRun,
    OrchestrateConfig,
    ReasoningEffortChoice,
    default_output_path,
    run_localbench,
)
from localbench.coding_exec import OPT_IN_WARNING
from localbench.coding_exec.orchestrate import CodingExecConfig, CodingExecError, DEFAULT_IMAGE, run_coding_exec
from localbench.kld import run_kld_ladder
from localbench.providers import provider_choices
from localbench.scoring.paired_delta import (
    CompareResult,
    compare_run_files,
    format_honest_delta,
)

_REASONING_EFFORT_CHOICES: Final[tuple[ReasoningEffortChoice, ...]] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the localbench CLI."""
    _prefer_utf8_stdout()
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "kld":
        return _kld(args)
    if args.command == "code":
        return _code(args)
    parser.print_help()
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localbench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run a local benchmark suite")
    run_parser.add_argument("--endpoint", required=True, help="OpenAI-compatible base URL")
    run_parser.add_argument("--model", required=True, help="model name to send in requests")
    run_parser.add_argument(
        "--bench",
        default="all",
        help="'all', a single bench name, or a comma-separated list of bench names",
    )
    run_parser.add_argument("--tier", choices=("quick", "standard"), default="quick")
    run_parser.add_argument("--concurrency", type=int, default=4)
    run_parser.add_argument("--provider", choices=provider_choices(), default="local")
    run_parser.add_argument("--out", type=Path)
    run_parser.add_argument("--api-key-env")
    run_parser.add_argument("--max-items", type=int)
    run_parser.add_argument("--suite-dir", type=Path)
    run_parser.add_argument("--price-in", type=float)
    run_parser.add_argument("--price-out", type=float)
    run_parser.add_argument(
        "--lane",
        choices=("answer-only", "capped-thinking", "api-uncapped"),
        default="answer-only",
    )
    run_parser.add_argument(
        "--reasoning-effort",
        choices=_REASONING_EFFORT_CHOICES,
        default=None,
    )
    run_parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="cap per-item max_tokens (min'd with the bench value); use for bounded local context windows",
    )
    compare_parser = subparsers.add_parser(
        "compare",
        help="compare two saved localbench run records",
    )
    compare_parser.add_argument("run_a", metavar="RUN_A.json", type=Path)
    compare_parser.add_argument("run_b", metavar="RUN_B.json", type=Path)
    compare_parser.add_argument("--out", type=Path)
    compare_parser.add_argument("--iters", type=int, default=10_000)
    compare_parser.add_argument("--seed", type=int, default=0)
    kld_parser = subparsers.add_parser(
        "kld",
        help="measure quant distribution-drift (KLD) vs a full-precision reference",
    )
    kld_parser.add_argument("--reference", required=True, type=Path,
                            help="full-precision (or Q8-proxy) reference GGUF")
    kld_parser.add_argument("--quant", required=True, action="append", type=_label_path,
                            metavar="LABEL=PATH", help="quant GGUF, repeatable")
    kld_parser.add_argument("--calib", required=True, type=Path,
                            help="calibration corpus (hashed into the drift record for provenance)")
    kld_parser.add_argument("--llama-perplexity", required=True, type=Path,
                            help="path to the llama.cpp llama-perplexity binary")
    kld_parser.add_argument("--out", required=True, type=Path, help="drift JSON output path")
    kld_parser.add_argument("--model-label", required=True, help="model name for the drift record")
    kld_parser.add_argument("--reference-label", default="BF16",
                            help="reference type label shown on the model page (e.g. BF16, 'Q8 (proxy)')")
    kld_parser.add_argument("--work-dir", type=Path,
                            help="scratch dir for the baseline .kld + per-quant logs (default: alongside --out)")
    kld_parser.add_argument("--ngl", type=int, default=99)
    kld_parser.add_argument("--churn-reference", type=Path,
                            help="reference task-run JSON; pair with --churn-quant to attach churn")
    kld_parser.add_argument("--churn-quant", action="append", type=_label_path,
                            metavar="LABEL=PATH", help="quant task-run JSON for churn, repeatable")
    code_parser = subparsers.add_parser(
        "code",
        help="opt-in code-EXECUTION axis (BigCodeBench-Hard) in a hardened Docker sandbox",
    )
    code_parser.add_argument("--endpoint", required=True, help="OpenAI-compatible base URL")
    code_parser.add_argument("--model", required=True, help="model name to send in requests")
    code_parser.add_argument("--suite-dir", type=Path, help="suite dir (defaults to suite/v1)")
    code_parser.add_argument("--image", default=DEFAULT_IMAGE,
                             help="bigcode evaluate Docker image; SHOULD be digest-pinned (repo@sha256:...)")
    code_parser.add_argument("--tier", choices=("quick", "standard"), default="standard")
    code_parser.add_argument("--concurrency", type=int, default=4)
    code_parser.add_argument("--provider", choices=provider_choices(), default="local")
    code_parser.add_argument("--api-key-env")
    code_parser.add_argument("--max-items", type=int)
    code_parser.add_argument("--out", type=Path)
    code_parser.add_argument("--reasoning-effort", choices=_REASONING_EFFORT_CHOICES, default=None)
    code_parser.add_argument("--per-task-timeout", type=int, default=30,
                             help="per-task wall-clock seconds inside the sandbox")
    code_parser.add_argument("--runtime", help="extra-isolation container runtime, e.g. runsc (gVisor) on Linux")
    code_parser.add_argument(
        "--allow-unsafe-sandbox",
        action="store_true",
        help="override the fail-closed gate and run on rootful bare-Linux Docker with no second "
        "isolation boundary (NOT recommended — install gVisor or use rootless Docker instead)",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    api_key = _api_key(args.api_key_env)
    out = args.out or default_output_path(args.model, args.tier)
    record = anyio.run(
        run_localbench,
        OrchestrateConfig(
            endpoint=args.endpoint,
            model=args.model,
            bench=args.bench,
            tier=args.tier,
            concurrency=args.concurrency,
            out=out,
            api_key=api_key,
            max_items=args.max_items,
            suite_dir=args.suite_dir,
            price_in=args.price_in,
            price_out=args.price_out,
            lane=_lane(args.lane),
            provider=args.provider,
            reasoning_effort=_reasoning_effort(args.reasoning_effort),
            max_tokens=args.max_tokens,
        ),
    )
    _print_summary(record)
    return 0


def _compare(args: argparse.Namespace) -> int:
    try:
        comparison = compare_run_files(
            args.run_a,
            args.run_b,
            iters=max(1, args.iters),
            seed=args.seed,
        )
    except ValueError as error:
        print(f"error      {error}")
        return 2
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as handle:
            json.dump(comparison, handle, indent=2)
            handle.write("\n")
    _print_compare(comparison)
    return 0


def _kld(args: argparse.Namespace) -> int:
    quants = dict(args.quant)
    churn_quants = dict(args.churn_quant) if args.churn_quant else None
    work_dir = args.work_dir or args.out.parent / f"{args.out.stem}-kld"
    drift = run_kld_ladder(
        llama_perplexity=args.llama_perplexity,
        reference=args.reference,
        quants=quants,
        calib=args.calib,
        model_label=args.model_label,
        reference_label=args.reference_label,
        work_dir=work_dir,
        ngl=args.ngl,
        churn_reference=args.churn_reference,
        churn_quants=churn_quants,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        json.dump(drift, handle, indent=2)
        handle.write("\n")
    _print_kld_summary(drift)
    print(f"output     {args.out}")
    return 0


def _code(args: argparse.Namespace) -> int:
    print(OPT_IN_WARNING)
    if "@sha256:" not in args.image:
        print(f"warning    image '{args.image}' is not digest-pinned; pin repo@sha256:... before a ranked run")
    config = CodingExecConfig(
        endpoint=args.endpoint,
        model=args.model,
        suite_dir=args.suite_dir or _default_v1_suite_dir(),
        image=args.image,
        tier=args.tier,
        concurrency=args.concurrency,
        out=args.out,
        api_key=_api_key(args.api_key_env),
        max_items=args.max_items,
        provider=args.provider,
        reasoning_effort=_reasoning_effort(args.reasoning_effort),
        per_task_timeout=args.per_task_timeout,
        runtime=args.runtime,
        allow_unsafe_sandbox=args.allow_unsafe_sandbox,
    )
    try:
        run = anyio.run(run_coding_exec, config)
    except CodingExecError as error:
        print(f"error      {error}")
        return 2
    for warning in run["warnings"]:
        print(f"warning    {warning}")
    _print_coding_summary(run)
    return 0


def _default_v1_suite_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "suite" / "v1"


def _print_coding_summary(run: dict) -> None:
    score = run["score"]
    print(
        f"coding-exec {score['n_passed']}/{score['n']} passed "
        f"(raw {score['raw_accuracy'] * 100:.1f}%, no-code {score['n_no_code']}, "
        f"timed-out {score['n_timed_out']})",
    )
    manifest = run["manifest"]
    print(f"image      {manifest['image']} (digest-pinned={manifest['image_digest_pinned']})")
    if manifest.get("ranked_eligible"):
        print("ranked     eligible (digest-pinned + sandbox not overridden)")
    else:
        reasons = "; ".join(manifest.get("ranked_ineligible_reasons", [])) or "see manifest"
        print(f"ranked     NOT eligible — {reasons}")
    print(f"output     {run['output_path']}")
    for warning in run["warnings"]:
        print(f"warning    {warning}")


def _label_path(value: str) -> tuple[str, Path]:
    label, sep, path = value.partition("=")
    if not sep or not label or not path:
        raise argparse.ArgumentTypeError(f"expected LABEL=PATH, got {value!r}")
    return label, Path(path)


def _print_kld_summary(drift: dict) -> None:
    print(f"model      {drift['model']}  (drift vs reference={drift['reference']}; NOT a task score)")
    print("quant       medKLD   q99KLD  sameTop%  churn%")
    for label, entry in drift["quants"].items():
        kld = entry["kld"]
        churn = entry["churn"]
        churn_pct = f"{churn['churn'] * 100:>5.1f}" if churn is not None else "    -"
        print(
            f"{label:<10} "
            f"{kld['median_kld']:>7.3f} "
            f"{kld['q99_kld']:>8.3f} "
            f"{kld['same_top_p']:>8.1f} "
            f"{churn_pct}",
        )


def _api_key(env_var: str | None) -> str | None:
    if env_var is None:
        return None
    return os.environ.get(env_var)


def _prefer_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _lane(value: str) -> LaneChoice:
    if value == "capped-thinking":
        return "capped-thinking"
    if value == "api-uncapped":
        return "api-uncapped"
    return "answer-only"


def _reasoning_effort(value: str | None) -> ReasoningEffortChoice | None:
    match value:
        case None:
            return None
        case "none":
            return "none"
        case "minimal":
            return "minimal"
        case "low":
            return "low"
        case "medium":
            return "medium"
        case "high":
            return "high"
        case "xhigh":
            return "xhigh"
        case _:
            raise argparse.ArgumentTypeError(f"unsupported reasoning effort: {value}")


def _print_summary(record: LocalbenchRun) -> None:
    print("bench       raw      corrected  n    fail  err")
    for name, aggregate in record["benches"].items():
        print(
            f"{name:<10} "
            f"{aggregate['raw_accuracy'] * 100:>6.1f}% "
            f"{aggregate['chance_corrected'] * 100:>9.1f}% "
            f"{aggregate['n']:>4} "
            f"{aggregate['n_extraction_failures']:>5} "
            f"{aggregate['n_errors']:>4}",
        )
    totals = record["totals"]
    print(f"composite  {record['composite'] * 100:.1f}%")
    print(
        "tokens     "
        f"prompt={totals['prompt_tokens']} "
        f"completion={totals['completion_tokens']} "
        f"total={totals['total_tokens']}",
    )
    print(
        f"wall       {totals['wall_time_seconds']:.2f}s, "
        f"tok/s={totals['completion_tokens_per_second']:.2f}",
    )
    if "estimated_cost_usd" in record:
        print(f"cost       ${record['estimated_cost_usd']:.6f}")
    print(f"output     {record['output_path']}")
    for warning in record["warnings"]:
        print(f"warning    {warning}")


def _print_compare(comparison: CompareResult) -> None:
    print(f"paired composite delta  {format_honest_delta(comparison['composite_delta'])}")
    repeatability = comparison["repeatability_ci"]
    generalization = comparison["generalization_ci"]
    print(
        "repeatability CI        "
        f"{repeatability['lo'] * 100:.1f} .. {repeatability['hi'] * 100:.1f}",
    )
    print(
        "generalization CI       "
        f"{generalization['lo'] * 100:.1f} .. {generalization['hi'] * 100:.1f}",
    )
    print("domains")
    for domain, result in comparison["domains"].items():
        print(f"  {domain:<22} {format_honest_delta(result['delta'])}")
    worst_axis = comparison["worst_axis"]
    print(
        "worst axis              "
        f"{worst_axis['domain']} {format_honest_delta(worst_axis['delta'])}",
    )
    flags = comparison["severe_subgroup_regressions"]
    if flags:
        print("subgroup regressions")
        for flag in flags:
            print(
                f"  {flag['domain']}: {flag['stratum']} "
                f"{format_honest_delta(flag['ci'])}",
            )
