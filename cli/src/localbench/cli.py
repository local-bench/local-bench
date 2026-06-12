"""Command-line interface for localbench."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

import anyio

from localbench.orchestrate import (
    LaneChoice,
    LocalbenchRun,
    OrchestrateConfig,
    default_output_path,
    run_localbench,
)
from localbench.providers import provider_choices


def main(argv: Sequence[str] | None = None) -> int:
    """Run the localbench CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
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
        choices=("all", "mmlu_pro", "ifeval", "genmath"),
        default="all",
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
        ),
    )
    _print_summary(record)
    return 0


def _api_key(env_var: str | None) -> str | None:
    if env_var is None:
        return None
    return os.environ.get(env_var)


def _lane(value: str) -> LaneChoice:
    if value == "capped-thinking":
        return "capped-thinking"
    if value == "api-uncapped":
        return "api-uncapped"
    return "answer-only"


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
