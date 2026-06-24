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
import httpx

from localbench.orchestrate import (
    LaneChoice,
    LocalbenchRun,
    OrchestrateConfig,
    ReasoningActivationChoice,
    ReasoningEffortChoice,
    default_output_path,
    run_localbench,
)
from localbench._scoring import (
    ScoredItem,
    aggregate,
    composite,
    run_totals,
    score_bench,
    scorer_unavailable_results,
    scorer_unavailable_warning,
)
from localbench._suite import RenderedBench, read_json_object, render_benches
from localbench._types import ItemResult, JsonValue
from localbench.coding_exec import OPT_IN_WARNING
from localbench.coding_exec.orchestrate import CodingExecConfig, CodingExecError, DEFAULT_IMAGE, run_coding_exec
from localbench.kld import run_kld_ladder
from localbench.lane_conformance import assess_run_conformance
from localbench.providers import provider_choices
from localbench.scoring.paired_delta import (
    CompareResult,
    compare_run_files,
    format_honest_delta,
)
from localbench.scoring.board import BoardBuildError, write_board
from localbench.scoring.board_support import DEFAULT_OUT, DEFAULT_RUNS_DIR
from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.validate import SubmissionValidationError
from localbench.submissions.verify import verify_bundle_offline
from localbench.suite_resolver import (
    DEFAULT_SUITE_ID,
    SuiteResolutionError,
    fetch_suite,
    normalize_suite_id,
    resolve_suite_dir,
    suite_cache_root,
)

_REASONING_EFFORT_CHOICES: Final[tuple[ReasoningEffortChoice, ...]] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
_REASONING_ACTIVATION_CHOICES: Final[tuple[ReasoningActivationChoice, ...]] = (
    "qwen3",
    "granite",
    "nemotron",
    "r1",
    "gemma4",
)
_NO_SCORABLE_BENCH: Final = "__localbench_no_scorable_bench__"


class EndpointPreflightError(RuntimeError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    """Run the localbench CLI."""
    _prefer_utf8_stdout()
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "fetch-suite":
        return _fetch_suite(args)
    if args.command == "suite":
        return _suite(args)
    if args.command == "submit":
        return _submit(args)
    if args.command == "doctor":
        return _doctor(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "kld":
        return _kld(args)
    if args.command == "code":
        return _code(args)
    if args.command == "board":
        return _board(args)
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
    run_parser.add_argument("--tier", choices=("quick", "standard"), default=None)
    run_parser.add_argument("--concurrency", type=int, default=4)
    run_parser.add_argument("--provider", choices=provider_choices(), default="local")
    run_parser.add_argument("--out", type=Path)
    run_parser.add_argument("--api-key-env")
    run_parser.add_argument("--max-items", type=int)
    run_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    run_parser.add_argument("--suite-dir", type=Path)
    run_parser.add_argument("--suite-source", type=Path)
    run_parser.add_argument("--accept-suite-terms", action="store_true")
    run_parser.add_argument("--cache-dir", type=Path)
    run_parser.add_argument("--dry-run", action="store_true")
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
        "--hf-model-id",
        default=None,
        help="served model HF repo for local capped-thinking chat-template rendering",
    )
    run_parser.add_argument(
        "--reasoning-activation",
        choices=_REASONING_ACTIVATION_CHOICES,
        default="qwen3",
        help="model-family activation used with --hf-model-id in local capped-thinking",
    )
    run_parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="cap per-item max_tokens (min'd with the bench value); use for bounded local context windows",
    )
    fetch_parser = subparsers.add_parser(
        "fetch-suite",
        help="cache a verified public suite bundle from a local source",
    )
    fetch_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    fetch_parser.add_argument("--source", type=Path)
    fetch_parser.add_argument("--accept-suite-terms", action="store_true")
    fetch_parser.add_argument("--cache-dir", type=Path)
    suite_parser = subparsers.add_parser("suite", help="suite utilities")
    suite_subparsers = suite_parser.add_subparsers(dest="suite_command", required=True)
    inspect_parser = suite_subparsers.add_parser("inspect", help="inspect a resolved suite")
    inspect_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    inspect_parser.add_argument("--suite-dir", type=Path)
    inspect_parser.add_argument("--cache-dir", type=Path)
    submit_parser = subparsers.add_parser("submit", help="submission bundle utilities")
    submit_subparsers = submit_parser.add_subparsers(dest="submit_command", required=True)
    pack_parser = submit_subparsers.add_parser("pack", help="pack an offline submission bundle")
    pack_parser.add_argument("--run", required=True, type=Path)
    pack_parser.add_argument("--suite-dir", required=True, type=Path)
    pack_parser.add_argument("--model-name", required=True)
    pack_parser.add_argument("--signing-key", required=True, type=Path)
    pack_parser.add_argument("--out", required=True, type=Path)
    pack_parser.add_argument("--offline", action="store_true")
    pack_parser.add_argument("--created-at", help=argparse.SUPPRESS)
    pack_parser.add_argument("--run-nonce", help=argparse.SUPPRESS)
    verify_parser = submit_subparsers.add_parser(
        "verify-offline",
        help="verify and re-score an offline submission bundle",
    )
    verify_parser.add_argument("bundle", type=Path)
    verify_parser.add_argument("--suite-dir", required=True, type=Path)
    verify_parser.add_argument("--out", required=True, type=Path)
    doctor_parser = subparsers.add_parser("doctor", help="check localbench local-run readiness")
    doctor_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    doctor_parser.add_argument("--cache-dir", type=Path)
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
    board_parser = subparsers.add_parser(
        "board",
        help="build scorer-side board_v1.json and release manifest",
    )
    board_parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    board_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    board_parser.add_argument("--curation", type=Path)
    board_parser.add_argument("--frozen-timestamp")
    board_parser.add_argument("--check-parity", dest="check_parity", action="store_true", default=True)
    board_parser.add_argument("--no-check-parity", dest="check_parity", action="store_false")
    return parser


def _run(args: argparse.Namespace) -> int:
    api_key = _api_key(args.api_key_env)
    tier = _resolved_run_tier(args.suite, args.tier)
    if args.dry_run:
        return _run_dry(args, tier)
    out = args.out or default_output_path(args.model, tier)
    try:
        bench_choice, scorer_gates = _scorer_gates(args, tier)
        anyio.run(_preflight_endpoint, args.endpoint)
        record = anyio.run(
            run_localbench,
            OrchestrateConfig(
                endpoint=args.endpoint,
                model=args.model,
                suite=args.suite,
                bench=bench_choice,
                tier=tier,
                concurrency=args.concurrency,
                out=out,
                api_key=api_key,
                max_items=args.max_items,
                suite_dir=args.suite_dir,
                suite_source=args.suite_source,
                accept_suite_terms=args.accept_suite_terms,
                cache_root=args.cache_dir,
                price_in=args.price_in,
                price_out=args.price_out,
                lane=_lane(args.lane),
                provider=args.provider,
                reasoning_effort=_reasoning_effort(args.reasoning_effort),
                hf_model_id=args.hf_model_id,
                reasoning_activation=_reasoning_activation(args.reasoning_activation),
                max_tokens=args.max_tokens,
            ),
        )
    except EndpointPreflightError as error:
        print(f"error      {error}")
        return 2
    if scorer_gates:
        _append_scorer_gated_benches(record, scorer_gates)
        _rewrite_run_record(record)
    _print_summary(record)
    return 0


async def _preflight_endpoint(endpoint: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.get(f"{endpoint.rstrip('/')}/models")
        except httpx.TransportError as error:
            raise EndpointPreflightError(
                "nothing is listening at "
                f"{endpoint.rstrip('/')}; start your llama-server or another "
                "OpenAI-compatible server before running localbench",
            ) from error


def _scorer_gates(
    args: argparse.Namespace,
    tier: str,
) -> tuple[str, dict[str, tuple[RenderedBench, str]]]:
    ref = resolve_suite_dir(
        suite_id=args.suite,
        suite_dir=args.suite_dir,
        accept_suite_terms=args.accept_suite_terms,
        source=args.suite_source,
        cache_root=args.cache_dir,
    )
    suite = read_json_object(ref.path / "suite.json")
    warnings: list[str] = []
    rendered = render_benches(args.bench, tier, args.max_items, ref.path, suite, warnings)
    gates: dict[str, tuple[RenderedBench, str]] = {}
    available: list[str] = []
    for bench in rendered:
        warning = scorer_unavailable_warning(bench)
        if warning is None:
            available.append(bench.name)
            continue
        gates[bench.name] = (bench, warning)
    if not gates:
        return args.bench, {}
    return ",".join(available) if available else _NO_SCORABLE_BENCH, gates


def _append_scorer_gated_benches(
    record: LocalbenchRun,
    gates: dict[str, tuple[RenderedBench, str]],
) -> None:
    added: list[ScoredItem] = []
    record["warnings"] = [
        warning for warning in record["warnings"] if _NO_SCORABLE_BENCH not in warning
    ]
    for bench, warning in gates.values():
        results = scorer_unavailable_results(bench, warning)
        scored = score_bench(bench, results)
        added.extend(scored)
        record["benches"][bench.name] = aggregate(bench.name, scored, bench.baseline)
        if warning not in record["warnings"]:
            record["warnings"].append(warning)
    record["items"].extend(added)
    record["totals"] = run_totals(record["items"], record["totals"]["wall_time_seconds"])
    record["composite"] = composite(record["benches"])
    record["conformance"] = assess_run_conformance(
        _results_by_bench_from_scored(record["items"]),
        forced=_record_forced(record),
    )


def _results_by_bench_from_scored(items: list[ScoredItem]) -> dict[str, list[ItemResult]]:
    results: dict[str, list[ItemResult]] = {}
    for item in items:
        bench = item["bench"]
        result: ItemResult = {
            "id": item["id"],
            "response_text": item["response_text"],
            "reasoning_text": _optional_text(item.get("reasoning_text")),
            "finish_reason": item["finish_reason"],
            "usage": item["usage"],
            "latency_seconds": item["latency_seconds"],
            "started_at": item["started_at"],
            "finished_at": item["finished_at"],
            "attempts": item["attempts"],
            "error": item["error"],
        }
        results.setdefault(bench, []).append(result)
    return results


def _record_forced(record: LocalbenchRun) -> bool:
    suite = record["manifest"].get("suite")
    if not isinstance(suite, dict):
        return False
    caps = suite.get("caps")
    if not isinstance(caps, dict):
        return False
    thinking_budget = caps.get("thinking_budget")
    return isinstance(thinking_budget, int) and thinking_budget > 0


def _rewrite_run_record(record: LocalbenchRun) -> None:
    output_path = Path(record["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")


def _optional_text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _fetch_suite(args: argparse.Namespace) -> int:
    try:
        ref = fetch_suite(
            suite_id=args.suite,
            source=args.source,
            accept_suite_terms=args.accept_suite_terms,
            cache_root=args.cache_dir,
        )
    except SuiteResolutionError as error:
        print(f"error      {error}")
        return 2
    print(f"suite_id  {ref.suite_id}")
    print(f"hash      {ref.suite_hash}")
    print(f"cached    {ref.path}")
    return 0


def _suite(args: argparse.Namespace) -> int:
    if args.suite_command == "inspect":
        try:
            ref = resolve_suite_dir(
                suite_id=args.suite,
                suite_dir=args.suite_dir,
                cache_root=args.cache_dir,
            )
        except SuiteResolutionError as error:
            print(f"error      {error}")
            return 2
        _print_suite_ref(ref.path, ref.suite_id, ref.suite_hash, ref.source)
        return 0
    print("error      unsupported suite command")
    return 2


def _submit(args: argparse.Namespace) -> int:
    if args.submit_command == "pack":
        return _submit_pack(args)
    if args.submit_command == "verify-offline":
        return _submit_verify_offline(args)
    print("error      unsupported submit command")
    return 2


def _submit_pack(args: argparse.Namespace) -> int:
    try:
        manifest = pack_submission_bundle(
            run_path=args.run,
            suite_dir=args.suite_dir,
            model_name=args.model_name,
            signing_key_path=args.signing_key,
            out_path=args.out,
            offline=args.offline,
            created_at=args.created_at,
            run_nonce=args.run_nonce,
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError) as error:
        print(f"error      {error}")
        return 2
    print(f"bundle    {args.out}")
    print(f"payload   {manifest['payload_sha256']}")
    return 0


def _submit_verify_offline(args: argparse.Namespace) -> int:
    try:
        result = verify_bundle_offline(args.bundle, suite_dir=args.suite_dir, out_path=args.out)
    except (SubmissionValidationError, OSError, json.JSONDecodeError) as error:
        print(f"error      {error}")
        return 2
    print(f"verification {args.out}")
    print(f"trust_label  {result['trust_label']}")
    print(f"publishable  {str(result['publishable']).lower()}")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    print(f"python    {sys.version.split()[0]}")
    print(f"cache     {suite_cache_root(args.cache_dir)}")
    try:
        ref = resolve_suite_dir(suite_id=args.suite, cache_root=args.cache_dir)
    except SuiteResolutionError as error:
        print(f"suite     {args.suite} unavailable: {error}")
        return 0
    print(f"suite     {ref.suite_id} ok ({ref.source}, {ref.suite_hash})")
    return 0


def _run_dry(args: argparse.Namespace, tier: str) -> int:
    try:
        ref = resolve_suite_dir(
            suite_id=args.suite,
            suite_dir=args.suite_dir,
            accept_suite_terms=args.accept_suite_terms,
            source=args.suite_source,
            cache_root=args.cache_dir,
        )
    except SuiteResolutionError as error:
        print(f"error      {error}")
        return 2
    suite = read_json_object(ref.path / "suite.json")
    warnings: list[str] = []
    benches = render_benches(args.bench, tier, args.max_items, ref.path, suite, warnings)
    n_items = sum(len(bench.benchmark_items) for bench in benches)
    print("dry-run   no endpoint calls made")
    print(f"suite_id  {ref.suite_id}")
    print(f"hash      {ref.suite_hash}")
    print(f"path      {ref.path}")
    print(f"endpoint  {args.endpoint}")
    print(f"model     {args.model}")
    print(f"benches   {', '.join(bench.name for bench in benches) or '(none)'}")
    print(f"items     {n_items}")
    for warning in warnings:
        print(f"warning    {warning}")
    return 0


def _resolved_run_tier(suite_id: str, requested_tier: str | None) -> str:
    if requested_tier is not None:
        return requested_tier
    if normalize_suite_id(suite_id) == DEFAULT_SUITE_ID:
        return "standard"
    return "quick"


def _print_suite_ref(path: Path, suite_id: str, hash_value: str, source: str) -> None:
    suite = read_json_object(path / "suite.json")
    benches = suite.get("benches")
    names = sorted(benches) if isinstance(benches, dict) else []
    print(f"suite_id  {suite_id}")
    print(f"hash      {hash_value}")
    print(f"source    {source}")
    print(f"path      {path}")
    print(f"benches   {', '.join(names) if names else '(none)'}")


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


def _board(args: argparse.Namespace) -> int:
    try:
        result = write_board(
            runs_dir=args.runs_dir,
            out=args.out,
            curation_path=args.curation,
            frozen_timestamp=args.frozen_timestamp,
            check_parity=args.check_parity,
        )
    except (BoardBuildError, OSError, json.JSONDecodeError) as error:
        print(f"error      {error}")
        return 2
    print(f"output     {result.board_path}")
    print(f"manifest   {result.manifest_path}")
    print(f"sha256     {result.board_sha256}")
    if not result.parity.checked:
        print("parity    skipped")
        return 0
    if result.parity.divergences:
        for divergence in result.parity.divergences:
            print(
                "DIVERGENCE "
                f"{divergence.model} {divergence.field}: "
                f"board={divergence.board_value} index={divergence.index_value}",
            )
        return 1
    print("parity    ok")
    return 0


def _default_v1_suite_dir() -> Path:
    return resolve_suite_dir(suite_id=DEFAULT_SUITE_ID).path


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


def _reasoning_activation(value: str) -> ReasoningActivationChoice:
    match value:
        case "qwen3":
            return "qwen3"
        case "granite":
            return "granite"
        case "nemotron":
            return "nemotron"
        case "r1":
            return "r1"
        case "gemma4":
            return "gemma4"
        case _:
            raise argparse.ArgumentTypeError(f"unsupported reasoning activation: {value}")


def _print_summary(record: LocalbenchRun) -> None:
    print("bench             raw  corrected     term     cond    n   fail  err")
    for name, aggregate in record["benches"].items():
        print(
            f"{name:<14} "
            f"{aggregate['raw_accuracy'] * 100:>6.1f}% "
            f"{aggregate['chance_corrected'] * 100:>9.1f}% "
            f"{aggregate['termination_rate'] * 100:>7.1f}% "
            f"{aggregate['conditional_accuracy'] * 100:>7.1f}% "
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
        f"{repeatability['lo'] * 100:.1f} .. {repeatability['hi'] * 100:.1f}  (within-suite item bootstrap)",
    )
    print(
        "generalization CI       "
        f"{generalization['lo'] * 100:.1f} .. {generalization['hi'] * 100:.1f}  (clustered by subject/source)",
    )
    print("note     run-to-run repeatability needs repeat RUNS; replication needs >=3 accounts — not computed here")
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
