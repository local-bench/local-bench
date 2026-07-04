"""GPU-run funnel runner for the AppWorld-C candidate — staged campaign CLI.

This is the command the (separate, explicitly-gated) GPU run invokes per funnel stage. It:

  1. loads the real AppWorld task ids for the needed split via ``appworld.load_task_ids`` and reads
     per-task ``ground_truth/metadata.json`` (difficulty / primary app / gold api-call count) for
     stratification — both WSL-only, so this runner lives in ``cli/tools`` and is run inside the
     appworld venv;
  2. builds the FROZEN, pre-registered subset for the stage (``funnel.subset_for_stage``) and prints
     its manifest hash so it can be checked against the locked manifest;
  3. points a :class:`ChatCompletionsClient` at the local ``llama-server`` (default
     ``http://127.0.0.1:8000``) and runs the funnel stage with the LOCKED 2-rerun rule
     (``funnel.run_with_reruns``), persisting every BenchmarkReport under ``cli/runs/agentic/``;
  4. runs the early-stop check (``funnel.evaluate_early_stop``) and prints the verdict + reasons.

GPU-free modes for verification (NO model, NO server, NO GPU):
  * ``--print-subset`` — load ids + metadata, build + print the frozen subset (ids + hash) and EXIT.
    Use this to FREEZE / verify the manifest without touching the GPU.
  * ``--dry-run`` — do everything except the HTTP calls: prints the subset, the endpoint it WOULD
    hit, and the exact per-stage plan, then exits 0. (No llama-server contact.)

Only when run WITHOUT those flags (and with a llama-server actually listening) does it make model
calls — that is the gated GPU step. The agentic axis stays unregistered / weight-0; nothing here
touches the scorer/board/registry.

Examples (run inside the appworld venv; see ``docs/foundations/appworld-c-funnel-harness.md``):
  # freeze/verify the 96-task scored manifest, no GPU:
  python cli/tools/appworld_c_funnel.py --stage scored --print-subset
  # smoke stage against a live server:
  python cli/tools/appworld_c_funnel.py --stage smoke --base-url http://127.0.0.1:8000 \
      --model qwen3.5-0.8b --label qwen3.5-0.8b
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))

from localbench.scoring.agentic_exec import funnel as fn  # noqa: E402
from localbench.scoring.agentic_exec.loop_config import LoopConfig  # noqa: E402
from localbench.scoring.agentic_exec.task_pool import build_subset  # noqa: E402

_DEFAULT_RESULTS_DIR = _REPO / "cli" / "runs" / "agentic"


def _print_subset(subset: fn.SubsetSpec) -> None:
    print("=" * 100)
    print(f"FROZEN SUBSET - {subset.name}")
    print("=" * 100)
    print(f"  split           : {subset.split}")
    print(f"  size            : {subset.size}")
    print(f"  seed            : {subset.seed}")
    print(f"  selection       : {subset.selection_version}")
    print(f"  manifest_hash   : {subset.manifest_hash}")
    print(f"  task_ids        : {list(subset.task_ids)}")
    print("=" * 100)


# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    _locked = LoopConfig()  # source of the LOCKED budget defaults for the override flags below.
    ap = argparse.ArgumentParser(description="AppWorld-C staged funnel runner (GPU run).")
    ap.add_argument("--stage", required=True, choices=[s.value for s in fn.Stage])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000",
                    help="llama-server root (without /v1/...). Default http://127.0.0.1:8000.")
    ap.add_argument("--model", default="", help="served model id the endpoint expects.")
    ap.add_argument("--api-key", default="", help="optional bearer token (local server ignores).")
    ap.add_argument("--label", default="", help="row label for persisted results (default=model).")
    ap.add_argument("--timeout-s", type=float, default=120.0)
    ap.add_argument("--results-dir", default=str(_DEFAULT_RESULTS_DIR))
    ap.add_argument("--reruns", type=int, default=fn.RERUN_BASE_COUNT,
                    help=f"base rerun count for a displayed row (LOCKED default {fn.RERUN_BASE_COUNT}).")
    ap.add_argument("--max-output-tokens", type=int, default=_locked.max_output_tokens_per_turn,
                    help=f"DIAGNOSTIC override of the per-turn output token cap (LOCKED default "
                         f"{_locked.max_output_tokens_per_turn}). Raise for native-thinking models whose "
                         f"reasoning is truncated at the locked cap. Dev-split calibration ONLY; a scored "
                         f"run must use the value frozen in the AppWorld-C manifest.")
    ap.add_argument("--max-turns", type=int, default=_locked.max_turns,
                    help=f"DIAGNOSTIC override of the turn cap (LOCKED default {_locked.max_turns}). "
                         f"Dev-split calibration ONLY.")
    ap.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=True,
                    help="engage the model's NATIVE THINKING per-request via chat_template_kwargs "
                         "{enable_thinking: true} (default ON — required for thinking-lane models; "
                         "pass --no-thinking for a non-thinking model).")
    ap.add_argument("--wide-smoke", action="store_true",
                    help=f"use the {fn.SMOKE_SIZE_EXT}-task smoke instead of {fn.SMOKE_SIZE}.")
    ap.add_argument("--no-metadata", action="store_true",
                    help="skip reading metadata.json (single-stratum selection; faster).")
    ap.add_argument("--print-subset", action="store_true",
                    help="build + print the frozen subset and EXIT (no GPU, no server).")
    ap.add_argument("--dry-run", action="store_true",
                    help="print subset + the plan WITHOUT any model calls, then exit.")
    args = ap.parse_args(argv)

    stage = fn.Stage(args.stage)
    label = args.label or args.model or stage.value

    # Build the frozen subset (needs WSL appworld for ids; metadata optional).
    try:
        subset = build_subset(
            stage, wide_smoke=args.wide_smoke, with_metadata=not args.no_metadata
        )
    except Exception as exc:  # noqa: BLE001 — surface a clear message off-WSL.
        print(f"[FATAL] could not load AppWorld task ids/metadata: {type(exc).__name__}: {exc}")
        print("        (this runner must run inside the WSL appworld venv with APPWORLD_ROOT set.)")
        return 2

    _print_subset(subset)

    if args.print_subset:
        return 0

    cfg = LoopConfig(max_turns=args.max_turns, max_output_tokens_per_turn=args.max_output_tokens)
    endpoint = f"{args.base_url.rstrip('/')}/v1/chat/completions"
    print(f"  stage           : {stage.value}")
    print(f"  endpoint        : {endpoint}")
    print(f"  model           : {args.model or '<unset>'}")
    print(f"  label           : {label}")
    print(f"  reruns (base)   : {args.reruns}  (3rd added iff ASR drift > {fn.DELTA_TRIGGER_PP}pp)")
    print(f"  results_dir     : {args.results_dir}")
    print(f"  loop            : max_turns={cfg.max_turns} "
          f"max_out_tok={cfg.max_output_tokens_per_turn} temp={cfg.temperature} seed={cfg.seed}")

    if args.dry_run:
        print("\n[DRY-RUN] no model calls made; subset + plan printed above. Exiting 0.")
        return 0

    # ---- live (gated GPU) path: real model calls ----
    from localbench.scoring.agentic_exec.benchmark import (  # noqa: PLC0415 — lazy: bwrap/appworld.
        appworld_sandbox_factory,
    )

    thinking_kwargs = {"enable_thinking": True} if args.thinking else None
    print(f"  thinking        : {'ON (enable_thinking per-request)' if args.thinking else 'OFF'}")
    model_factory = fn.chat_client_factory(
        args.base_url, args.model, api_key=args.api_key, timeout_s=args.timeout_s,
        chat_template_kwargs=thinking_kwargs,
    )
    sandbox_factory = appworld_sandbox_factory()

    agg = fn.run_with_reruns(
        label=label,
        stage=stage,
        subset=subset,
        model_factory=model_factory,
        sandbox_factory=sandbox_factory,
        config=cfg,
        results_dir=Path(args.results_dir),
        base_count=args.reruns,
        endpoint=endpoint,
        model_id=args.model,
        chat_template_kwargs=thinking_kwargs,
    )

    print("\n" + "=" * 100)
    print(f"RERUN AGGREGATE — {label} / {stage.value}")
    print("=" * 100)
    print(f"  ASR series       : {[round(x, 4) for x in agg.asr_series]}")
    print(f"  mean ASR         : {agg.mean_asr:.4f}")
    print(f"  max abs delta    : {agg.max_abs_delta_pp:.2f}pp "
          f"(trigger {fn.DELTA_TRIGGER_PP}pp -> 3rd run: {agg.triggered_third_run})")
    for r in agg.runs:
        print(f"    run{r.run_index}: ASR {r.report.agentic_success_rate:.4f}  -> {r.results_path}")

    # Early-stop check on the LAST run's report (the freshest full picture).
    last_report = agg.runs[-1].report
    signal = fn.evaluate_early_stop(last_report)
    print("\n" + "-" * 100)
    print("EARLY-STOP CHECK (loop-internal conditions)")
    print(f"  should_stop      : {signal.should_stop}")
    print(f"  asr              : {signal.asr:.4f}")
    print(f"  harness_share    : {signal.harness_failure_share:.2f} (of non-success tasks)")
    for reason in signal.reasons:
        print(f"    - {reason}")
    if not signal.reasons:
        print("    (no early-stop condition met; sweep may continue)")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
