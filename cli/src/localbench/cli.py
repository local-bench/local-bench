"""Command-line interface for localbench."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, TypeAlias

import anyio
import httpx

from localbench.orchestrate import (
    LaneChoice,
    LocalbenchRun,
    OrchestrateConfig,
    ReasoningActivationChoice,
    ReasoningEffortChoice,
    UnsafeResumeError,
    default_output_path,
    run_localbench,
)
from localbench._scoring import (
    ScoredItem,
    scorer_unavailable_warning,
)
from localbench._suite import RenderedBench, read_json_object, render_benches
from localbench._types import ItemResult, JsonValue
from localbench.campaign import campaign_paths
from localbench.coding_exec import OPT_IN_WARNING
from localbench.coding_exec.orchestrate import CodingExecConfig, CodingExecError, DEFAULT_IMAGE, run_coding_exec
from localbench.exit_codes import (
    EXIT_CHECKPOINT_CORRUPTION,
    EXIT_COMPLETE,
    EXIT_INTERNAL_RUNNER_BUG,
    EXIT_PREFLIGHT_FAILED,
    EXIT_UNSAFE_RESUME,
)
from localbench.campaign_checkpoints import CheckpointCorruptionError, completed_benches
from localbench.kld import run_kld_ladder
from localbench.lane_conformance import assess_run_conformance
from localbench.persistence import atomic_write_json
from localbench.providers import provider_choices
from localbench.run_plan import resolve_run_benches
from localbench.scoring.paired_delta import (
    CompareResult,
    compare_run_files,
    format_honest_delta,
)
from localbench.scoring.axis_status import axis_key_for_bench, mark_axis_not_measured
from localbench.scoring.board import BoardBuildError, write_board
from localbench.scoring.board_support import DEFAULT_OUT_V2, DEFAULT_RUNS_DIR
from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.canon import canonical_json_bytes, write_json_file
from localbench.submissions.foundation_scores import score_summary
from localbench.submissions.client import (
    AdminBundleDownloadRequest,
    AdminSubmissionListRequest,
    AdminVerificationResultRequest,
    SubmissionStatusRequest,
    SubmissionTicketRequest,
    SubmissionUploadRequest,
    complete_uploaded_bundle,
    download_admin_bundle,
    list_admin_submissions,
    mark_admin_verification_result,
    read_submission_ticket,
    request_submission_ticket,
    upload_submission_bundle,
)
from localbench.submissions.crypto import load_private_key
from localbench.submissions.keys import Ed25519SeedError, write_private_key
from localbench.submissions.foundation import (
    rescore_bundle as rescore_result_bundle,
    validate_submission_bundle as validate_result_bundle_file,
)
from localbench.submissions.status_update import verify_submission
from localbench.submissions.validate import SubmissionValidationError
from localbench.submissions.verify import verify_bundle_offline
from localbench.tc_json_v1_runner import run_tc_json_v1
from localbench.suite_resolver import (
    DEFAULT_SUITE_ID,
    RemoteSuiteFetch,
    SuiteResolutionError,
    fetch_suite,
    fetch_suite_from_manifest_url,
    normalize_suite_id,
    resolve_suite_dir,
    suite_cache_root,
)
from localbench.supervisor import SupervisorConfig, run_supervised

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
ScorerGate: TypeAlias = tuple[RenderedBench, str, str]


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
    if args.command == "validate-submission-bundle":
        return _validate_result_bundle_command(args)
    if args.command == "rescore-bundle":
        return _rescore_result_bundle_command(args)
    if args.command == "verify-submission":
        return _verify_submission_command(args)
    if args.command == "doctor":
        return _doctor(args)
    if args.command == "status":
        return _status(args)
    if args.command == "collect":
        return _collect(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "kld":
        return _kld(args)
    if args.command == "code":
        return _code(args)
    if args.command == "board":
        return _board(args)
    if args.command == "tc-json":
        return _tc_json(args)
    parser.print_help()
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localbench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run a local benchmark suite")
    run_parser.add_argument("--endpoint", help="OpenAI-compatible base URL")
    run_parser.add_argument("--model", help="model name to send in requests")
    run_parser.add_argument("--resume", type=Path, help="resume an existing campaign directory")
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
    run_parser.add_argument("--preflight", action="store_true")
    run_parser.add_argument("--no-supervisor", action="store_true")
    run_parser.add_argument("--skip-preflight", action="store_true", help=argparse.SUPPRESS)
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
    run_parser.add_argument("--publishable", action="store_true", help="pin sampler settings for submission")
    run_parser.add_argument("--sampler-seed", type=int)
    run_parser.add_argument("--model-file", type=Path)
    run_parser.add_argument("--model-family")
    run_parser.add_argument("--quant-label")
    run_parser.add_argument("--model-format")
    run_parser.add_argument("--tokenizer-file", type=Path)
    run_parser.add_argument("--chat-template-file", type=Path)
    run_parser.add_argument("--runtime-name")
    run_parser.add_argument("--runtime-version")
    run_parser.add_argument("--kv-cache-quant")
    run_parser.add_argument("--ctx-len-configured", type=int)
    run_parser.add_argument("--parallel-slots", type=int)
    run_parser.add_argument("--build-flags")
    run_parser.add_argument("--runner-build-id")
    fetch_parser = subparsers.add_parser(
        "fetch-suite",
        help="cache a verified public suite bundle from a local source or manifest URL",
    )
    fetch_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    fetch_parser.add_argument("--source", type=Path)
    fetch_parser.add_argument("--source-url")
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
    keygen_parser = submit_subparsers.add_parser("keygen", help="create an Ed25519 submission key")
    keygen_parser.add_argument("--out", required=True, type=Path)
    ticket_parser = submit_subparsers.add_parser("ticket", help="request an online submission ticket")
    ticket_parser.add_argument("--site", required=True)
    ticket_key_group = ticket_parser.add_mutually_exclusive_group(required=True)
    ticket_key_group.add_argument("--public-key")
    ticket_key_group.add_argument("--signing-key", type=Path)
    ticket_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    ticket_parser.add_argument("--out", type=Path, default=Path("ticket.json"))
    pack_parser = submit_subparsers.add_parser(
        "pack",
        help="pack an offline or ticket-bound submission bundle",
    )
    pack_parser.add_argument("--run", required=True, type=Path)
    pack_parser.add_argument("--suite-dir", required=True, type=Path)
    pack_parser.add_argument("--model-name", required=True)
    pack_parser.add_argument("--signing-key", required=True, type=Path)
    pack_parser.add_argument("--out", required=True, type=Path)
    pack_parser.add_argument("--offline", action="store_true")
    pack_parser.add_argument("--ticket", type=Path)
    pack_parser.add_argument("--created-at", help=argparse.SUPPRESS)
    pack_parser.add_argument("--run-nonce", help=argparse.SUPPRESS)
    upload_parser = submit_subparsers.add_parser("upload", help="upload a ticket-bound submission bundle")
    upload_parser.add_argument("--ticket", required=True, type=Path)
    upload_parser.add_argument("--bundle", required=True, type=Path)
    status_parser = submit_subparsers.add_parser("status", help="poll online submission status")
    status_parser.add_argument("submission_id")
    status_parser.add_argument("--site", required=True)
    admin_verify_parser = submit_subparsers.add_parser(
        "admin-verify",
        help="pull uploaded submissions, re-score them locally, and mark them for review",
    )
    admin_verify_parser.add_argument("--site", required=True)
    admin_verify_parser.add_argument("--suite-dir", required=True, type=Path)
    admin_verify_parser.add_argument("--work-dir", required=True, type=Path)
    admin_verify_parser.add_argument("--admin-secret-env", default="LOCALBENCH_ADMIN_SECRET")
    admin_verify_parser.add_argument("--status", default="uploaded")
    admin_verify_parser.add_argument("--limit", type=int, default=20)
    verify_parser = submit_subparsers.add_parser(
        "verify-offline",
        help="verify and re-score an offline submission bundle",
    )
    verify_parser.add_argument("bundle", type=Path)
    verify_parser.add_argument("--suite-dir", required=True, type=Path)
    verify_parser.add_argument("--out", required=True, type=Path)
    validate_bundle_parser = subparsers.add_parser(
        "validate-submission-bundle",
        help="validate a result bundle against the publishable submission contract",
    )
    validate_bundle_parser.add_argument("bundle", type=Path)
    validate_bundle_parser.add_argument("--suite-dir", type=Path, default=Path("..") / "suite" / "v1")
    validate_bundle_parser.add_argument("--out", type=Path)
    rescore_bundle_parser = subparsers.add_parser(
        "rescore-bundle",
        help="re-score a result bundle and write an accepted-result projection",
    )
    rescore_bundle_parser.add_argument("bundle", type=Path)
    rescore_bundle_parser.add_argument("--suite-dir", required=True, type=Path)
    rescore_bundle_parser.add_argument("--out", required=True, type=Path)
    rescore_bundle_parser.add_argument("--validated-at", default="1970-01-01T00:00:00Z")
    verify_submission_parser = subparsers.add_parser(
        "verify-submission",
        help="validate and re-score a local result bundle for submission status update",
    )
    verify_submission_parser.add_argument("bundle", type=Path)
    verify_submission_parser.add_argument("--suite-dir", required=True, type=Path)
    verify_submission_parser.add_argument("--projection-out", required=True, type=Path)
    verify_submission_parser.add_argument("--out", type=Path)
    verify_submission_parser.add_argument("--validated-at", default="1970-01-01T00:00:00Z")
    verify_submission_parser.add_argument("--validator-commit")
    doctor_parser = subparsers.add_parser("doctor", help="check localbench local-run readiness")
    doctor_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    doctor_parser.add_argument("--cache-dir", type=Path)
    status_parser = subparsers.add_parser("status", help="show campaign progress")
    status_parser.add_argument("campaign_dir", type=Path)
    collect_parser = subparsers.add_parser("collect", help="write a redacted campaign support bundle")
    collect_parser.add_argument("campaign_dir", type=Path)
    collect_parser.add_argument("--out", required=True, type=Path)
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
        help="build scorer-side board_v2.json and release manifest",
    )
    board_parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    board_parser.add_argument("--out", type=Path, default=DEFAULT_OUT_V2)
    board_parser.add_argument("--curation", type=Path)
    board_parser.add_argument("--frozen-timestamp")
    board_parser.add_argument("--check-parity", dest="check_parity", action="store_true", default=True)
    board_parser.add_argument("--no-check-parity", dest="check_parity", action="store_false")
    tc_json_parser = subparsers.add_parser("tc-json", help="run the tc_json_v1 Tool-calling axis")
    tc_json_parser.add_argument("--endpoint", required=True, help="OpenAI-compatible base URL")
    tc_json_parser.add_argument("--model", required=True, help="model name to send in requests")
    tc_json_parser.add_argument("--suite-dir", type=Path, default=Path("..") / "suite" / "v1")
    tc_json_parser.add_argument("--out", type=Path, required=True)
    tc_json_parser.add_argument("--api-key-env")
    tc_json_parser.add_argument("--max-items", type=int)
    tc_json_parser.add_argument("--concurrency", type=int, default=4)
    return parser


def _run(args: argparse.Namespace) -> int:
    api_key = _api_key(args.api_key_env)
    if args.resume is not None:
        _populate_resume_args(args)
    if args.endpoint is None or args.model is None:
        print("error      --endpoint and --model are required unless --resume is used", file=sys.stderr)
        return 2
    if args.publishable and args.sampler_seed is None:
        print("error      --publishable requires --sampler-seed", file=sys.stderr)
        return 2
    tier = _resolved_run_tier(args.suite, args.tier)
    if args.dry_run:
        return _run_dry(args, tier)
    out = args.out or default_output_path(args.model, tier)
    try:
        bench_choice, scorer_gates, suite_axis_map = _scorer_gates(args, tier)
        if not args.skip_preflight:
            anyio.run(_preflight_endpoint, args.endpoint, args.model, api_key)
            anyio.run(_preflight_smoke, args, tier, api_key, bench_choice)
        if args.preflight:
            print("preflight ok")
            return 0
        if not args.no_supervisor:
            return _run_supervised(args, tier, out)
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
                resume=args.resume,
                publishable=args.publishable,
                sampler_seed=args.sampler_seed,
                model_file=args.model_file,
                model_family=args.model_family,
                quant_label=args.quant_label,
                model_format=args.model_format,
                tokenizer_file=args.tokenizer_file,
                chat_template_file=args.chat_template_file,
                runtime_name=args.runtime_name,
                runtime_version=args.runtime_version,
                kv_cache_quant=args.kv_cache_quant,
                ctx_len_configured=args.ctx_len_configured,
                parallel_slots=args.parallel_slots,
                build_flags=args.build_flags,
                runner_build_id=args.runner_build_id,
            ),
        )
    except EndpointPreflightError as error:
        print(f"error      {error}")
        return EXIT_PREFLIGHT_FAILED
    except UnsafeResumeError as error:
        print(f"error      {error}")
        return EXIT_UNSAFE_RESUME
    except CheckpointCorruptionError as error:
        print(f"error      {error}")
        return EXIT_CHECKPOINT_CORRUPTION
    except (RuntimeError, OSError) as error:
        print(f"error      {error}")
        return EXIT_INTERNAL_RUNNER_BUG
    if scorer_gates:
        _append_scorer_gated_benches(record, scorer_gates, suite_axis_map)
        _rewrite_run_record(record, out)
    _print_summary(record)
    return EXIT_COMPLETE


def _populate_resume_args(args: argparse.Namespace) -> None:
    campaign_path = args.resume / "campaign.json"
    campaign = read_json_object(campaign_path)
    suite = campaign.get("suite")
    model = campaign.get("model")
    provider = campaign.get("provider")
    if isinstance(suite, dict):
        if args.suite_dir is None and isinstance(suite.get("suite_dir"), str):
            args.suite_dir = Path(suite["suite_dir"])
        if isinstance(suite.get("suite_id"), str):
            args.suite = suite["suite_id"]
    if isinstance(model, dict) and args.model is None and isinstance(model.get("declared_model_id"), str):
        args.model = model["declared_model_id"]
    if isinstance(provider, dict):
        if args.endpoint is None and isinstance(provider.get("endpoint"), str):
            args.endpoint = provider["endpoint"]
        if isinstance(provider.get("name"), str):
            args.provider = provider["name"]
    if args.tier is None and isinstance(campaign.get("tier"), str):
        args.tier = campaign["tier"]
    if isinstance(campaign.get("lane"), str):
        args.lane = campaign["lane"]


def _run_supervised(args: argparse.Namespace, tier: str, out: Path) -> int:
    paths = campaign_paths(out, args.resume)
    command = _worker_command(args, tier, out)
    return run_supervised(
        SupervisorConfig(
            command=command,
            campaign_root=paths.root,
            label=f"localbench:{args.model}",
            sample_interval_seconds=5.0,
        )
    )


def _worker_command(args: argparse.Namespace, tier: str, out: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "localbench",
        "run",
        "--endpoint",
        args.endpoint,
        "--model",
        args.model,
        "--bench",
        args.bench,
        "--tier",
        tier,
        "--concurrency",
        str(args.concurrency),
        "--provider",
        args.provider,
        "--out",
        str(out),
        "--lane",
        args.lane,
        "--reasoning-activation",
        args.reasoning_activation,
        "--no-supervisor",
        "--skip-preflight",
    ]
    _append_optional(command, "--api-key-env", args.api_key_env)
    _append_optional(command, "--max-items", args.max_items)
    _append_optional(command, "--suite", args.suite)
    _append_optional(command, "--suite-dir", args.suite_dir)
    _append_optional(command, "--suite-source", args.suite_source)
    _append_optional(command, "--cache-dir", args.cache_dir)
    _append_optional(command, "--price-in", args.price_in)
    _append_optional(command, "--price-out", args.price_out)
    _append_optional(command, "--reasoning-effort", args.reasoning_effort)
    _append_optional(command, "--hf-model-id", args.hf_model_id)
    _append_optional(command, "--max-tokens", args.max_tokens)
    _append_optional(command, "--resume", args.resume)
    _append_optional(command, "--sampler-seed", args.sampler_seed)
    _append_optional(command, "--model-file", args.model_file)
    _append_optional(command, "--model-family", args.model_family)
    _append_optional(command, "--quant-label", args.quant_label)
    _append_optional(command, "--model-format", args.model_format)
    _append_optional(command, "--tokenizer-file", args.tokenizer_file)
    _append_optional(command, "--chat-template-file", args.chat_template_file)
    _append_optional(command, "--runtime-name", args.runtime_name)
    _append_optional(command, "--runtime-version", args.runtime_version)
    _append_optional(command, "--kv-cache-quant", args.kv_cache_quant)
    _append_optional(command, "--ctx-len-configured", args.ctx_len_configured)
    _append_optional(command, "--parallel-slots", args.parallel_slots)
    _append_optional(command, "--build-flags", args.build_flags)
    _append_optional(command, "--runner-build-id", args.runner_build_id)
    if args.accept_suite_terms:
        command.append("--accept-suite-terms")
    if args.publishable:
        command.append("--publishable")
    return command


def _append_optional(command: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def _validate_result_bundle_command(args: argparse.Namespace) -> int:
    try:
        result = validate_result_bundle_file(args.bundle, suite_dir=args.suite_dir)
    except (SubmissionValidationError, OSError, json.JSONDecodeError) as error:
        print(f"error      {error}", file=sys.stderr)
        return 2
    _write_or_print_result(result, args.out)
    return EXIT_COMPLETE


def _rescore_result_bundle_command(args: argparse.Namespace) -> int:
    try:
        projection = rescore_result_bundle(
            args.bundle,
            suite_dir=args.suite_dir,
            validated_at=args.validated_at,
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError) as error:
        print(f"error      {error}", file=sys.stderr)
        return 2
    write_json_file(args.out, projection)
    return EXIT_COMPLETE


def _verify_submission_command(args: argparse.Namespace) -> int:
    try:
        status_update = verify_submission(
            args.bundle,
            suite_dir=args.suite_dir,
            projection_out=args.projection_out,
            validated_at=args.validated_at,
            validator_commit=args.validator_commit,
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError) as error:
        print(f"error      {error}", file=sys.stderr)
        return 2
    _write_or_print_result(status_update, args.out)
    return EXIT_COMPLETE


def _write_or_print_result(result: dict[str, JsonValue], output_path: Path | None) -> None:
    if output_path is None:
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
        return
    write_json_file(output_path, result)


def _status(args: argparse.Namespace) -> int:
    campaign_dir = args.campaign_dir
    status = _read_optional_json(campaign_dir / "run.status.json")
    checkpoints = completed_benches(campaign_paths(campaign_dir / "localbench-run.json", campaign_dir))
    completed_items = status.get("completed_items") if isinstance(status.get("completed_items"), int) else 0
    total_items = status.get("total_items") if isinstance(status.get("total_items"), int) else 0
    current_bench = status.get("current_bench") if isinstance(status.get("current_bench"), str) else "-"
    state = status.get("state") if isinstance(status.get("state"), str) else "unknown"
    print(f"state     {state}")
    print(f"bench     {current_bench}")
    print(f"progress  {completed_items}/{total_items}")
    print(f"complete  {', '.join(sorted(checkpoints)) or '-'}")
    monitor = _monitor_tail(campaign_dir / "monitor" / "monitor.jsonl", 1)
    if monitor:
        monitor_status = monitor[-1].get("status")
        print(f"health    {monitor_status if isinstance(monitor_status, str) else 'unknown'}")
    return EXIT_COMPLETE


def _collect(args: argparse.Namespace) -> int:
    campaign_dir = args.campaign_dir
    bundle = {
        "schema_version": "localbench-support-bundle-v1",
        "campaign_dir": str(campaign_dir),
        "campaign": _redact(_read_optional_json(campaign_dir / "campaign.json")),
        "status": _redact(_read_optional_json(campaign_dir / "run.status.json")),
        "logs": {
            "run_tail": _redact(_tail_lines(campaign_dir / "logs" / "run.log")),
            "serve_tail": _redact(_tail_lines(campaign_dir / "logs" / "serve.log")),
        },
        "monitor_tail": _redact(_monitor_tail(campaign_dir / "monitor" / "monitor.jsonl", 20)),
        "checkpoint_files": sorted(path.name for path in (campaign_dir / "benchmarks").glob("*")),
        "system": {"platform": platform.platform(), "python": platform.python_version()},
    }
    atomic_write_json(bundle, args.out)
    print(f"wrote     {args.out}")
    return EXIT_COMPLETE


def _read_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _tail_lines(path: Path, limit: int = 40) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]


def _monitor_tail(path: Path, limit: int) -> list[dict]:
    rows: list[dict] = []
    for line in _tail_lines(path, limit):
        raw = json.loads(line)
        if isinstance(raw, dict):
            rows.append(raw)
    return rows


def _redact(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            redacted[key] = "***REDACTED***" if _secret_key(str(key)) else _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("api_key", "token", "secret", "password", "authorization"))


def _redact_text(value: str) -> str:
    value = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "***REDACTED***", value)
    return re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***REDACTED***", value)


def _tc_json(args: argparse.Namespace) -> int:
    api_key = _api_key(args.api_key_env)
    record = anyio.run(
        _run_tc_json_async,
        args,
        api_key,
    )
    aggregate_record = record["aggregate"]
    interval = aggregate_record["wilson_95_ci"]
    print(f"items     {aggregate_record['n']}")
    print(f"raw_asr   {aggregate_record['raw_asr']:.4f}")
    print(f"wilson95  [{interval['lo']:.4f}, {interval['hi']:.4f}]")
    print(f"band      {aggregate_record['band']}")
    print(f"wrote     {args.out}")
    return 0


async def _run_tc_json_async(args: argparse.Namespace, api_key: str | None):
    return await run_tc_json_v1(
        base_url=args.endpoint,
        model=args.model,
        suite_dir=args.suite_dir,
        out=args.out,
        api_key=api_key,
        max_items=args.max_items,
        concurrency=args.concurrency,
    )


async def _preflight_endpoint(
    endpoint: str,
    model: str,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
        try:
            response = await client.get(f"{endpoint.rstrip('/')}/models", headers=headers)
        except httpx.TransportError as error:
            raise EndpointPreflightError(
                "nothing is listening at "
                f"{endpoint.rstrip('/')}; start your llama-server or another "
                "OpenAI-compatible server before running localbench",
            ) from error
    if response.status_code >= 400:
        raise EndpointPreflightError(f"/v1/models returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except json.JSONDecodeError as error:
        raise EndpointPreflightError("/v1/models returned non-JSON") from error
    served_models = _served_model_ids(payload)
    if model not in served_models:
        models = ", ".join(sorted(served_models)) or "(none)"
        raise EndpointPreflightError(f"claimed model {model!r} is not served by /v1/models: {models}")


async def _preflight_smoke(
    args: argparse.Namespace,
    tier: str,
    api_key: str | None,
    bench_choice: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    _check_disk_headroom(args.out, estimated_bytes=10_000_000)
    with tempfile.TemporaryDirectory(prefix="localbench-preflight-") as tmp:
        try:
            await run_localbench(
                OrchestrateConfig(
                    endpoint=args.endpoint,
                    model=args.model,
                    suite=args.suite,
                    bench=bench_choice,
                    tier=tier,
                    concurrency=args.concurrency,
                    out=Path(tmp) / "campaign" / "localbench-run.json",
                    api_key=api_key,
                    max_items=1,
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
                    resume=None,
                ),
                transport=transport,
            )
        except Exception as error:
            raise EndpointPreflightError(f"preflight smoke failed: {error}") from error


def _served_model_ids(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    data = payload.get("data")
    if not isinstance(data, list):
        return set()
    ids: set[str] = set()
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.add(item["id"])
    return ids


def _check_disk_headroom(output_path: Path | None, estimated_bytes: int) -> None:
    probe = (output_path.parent if output_path is not None else Path.cwd()).resolve()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if shutil.disk_usage(probe).free <= estimated_bytes:
        raise EndpointPreflightError(f"insufficient disk headroom at {probe}")


def _scorer_gates(
    args: argparse.Namespace,
    tier: str,
) -> tuple[str, dict[str, ScorerGate], Mapping[str, JsonValue] | None]:
    ref = resolve_suite_dir(
        suite_id=args.suite,
        suite_dir=args.suite_dir,
        accept_suite_terms=args.accept_suite_terms,
        source=args.suite_source,
        cache_root=args.cache_dir,
    )
    suite = read_json_object(ref.path / "suite.json")
    suite_axes = suite.get("axes")
    suite_axis_map = suite_axes if isinstance(suite_axes, dict) else None
    warnings: list[str] = []
    resolved = resolve_run_benches(args.bench, suite)
    bench_choice = ",".join(resolved)
    rendered = render_benches(bench_choice, tier, args.max_items, ref.path, suite, warnings)
    gates: dict[str, ScorerGate] = {}
    available: list[str] = []
    for bench in rendered:
        warning = scorer_unavailable_warning(bench)
        if warning is None:
            available.append(bench.name)
            continue
        gates[bench.name] = (
            bench,
            warning,
            axis_key_for_bench(bench.name, suite_axis_map),
        )
    if not gates:
        return bench_choice, {}, suite_axis_map
    # Benches that do NOT render as HTTP items (e.g. appworld_c) are executed by the agentic branch
    # in run_localbench, not this scorer-gate path -- so they never enter `available`. Preserve them
    # in the returned bench choice; otherwise an unrelated gated HTTP bench would silently drop the
    # agentic campaign (run_agentic would see no appworld_c).
    rendered_names = {bench.name for bench in rendered}
    non_http = [name for name in resolved if name not in rendered_names]
    passthrough = available + non_http
    return ",".join(passthrough) if passthrough else _NO_SCORABLE_BENCH, gates, suite_axis_map


def _append_scorer_gated_benches(
    record: LocalbenchRun,
    gates: dict[str, ScorerGate],
    suite_axes: Mapping[str, JsonValue] | None = None,
) -> None:
    record["warnings"] = [
        warning for warning in record["warnings"] if _NO_SCORABLE_BENCH not in warning
    ]
    for _bench, warning, axis in gates.values():
        mark_axis_not_measured(
            record["axis_status"],
            axis,
            reason="scorer_unavailable",
            detail=warning,
        )
        if warning not in record["warnings"]:
            record["warnings"].append(warning)
    record["scores"] = score_summary(record["benches"], record["axis_status"], suite_axes=suite_axes)
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


def _rewrite_run_record(record: LocalbenchRun, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")


def _optional_text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _summary_score(record: LocalbenchRun) -> float:
    scores = record.get("scores")
    if isinstance(scores, dict):
        headline = scores.get("headline_score")
        if isinstance(headline, int | float):
            return float(headline)
        partial = scores.get("partial_composite")
        if isinstance(partial, int | float):
            return float(partial)
    composite_value = record.get("composite")
    return float(composite_value) if isinstance(composite_value, int | float) else 0.0


def _fetch_suite(args: argparse.Namespace) -> int:
    if args.source is not None and args.source_url is not None:
        print("error      use only one of --source or --source-url")
        return 2
    try:
        if args.source_url is not None:
            ref = fetch_suite_from_manifest_url(
                RemoteSuiteFetch(
                    accept_suite_terms=args.accept_suite_terms,
                    manifest_url=args.source_url,
                    cache_root=args.cache_dir,
                ),
            )
        else:
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
    if args.submit_command == "keygen":
        return _submit_keygen(args)
    if args.submit_command == "ticket":
        return _submit_ticket(args)
    if args.submit_command == "pack":
        return _submit_pack(args)
    if args.submit_command == "upload":
        return _submit_upload(args)
    if args.submit_command == "status":
        return _submit_status(args)
    if args.submit_command == "admin-verify":
        return _submit_admin_verify(args)
    if args.submit_command == "verify-offline":
        return _submit_verify_offline(args)
    print("error      unsupported submit command")
    return 2


def _submit_keygen(args: argparse.Namespace) -> int:
    if args.out.exists():
        print(f"error      key already exists: {args.out}")
        return 2
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        public_key = write_private_key(args.out)
    except (Ed25519SeedError, OSError, ValueError) as error:
        print(f"error      {error}")
        return 2
    print(f"key        {args.out}")
    print(f"public_key {public_key}")
    return 0


def _submit_ticket(args: argparse.Namespace) -> int:
    try:
        public_key = args.public_key or load_private_key(args.signing_key).public_key.hex()
        ticket = request_submission_ticket(
            SubmissionTicketRequest(
                public_key=public_key,
                site=args.site,
                suite_id=args.suite,
            ),
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as handle:
            json.dump(ticket, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError, ValueError) as error:
        print(f"error      {error}")
        return 2
    print(f"submission {ticket['submission_id']}")
    print(f"status     {ticket['status']}")
    print(f"ticket     {args.out}")
    return 0


def _submit_pack(args: argparse.Namespace) -> int:
    try:
        manifest = pack_submission_bundle(
            run_path=args.run,
            suite_dir=args.suite_dir,
            model_name=args.model_name,
            signing_key_path=args.signing_key,
            out_path=args.out,
            offline=args.offline,
            ticket_path=args.ticket,
            created_at=args.created_at,
            run_nonce=args.run_nonce,
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError) as error:
        print(f"error      {error}")
        return 2
    print(f"bundle    {args.out}")
    print(f"payload   {manifest['payload_sha256']}")
    return 0


def _submit_upload(args: argparse.Namespace) -> int:
    try:
        ticket = read_submission_ticket(args.ticket)
        result = upload_submission_bundle(
            SubmissionUploadRequest(
                bundle_path=args.bundle,
                ticket=ticket,
            ),
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError) as error:
        print(f"error      {error}")
        return 2
    print(f"submission {result.get('submission_id', ticket['submission_id'])}")
    print(f"status     {result.get('status', 'uploaded')}")
    return 0


def _submit_status(args: argparse.Namespace) -> int:
    try:
        result = complete_uploaded_bundle(
            SubmissionStatusRequest(site=args.site, submission_id=args.submission_id),
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError) as error:
        print(f"error      {error}")
        return 2
    print(f"submission {result.get('submission_id', args.submission_id)}")
    print(f"status     {result.get('status', 'unknown')}")
    return 0


def _submit_admin_verify(args: argparse.Namespace) -> int:
    admin_secret = os.environ.get(args.admin_secret_env)
    if not admin_secret:
        print(f"error      set {args.admin_secret_env} before running admin verification")
        return 2
    try:
        submissions = list_admin_submissions(
            AdminSubmissionListRequest(
                admin_secret=admin_secret,
                limit=args.limit,
                site=args.site,
                status=args.status,
            ),
        )
    except (SubmissionValidationError, httpx.HTTPError) as error:
        print(f"error      {error}")
        return 2
    args.work_dir.mkdir(parents=True, exist_ok=True)
    print(f"pending    {len(submissions)}")
    for submission in submissions:
        submission_id = submission["submission_id"]
        bundle_path = args.work_dir / f"{submission_id}.lbsub.zip"
        verification_path = args.work_dir / f"{submission_id}.verification.json"
        status = "needs_review"
        error_text: str | None = None
        try:
            mark_admin_verification_result(
                AdminVerificationResultRequest(
                    admin_secret=admin_secret,
                    site=args.site,
                    status="verifying",
                    submission_id=submission_id,
                ),
            )
        except (SubmissionValidationError, httpx.HTTPError) as error:
            print(f"error      {submission_id}: {error}")
            return 2
        try:
            download_admin_bundle(
                AdminBundleDownloadRequest(
                    download_url=submission["download_url"],
                    expected_sha256=submission.get("bundle_sha256"),
                    out_path=bundle_path,
                ),
            )
            result = verify_bundle_offline(bundle_path, suite_dir=args.suite_dir, out_path=verification_path)
            if result.get("submission_id") != submission_id:
                raise SubmissionValidationError("bundle ticket submission_id does not match D1 submission")
        except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError) as error:
            status = "rejected"
            error_text = str(error)
            verification_path.parent.mkdir(parents=True, exist_ok=True)
            with verification_path.open("w", encoding="utf-8") as handle:
                json.dump({"error": error_text, "status": status, "submission_id": submission_id}, handle, indent=2, sort_keys=True)
                handle.write("\n")
        try:
            mark_admin_verification_result(
                AdminVerificationResultRequest(
                    admin_secret=admin_secret,
                    error=error_text,
                    site=args.site,
                    status=status,
                    submission_id=submission_id,
                ),
            )
        except (SubmissionValidationError, httpx.HTTPError) as error:
            print(f"error      {submission_id}: {error}")
            return 2
        print(f"submission {submission_id}")
        print(f"status     {status}")
        print(f"verification {verification_path}")
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
    bench_choice = ",".join(resolve_run_benches(args.bench, suite))
    benches = render_benches(bench_choice, tier, args.max_items, ref.path, suite, warnings)
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
    for name, bench_aggregate in record["benches"].items():
        print(
            f"{name:<14} "
            f"{bench_aggregate['raw_accuracy'] * 100:>6.1f}% "
            f"{bench_aggregate['chance_corrected'] * 100:>9.1f}% "
            f"{bench_aggregate['termination_rate'] * 100:>7.1f}% "
            f"{bench_aggregate['conditional_accuracy'] * 100:>7.1f}% "
            f"{bench_aggregate['n']:>4} "
            f"{bench_aggregate['n_extraction_failures']:>5} "
            f"{bench_aggregate['n_errors']:>4}",
        )
    totals = record["totals"]
    print(f"composite  {_summary_score(record) * 100:.1f}%")
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


if __name__ == "__main__":
    raise SystemExit(main())
