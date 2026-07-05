"""Command-line interface for localbench."""

from __future__ import annotations

import argparse
import importlib.metadata
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

from localbench.bounded_final_profiles import (
    BOUNDED_FINAL_PROFILE_CHOICES,
    BoundedFinalProfileChoice,
)
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
from localbench._types import ItemResult, JsonObject, JsonValue
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
from localbench.lane_spec import lane_spec_id_for_lane
from localbench.persistence import atomic_write_json
from localbench.prompt_rendering import REASONING_ACTIVATIONS
from localbench.providers import provider_choices
from localbench.run_plan import resolve_run_benches
from localbench.scoring.paired_delta import (
    CompareResult,
    compare_run_files,
    format_honest_delta,
)
from localbench.scoring.axis_status import axis_key_for_bench, mark_axis_not_measured
from localbench.scoring.axes import AXES, STATIC_SUITE_INDEX_VERSION, STATIC_SUITE_WEIGHTS
from localbench.scoring.board import BoardBuildError, write_board
from localbench.scoring.board_support import DEFAULT_OUT_V2, DEFAULT_RUNS_DIR
from localbench.submissions.bundle import pack_submission_bundle
from localbench.submissions.canon import canonical_json_bytes, write_json_file
from localbench.submissions.decision_log import (
    DecisionLogError,
    append_decision_log,
    format_decision_log_entries,
    verify_log,
)
from localbench.submissions.foundation_scores import score_summary
from localbench.submissions.client import (
    AdminDecisionRequest,
    AdminVerificationRequest,
    SiteCredentials,
    SubmissionStatusRequest,
    SubmissionTicketRequest,
    SubmissionUploadRequest,
    get_submission_status,
    post_admin_decision,
    post_admin_verification,
    raw_bundle_sha256,
    read_submission_envelope,
    request_submission_ticket,
    upload_submission_bundle,
)
from localbench.submissions.crypto import load_private_key
from localbench.submissions.keys import Ed25519SeedError, write_private_key
from localbench.submissions.submit_run import (
    DEFAULT_SITE,
    SubmitRunError,
    SubmitRunOptions,
    default_signing_key_path,
    submit_finished_run,
)
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
    KNOWN_SUITE_IDS,
    RemoteSuiteFetch,
    SuiteResolutionError,
    fetch_suite,
    fetch_suite_from_manifest_url,
    normalize_suite_id,
    resolve_suite_dir,
    suite_cache_root,
)
from localbench.supervisor import SupervisorConfig, run_supervised
from localbench.serving.options import ServeBenchOptions
from localbench.serving.runner import run_orchestrated_bench

_REASONING_EFFORT_CHOICES: Final[tuple[ReasoningEffortChoice, ...]] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
_REASONING_ACTIVATION_CHOICES: Final[tuple[ReasoningActivationChoice, ...]] = REASONING_ACTIVATIONS
_PROFILE_CHOICES: Final[tuple[BoundedFinalProfileChoice, ...]] = BOUNDED_FINAL_PROFILE_CHOICES
_NO_SCORABLE_BENCH: Final = "__localbench_no_scorable_bench__"
_CLI_VERSION_FALLBACK: Final = "0.1.0"
_PUBLISHABLE_WARNING: Final = (
    "this run will not be submittable as publishable — add --publishable --sampler-seed <n>"
)
_HEADLINE_AXIS_KEYS: Final = tuple(axis.key for axis in AXES if axis.role == "headline")
_STATIC_AXIS_KEYS: Final = tuple(STATIC_SUITE_WEIGHTS)
ScorerGate: TypeAlias = tuple[RenderedBench, str, str]


class EndpointPreflightError(RuntimeError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    """Run the localbench CLI."""
    _prefer_utf8_stdout()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv == ["--version"]:
        print(_package_version())
        return 0
    parser = _parser()
    args = parser.parse_args(raw_argv)
    if args.command == "run":
        return _run(args)
    if args.command == "bench":
        return _bench(args)
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
    parser = argparse.ArgumentParser(
        prog="localbench",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Quickstart:\n"
            "  localbench fetch-suite --site https://local-bench.ai --suite "
            "suite-v1-text-code-agentic-5axis-v1 --accept-suite-terms\n"
            "  localbench bench --runtime llama.cpp --model-file <gguf> --model-id <slug> "
            "--ctx <n> --seed <n>\n"
            "  localbench run --endpoint <OpenAI-compatible url> --model <name>\n"
            "  localbench submit run --run <run-or-campaign> --suite-dir <suite-dir>\n"
            "Submission guide: https://local-bench.ai/submit"
        ),
    )
    parser.add_argument("--version", action="store_true", help="print the localbench package version")
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
        choices=("answer-only", "capped-thinking", "api-uncapped", "bounded-final-v1"),
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
        "--profile",
        choices=_PROFILE_CHOICES,
        default="auto",
        help="bounded-final-v1 execution profile",
    )
    run_parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="cap per-item max_tokens (min'd with the bench value); use for bounded local context windows",
    )
    run_parser.add_argument("--publishable", action="store_true", help="pin sampler settings for submission")
    run_parser.add_argument("--sampler-temperature", type=float)
    run_parser.add_argument("--sampler-top-k", type=int)
    run_parser.add_argument("--sampler-top-p", type=float)
    run_parser.add_argument("--sampler-min-p", type=float)
    run_parser.add_argument("--sampler-seed", type=int)
    run_parser.add_argument("--determinism-policy")
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
    run_parser.add_argument("--runtime-backend")
    run_parser.add_argument("--cuda-version")
    run_parser.add_argument("--runner-build-id")
    bench_parser = subparsers.add_parser("bench", help="launch a pinned local server and run a suite")
    bench_parser.add_argument("--runtime", choices=("llama.cpp", "vllm"), required=True)
    model_input = bench_parser.add_mutually_exclusive_group(required=True)
    model_input.add_argument("--model-file", type=Path)
    model_input.add_argument("--model-ref")
    bench_parser.add_argument("--model-id", required=True)
    bench_parser.add_argument("--server-bin", type=Path)
    bench_parser.add_argument("--ctx", type=int, required=True)
    bench_parser.add_argument("--determinism", choices=("strict", "throughput"), default="strict")
    bench_parser.add_argument("--tier", choices=("quick", "standard"), default="standard")
    bench_parser.add_argument(
        "--bench",
        default="all",
        help="'all', a single bench name, or a comma-separated list of bench names",
    )
    bench_parser.add_argument(
        "--lane",
        choices=("answer-only", "capped-thinking", "api-uncapped", "bounded-final-v1"),
        default="answer-only",
    )
    bench_parser.add_argument(
        "--reasoning-activation",
        choices=REASONING_ACTIVATIONS,
        default=None,
        help="model-family activation used with --hf-model-id in local capped-thinking",
    )
    bench_parser.add_argument(
        "--hf-model-id",
        default=None,
        help="served model HF repo for local capped-thinking chat-template rendering",
    )
    bench_parser.add_argument(
        "--profile",
        choices=_PROFILE_CHOICES,
        default="auto",
        help="bounded-final-v1 execution profile",
    )
    bench_parser.add_argument("--seed", type=int, required=True)
    bench_parser.add_argument("--max-items", type=int)
    bench_parser.add_argument(
        "--wsl-venv-python",
        default="~/appworld-harness/venv/bin/python3",
        help="WSL Python used for the AppWorld-C worker",
    )
    bench_parser.add_argument(
        "--appworld-root",
        default="/home/michael/appworld-data",
        help="WSL-native APPWORLD_ROOT for AppWorld-C",
    )
    bench_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    bench_parser.add_argument("--suite-source", type=Path)
    bench_parser.add_argument("--suite-dir", type=Path)
    bench_parser.add_argument("--out", type=Path)
    bench_parser.add_argument("--resume", type=Path)
    bench_parser.add_argument("--retry-errored", action="store_true")
    bench_parser.add_argument("--cache-dir", type=Path)
    bench_parser.add_argument("--threads", type=int, default=8)
    bench_parser.add_argument("--threads-batch", type=int, default=8)
    fetch_parser = subparsers.add_parser(
        "fetch-suite",
        help="cache a verified public suite bundle from a local source or manifest URL",
    )
    fetch_parser.add_argument("--suite", default=DEFAULT_SUITE_ID)
    fetch_parser.add_argument("--source", type=Path)
    fetch_parser.add_argument("--source-url")
    fetch_parser.add_argument("--site")
    fetch_parser.add_argument("--accept-suite-terms", action="store_true")
    fetch_parser.add_argument("--cache-dir", type=Path)
    _add_bypass_args(fetch_parser)
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
    ticket_parser.add_argument("--bundle", required=True, type=Path)
    ticket_key_group = ticket_parser.add_mutually_exclusive_group(required=True)
    ticket_key_group.add_argument("--public-key")
    ticket_key_group.add_argument("--signing-key", type=Path)
    ticket_key_group.add_argument("--submitter-id")
    ticket_parser.add_argument("--declared-model-slug")
    ticket_parser.add_argument("--out", type=Path, default=Path("ticket.json"))
    _add_bypass_args(ticket_parser)
    _add_admin_secret_args(ticket_parser)
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
    upload_parser.add_argument("--site", required=True)
    upload_parser.add_argument("--ticket", required=True, type=Path)
    upload_parser.add_argument("--bundle", required=True, type=Path)
    _add_bypass_args(upload_parser)
    status_parser = submit_subparsers.add_parser("status", help="poll online submission status")
    status_parser.add_argument("ticket_id")
    status_parser.add_argument("--site", required=True)
    _add_bypass_args(status_parser)
    admin_verify_parser = submit_subparsers.add_parser(
        "admin-verify",
        help="re-score a local result bundle and post verifier status",
    )
    admin_verify_parser.add_argument("--site", required=True)
    admin_verify_parser.add_argument("--submission-id", required=True)
    admin_verify_parser.add_argument("--bundle", required=True, type=Path)
    admin_verify_parser.add_argument("--suite-dir", required=True, type=Path)
    admin_verify_parser.add_argument("--projection-out", required=True, type=Path)
    admin_verify_parser.add_argument("--out", type=Path)
    admin_verify_parser.add_argument("--validated-at", default="1970-01-01T00:00:00Z")
    admin_verify_parser.add_argument("--validator-commit")
    _add_bypass_args(admin_verify_parser)
    _add_admin_secret_args(admin_verify_parser)
    admin_decision_parser = submit_subparsers.add_parser(
        "admin-decision",
        help="post a publish-state decision for a verified submission",
    )
    admin_decision_parser.add_argument("--site", required=True)
    admin_decision_parser.add_argument("--submission-id", required=True)
    admin_decision_parser.add_argument(
        "--publish-state",
        required=True,
        choices=("hidden", "preview", "published"),
    )
    _add_bypass_args(admin_decision_parser)
    _add_admin_secret_args(admin_decision_parser)
    log_parser = submit_subparsers.add_parser("log", help="inspect the signed private decision log")
    log_subparsers = log_parser.add_subparsers(dest="log_command", required=True)
    log_subparsers.add_parser("verify", help="verify the signed decision log")
    log_show_parser = log_subparsers.add_parser("show", help="show recent decision log entries")
    log_show_parser.add_argument("--tail", type=int, default=20)
    verify_parser = submit_subparsers.add_parser(
        "verify-offline",
        help="verify and re-score an offline submission bundle",
    )
    verify_parser.add_argument("bundle", type=Path)
    verify_parser.add_argument("--suite-dir", required=True, type=Path)
    verify_parser.add_argument("--out", required=True, type=Path)
    submit_run_parser = submit_subparsers.add_parser("run", help="pack and submit a finished run")
    submit_run_source = submit_run_parser.add_mutually_exclusive_group(required=True)
    submit_run_source.add_argument("--run", type=Path)
    submit_run_source.add_argument("--bundle", type=Path)
    submit_run_parser.add_argument("--site")
    submit_run_parser.add_argument("--suite-dir", type=Path)
    submit_run_parser.add_argument("--signing-key", type=Path)
    submit_run_parser.add_argument("--display-name")
    submit_run_parser.add_argument("--dry-run", action="store_true")
    _add_bypass_args(submit_run_parser)
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
    verify_submission_parser.add_argument("--origin", choices=("project_anchor", "community"), default="project_anchor")
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


def _add_bypass_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bypass-token")
    parser.add_argument("--bypass-token-file", type=Path)


def _add_admin_secret_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--admin-secret-env", default="LOCALBENCH_ADMIN_SECRET")
    parser.add_argument("--admin-secret-file", type=Path)


def _package_version() -> str:
    # Distribution is local-bench-ai on PyPI (local-bench/localbench were blocked
    # by / belong to an unrelated project); older names kept for editable installs
    # predating the renames.
    for distribution in ("local-bench-ai", "local-bench", "localbench"):
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return _CLI_VERSION_FALLBACK


def _publishability_warning_needed(args: argparse.Namespace) -> bool:
    return not bool(getattr(args, "publishable", False)) or getattr(args, "sampler_seed", None) is None


def _print_suite_resolution_error(error: SuiteResolutionError, suite_id: str) -> None:
    normalized = normalize_suite_id(suite_id)
    print(f"error      {error}")
    print(f"known suite ids: {', '.join(KNOWN_SUITE_IDS)}")
    print(f"fetch-suite --site {DEFAULT_SITE} --suite {normalized} --accept-suite-terms")


def _print_doctor_next_steps(args: argparse.Namespace) -> None:
    suite_id = normalize_suite_id(args.suite)
    if not (suite_cache_root(args.cache_dir) / suite_id).exists():
        print(f"next      localbench fetch-suite --site {DEFAULT_SITE} --suite {suite_id} --accept-suite-terms")
    if not default_signing_key_path().exists():
        print("next      submit run will create ~/.localbench/submitter_ed25519.pem if needed")
    if not os.environ.get("LOCALBENCH_ATTESTER_KEY_FILE"):
        print("next      LOCALBENCH_ATTESTER_KEY_FILE unset; attestations are project-anchor-only")


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
    if args.lane != "bounded-final-v1" and args.profile != "auto":
        print("error      --profile only allowed with --lane bounded-final-v1", file=sys.stderr)
        return 2
    if _publishability_warning_needed(args):
        print(f"warning    {_PUBLISHABLE_WARNING}")
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
                profile=_profile(getattr(args, "profile", "auto")),
                provider=args.provider,
                reasoning_effort=_reasoning_effort(args.reasoning_effort),
                hf_model_id=args.hf_model_id,
                reasoning_activation=_reasoning_activation(args.reasoning_activation),
                max_tokens=args.max_tokens,
                resume=args.resume,
                publishable=args.publishable,
                sampler_temperature=args.sampler_temperature,
                sampler_top_k=args.sampler_top_k,
                sampler_top_p=args.sampler_top_p,
                sampler_min_p=args.sampler_min_p,
                sampler_seed=args.sampler_seed,
                determinism_policy=args.determinism_policy,
                model_file=args.model_file,
                model_family=args.model_family,
                quant_label=args.quant_label,
                model_format=args.model_format,
                tokenizer_file=args.tokenizer_file,
                chat_template_file=args.chat_template_file,
                tokenizer_digest_source="external.file" if args.tokenizer_file is not None else None,
                chat_template_digest_source="server.override" if args.chat_template_file is not None else None,
                runtime_name=args.runtime_name,
                runtime_version=args.runtime_version,
                kv_cache_quant=args.kv_cache_quant,
                ctx_len_configured=args.ctx_len_configured,
                parallel_slots=args.parallel_slots,
                build_flags=args.build_flags,
                runtime_backend=args.runtime_backend,
                cuda_version=args.cuda_version,
                runner_build_id=args.runner_build_id,
            ),
        )
    except SuiteResolutionError as error:
        _print_suite_resolution_error(error, args.suite)
        return 2
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
    _print_summary(record, out)
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
        "--profile",
        getattr(args, "profile", "auto"),
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
    _append_optional(command, "--sampler-temperature", args.sampler_temperature)
    _append_optional(command, "--sampler-top-k", args.sampler_top_k)
    _append_optional(command, "--sampler-top-p", args.sampler_top_p)
    _append_optional(command, "--sampler-min-p", args.sampler_min_p)
    _append_optional(command, "--sampler-seed", args.sampler_seed)
    _append_optional(command, "--determinism-policy", args.determinism_policy)
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
    _append_optional(command, "--runtime-backend", args.runtime_backend)
    _append_optional(command, "--cuda-version", args.cuda_version)
    _append_optional(command, "--runner-build-id", args.runner_build_id)
    if args.accept_suite_terms:
        command.append("--accept-suite-terms")
    if args.publishable:
        command.append("--publishable")
    return command


def _append_optional(command: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def _bench(args: argparse.Namespace) -> int:
    usage_error = _bench_reasoning_usage_error(args)
    if usage_error is None and args.retry_errored and args.resume is None:
        usage_error = "--retry-errored requires --resume"
    if usage_error is not None:
        print(f"error      {usage_error}", file=sys.stderr)
        return 2
    options = ServeBenchOptions(
        runtime=args.runtime,
        model_file=args.model_file,
        model_ref=args.model_ref,
        model_id=args.model_id,
        server_bin=args.server_bin,
        ctx=args.ctx,
        determinism=args.determinism,
        tier=args.tier,
        bench=args.bench,
        lane=_lane(args.lane),
        profile=_profile(getattr(args, "profile", "auto")),
        seed=args.seed,
        max_items=args.max_items,
        suite=args.suite,
        suite_source=args.suite_source,
        suite_dir=args.suite_dir,
        out=args.out,
        resume=args.resume,
        retry_errored=args.retry_errored,
        cache_dir=args.cache_dir,
        threads=args.threads,
        threads_batch=args.threads_batch,
        reasoning_activation=_optional_reasoning_activation(args.reasoning_activation),
        hf_model_id=args.hf_model_id,
        wsl_venv_python=getattr(
            args,
            "wsl_venv_python",
            "~/appworld-harness/venv/bin/python3",
        ),
        appworld_root=getattr(args, "appworld_root", "/home/michael/appworld-data"),
    )
    try:
        record = anyio.run(
            run_orchestrated_bench,
            options,
        )
    except SuiteResolutionError as error:
        _print_suite_resolution_error(error, args.suite)
        return 2
    except NotImplementedError as error:
        print(f"error      {error}", file=sys.stderr)
        return 2
    except UnsafeResumeError as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_UNSAFE_RESUME
    except CheckpointCorruptionError as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_CHECKPOINT_CORRUPTION
    except (RuntimeError, OSError) as error:
        print(f"error      {error}", file=sys.stderr)
        return EXIT_INTERNAL_RUNNER_BUG
    _print_summary(record, _bench_output_path(options))
    return EXIT_COMPLETE


def _bench_reasoning_usage_error(args: argparse.Namespace) -> str | None:
    reasoning_activation = args.reasoning_activation
    hf_model_id = args.hf_model_id
    profile = getattr(args, "profile", "auto")
    if args.lane == "capped-thinking":
        if profile != "auto":
            return "--profile only allowed with --lane bounded-final-v1"
        missing: list[str] = []
        if reasoning_activation is None:
            missing.append("--reasoning-activation")
        if hf_model_id is None:
            missing.append("--hf-model-id")
        if missing:
            return f"--lane capped-thinking requires {_joined_flags(missing)}"
        return None
    if args.lane == "bounded-final-v1":
        if reasoning_activation is not None:
            return "--reasoning-activation only allowed with --lane capped-thinking"
        return None
    rejected: list[str] = []
    if profile != "auto":
        rejected.append("--profile")
    if reasoning_activation is not None:
        rejected.append("--reasoning-activation")
    if hf_model_id is not None:
        rejected.append("--hf-model-id")
    if rejected:
        return f"{_joined_flags(rejected)} only allowed with --lane capped-thinking or bounded-final-v1"
    return None


def _bench_output_path(options: ServeBenchOptions) -> Path:
    root = options.resume or options.out or Path("runs") / "bench" / options.model_id
    return root / "localbench-run.json"


def _joined_flags(flags: list[str]) -> str:
    if len(flags) == 1:
        return flags[0]
    return f"{', '.join(flags[:-1])} and {flags[-1]}"


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
            origin=args.origin,
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


def _site_credentials(args: argparse.Namespace, admin_secret: str | None = None) -> SiteCredentials:
    return SiteCredentials(
        admin_secret=admin_secret,
        bypass_token=_bypass_token(args),
        site=args.site,
    )


def _bypass_token(args: argparse.Namespace) -> str | None:
    token_file = getattr(args, "bypass_token_file", None)
    if token_file is not None:
        return _secret_from_file(token_file)
    token = getattr(args, "bypass_token", None)
    if token:
        return str(token).strip()
    env_token = os.environ.get("LOCALBENCH_PRIVATE_BYPASS_TOKEN")
    return env_token.strip() if env_token else None


def _optional_admin_secret(args: argparse.Namespace) -> str | None:
    secret_file = getattr(args, "admin_secret_file", None)
    if secret_file is not None:
        return _secret_from_file(secret_file)
    env_name = getattr(args, "admin_secret_env", "LOCALBENCH_ADMIN_SECRET")
    env_secret = os.environ.get(env_name)
    return env_secret.strip() if env_secret else None


def _required_admin_secret(args: argparse.Namespace) -> str:
    secret = _optional_admin_secret(args)
    if secret is None:
        env_name = getattr(args, "admin_secret_env", "LOCALBENCH_ADMIN_SECRET")
        raise SubmissionValidationError(f"set {env_name} or pass --admin-secret-file")
    return secret


def _secret_from_file(path: Path) -> str:
    secret = path.read_text(encoding="utf-8").strip()
    if not secret:
        raise SubmissionValidationError(f"secret file is empty: {path}")
    return secret


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
                    profile=_profile(getattr(args, "profile", "auto")),
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
        lane_spec_id=lane_spec_id_for_lane(_record_lane(record) or ""),
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
        max_tokens = item.get("max_tokens")
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool):
            result["max_tokens"] = max_tokens
        generated_tokens = item.get("generated_tokens")
        if isinstance(generated_tokens, dict):
            result["generated_tokens"] = dict(generated_tokens)
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


def _record_lane(record: LocalbenchRun) -> str | None:
    suite = record["manifest"].get("suite")
    if not isinstance(suite, dict):
        return None
    lane = suite.get("lane")
    return lane if isinstance(lane, str) else None


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
    remote_sources = [source for source in (args.source_url, args.site) if source is not None]
    if args.source is not None and remote_sources:
        print("error      use only one of --source, --source-url, or --site")
        return 2
    if len(remote_sources) > 1:
        print("error      use only one of --source-url or --site")
        return 2
    try:
        source_url = args.source_url
        if args.site is not None:
            source_url = f"{args.site.rstrip('/')}/api/suites/{normalize_suite_id(args.suite)}/manifest"
        if source_url is not None:
            ref = fetch_suite_from_manifest_url(
                RemoteSuiteFetch(
                    accept_suite_terms=args.accept_suite_terms,
                    bypass_token=_bypass_token(args),
                    cache_root=args.cache_dir,
                    manifest_url=source_url,
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
        _print_suite_resolution_error(error, args.suite)
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
            _print_suite_resolution_error(error, args.suite)
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
    if args.submit_command == "admin-decision":
        return _submit_admin_decision(args)
    if args.submit_command == "log":
        return _submit_log(args)
    if args.submit_command == "verify-offline":
        return _submit_verify_offline(args)
    if args.submit_command == "run":
        return _submit_run(args)
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
        public_key = args.public_key
        if args.signing_key is not None:
            public_key = load_private_key(args.signing_key).public_key.hex()
        submitter_id = args.submitter_id
        bundle_sha = raw_bundle_sha256(args.bundle)
        ticket = request_submission_ticket(
            SubmissionTicketRequest(
                credentials=_site_credentials(args, admin_secret=_optional_admin_secret(args)),
                declared_model_slug=args.declared_model_slug,
                public_key=public_key,
                raw_bundle_sha256=bundle_sha,
                submitter_id=submitter_id,
            ),
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as handle:
            json.dump(ticket, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError, ValueError) as error:
        print(f"error      {error}")
        return 2
    if public_key is not None:
        print(f"public_key {public_key}")
    print(f"ticket_id  {ticket['ticket_id']}")
    print(f"bundle    {bundle_sha}")
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
        envelope = read_submission_envelope(args.ticket)
        result = upload_submission_bundle(
            SubmissionUploadRequest(
                bundle_path=args.bundle,
                credentials=_site_credentials(args),
                envelope=envelope,
            ),
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError) as error:
        print(f"error      {error}")
        return 2
    print(f"submission {result.get('submission_id', envelope['ticket_id'])}")
    print(f"status     {result.get('status', 'pending_verification')}")
    return 0


def _submit_status(args: argparse.Namespace) -> int:
    try:
        result = get_submission_status(
            SubmissionStatusRequest(credentials=_site_credentials(args), ticket_id=args.ticket_id),
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError) as error:
        print(f"error      {error}")
        return 2
    print(f"submission {result.get('submission_id', args.ticket_id)}")
    print(f"status     {result.get('status', 'unknown')}")
    return 0


def _submit_run(args: argparse.Namespace) -> int:
    try:
        result = submit_finished_run(
            SubmitRunOptions(
                site=args.site,
                run=args.run,
                bundle=args.bundle,
                suite_dir=args.suite_dir,
                signing_key=args.signing_key,
                display_name=args.display_name,
                bypass_token=_bypass_token(args),
                bypass_token_file=None,
                dry_run=args.dry_run,
            ),
        )
    except (SubmitRunError, SubmissionValidationError, OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error      {error}")
        return error.exit_code if isinstance(error, SubmitRunError) else 2
    for line in result.lines:
        print(line)
    return result.exit_code


def _submit_admin_verify(args: argparse.Namespace) -> int:
    try:
        admin_secret = _required_admin_secret(args)
        submission = get_submission_status(
            SubmissionStatusRequest(
                credentials=_site_credentials(args, admin_secret=admin_secret),
                ticket_id=args.submission_id,
            ),
        )
        status_update = verify_submission(
            args.bundle,
            suite_dir=args.suite_dir,
            projection_out=args.projection_out,
            validated_at=args.validated_at,
            validator_commit=args.validator_commit,
            origin=_submission_origin(submission),
        )
        result = post_admin_verification(
            AdminVerificationRequest(
                credentials=_site_credentials(args, admin_secret=admin_secret),
                status_update=status_update,
                submission_id=args.submission_id,
            ),
        )
        _write_or_print_result(status_update, args.out)
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError) as error:
        print(f"error      {error}")
        return 2
    try:
        append_decision_log(
            actor="maintainer",
            action="admin_verify",
            submission_id=args.submission_id,
            reason=_json_text(status_update.get("reason")) or "verification posted",
            extra={"status": _json_text(status_update.get("status")) or "unknown"},
        )
    except (DecisionLogError, OSError, ValueError) as error:
        print(f"error      server call succeeded but decision log write failed: {error}")
        return 1
    print(f"submission {result.get('submission_id', args.submission_id)}")
    print(f"status     {result.get('status', status_update.get('status', 'unknown'))}")
    print(f"projection {args.projection_out}")
    return 0


def _submission_origin(submission: JsonObject) -> str:
    origin = submission.get("origin")
    if not isinstance(origin, str):
        raise SubmissionValidationError("submission origin missing from server response")
    return origin


def _submit_admin_decision(args: argparse.Namespace) -> int:
    try:
        admin_secret = _required_admin_secret(args)
        result = post_admin_decision(
            AdminDecisionRequest(
                credentials=_site_credentials(args, admin_secret=admin_secret),
                publish_state=args.publish_state,
                submission_id=args.submission_id,
            ),
        )
    except (SubmissionValidationError, OSError, json.JSONDecodeError, httpx.HTTPError) as error:
        print(f"error      {error}")
        return 2
    try:
        append_decision_log(
            actor="maintainer",
            action="admin_decision",
            submission_id=args.submission_id,
            reason=f"publish_state={args.publish_state}",
            extra={"publish_state": args.publish_state},
        )
    except (DecisionLogError, OSError, ValueError) as error:
        print(f"error      server call succeeded but decision log write failed: {error}")
        return 1
    print(f"submission {result.get('submission_id', args.submission_id)}")
    print(f"publish    {result.get('publish_state', args.publish_state)}")
    return 0


def _submit_log(args: argparse.Namespace) -> int:
    if args.log_command == "verify":
        result = verify_log()
        if result.ok:
            print(f"decision_log ok entries={result.entries}")
            return 0
        print(f"decision_log failed entries={result.entries} error={result.error}")
        return 1
    if args.log_command == "show":
        for line in format_decision_log_entries(args.tail):
            print(line)
        return 0
    print("error      unsupported submit log command")
    return 2


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
    else:
        print(f"suite     {ref.suite_id} ok ({ref.source}, {ref.suite_hash})")
    _print_doctor_next_steps(args)
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
        _print_suite_resolution_error(error, args.suite)
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
    if value == "bounded-final-v1":
        return "bounded-final-v1"
    if value == "capped-thinking":
        return "capped-thinking"
    if value == "api-uncapped":
        return "api-uncapped"
    return "answer-only"


def _profile(value: str) -> BoundedFinalProfileChoice:
    if value == "answer_only_v1":
        return "answer_only_v1"
    if value == "generic_think_tags_8192_v1":
        return "generic_think_tags_8192_v1"
    if value == "gemma4_channel_8192_v1":
        return "gemma4_channel_8192_v1"
    return "auto"


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


def _optional_reasoning_activation(value: str | None) -> ReasoningActivationChoice | None:
    if value is None:
        return None
    return _reasoning_activation(value)


def _print_summary(record: LocalbenchRun, output_path: Path | None = None) -> None:
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
    print(_placement_line(record))
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
    if output_path is not None:
        print(f"output     {output_path}")
    for warning in record["warnings"]:
        print(f"warning    {warning}")


def _placement_line(record: Mapping[str, JsonValue]) -> str:
    axis_status = _json_object(record.get("axis_status"))
    axes = _json_object(axis_status.get("axes"))
    measured = {
        axis
        for axis in _HEADLINE_AXIS_KEYS
        if _json_object(axes.get(axis)).get("status") == "measured"
    }
    if set(_HEADLINE_AXIS_KEYS) <= measured:
        return "placement  all 5 headline axes measured; this run is eligible for the full composite."
    if set(_STATIC_AXIS_KEYS) <= measured:
        return (
            "placement  4 static headline axes measured; this run is eligible for the static "
            f"composite ({STATIC_SUITE_INDEX_VERSION}), not the full composite."
        )
    return "placement  fewer than 4 static headline axes measured; this run is reported per-axis only."


def _json_object(value: JsonValue | None) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _json_text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


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
