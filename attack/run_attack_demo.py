"""Run the local-bench answer-injection attack demonstration."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import TypeAlias

import anyio
import httpx
from cheat_proxy import CheatProxy, CheatProxyConfig
from localbench.orchestrate import LocalbenchRun, OrchestrateConfig, run_localbench

Rows: TypeAlias = list[tuple[str, str, str]]

HONEST_REFERENCE = 50.0
HONEST_LABEL = "Illustrative honest local 7B baseline"


def main() -> int:
    args = _parser().parse_args()
    record = anyio.run(_run_demo, args)
    _print_summary(record, args.claimed_model)
    return 0


async def _run_demo(args: argparse.Namespace) -> LocalbenchRun:
    config = CheatProxyConfig(
        claimed_model=args.claimed_model,
        fake_tok_s=args.fake_tok_s,
        inject=args.inject,
    )
    if config.inject == "strong-model":
        raise SystemExit(
            "inject=strong-model is not implemented in P0; it would forward to an "
            "API model and needs a key this repo does not have.",
        )
    proxy = CheatProxy.from_suite_dir(args.suite_dir, config)
    print("Proxy mode: in-process httpx transport.")
    print("Network: no socket is opened, and no request is sent to localhost:8000.")
    with tempfile.TemporaryDirectory(prefix="localbench-cheat-demo-") as tmp:
        return await run_localbench(
            OrchestrateConfig(
                endpoint="http://inprocess-cheat-proxy.invalid/v1",
                model=args.claimed_model,
                tier="quick",
                suite_dir=args.suite_dir,
                bench="mmlu_pro,ifeval,genmath",
                max_items=args.max_items,
                concurrency=1,
                out=Path(tmp) / "attack-run.json",
            ),
            transport=httpx.MockTransport(proxy.handle_httpx_request),
        )


def _print_summary(record: LocalbenchRun, claimed_model: str) -> None:
    cheater = record["composite"] * 100
    rows = [
        (HONEST_LABEL, f"{HONEST_REFERENCE:.1f}", "Illustrative range: 45-55, not measured here"),
        (
            f"Cheat proxy claiming {claimed_model}",
            f"{cheater:.1f}",
            "Measured from injected transcripts in this demo",
        ),
    ]
    print()
    print("Before / After")
    _print_table(("Run", "Composite (0-100)", "Basis"), rows)
    print()
    print("Measured bench details")
    bench_rows = [
        (
            name,
            f"{aggregate['raw_accuracy'] * 100:.1f}",
            f"{aggregate['chance_corrected'] * 100:.1f}",
        )
        for name, aggregate in record["benches"].items()
    ]
    _print_table(("Bench", "Raw accuracy", "Chance-corrected"), bench_rows)
    print()
    print("Signal analysis")
    _print_table(
        ("Signal", "Result", "Reason"),
        [
            (
                "Server-side scoring",
                "DOES NOT catch",
                "The transcript contains valid-looking answers and scores normally.",
            ),
            (
                "Timing",
                "DOES NOT catch",
                "The proxy sleeps to mimic a slow local tokens-per-second rate.",
            ),
            (
                "Hardware sanity",
                "DOES NOT catch",
                "The claimed weak model is internally consistent with the fake endpoint.",
            ),
            (
                "Replication",
                "WOULD catch",
                "Independent real potato-7b-q2 runs would not converge near this score.",
            ),
        ],
    )


def _print_table(headers: tuple[str, str, str], rows: Rows) -> None:
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-dir", type=Path, default=repo_root / "suite" / "v0")
    parser.add_argument("--claimed-model", default="potato-7b-q2")
    parser.add_argument("--fake-tok-s", type=float, default=35.0)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--inject", choices=("answers", "strong-model"), default="answers")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
