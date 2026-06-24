"""Run the Protocol C agent LOOP with the SCRIPTED (non-LLM) agent through the REAL sandbox.

This is the end-to-end proof that the Protocol C loop turns the AppWorldSandbox into a runnable
benchmark — GPU-free and model-free. It drives the loop exactly as the GPU benchmark will, but
swaps the real chat-completions client for the deterministic ``ScriptedSolverAgent``:

    run_appworld_c_benchmark(
        task_ids=[fac291d_1, 50e1ac9_1],
        model_factory=ScriptedSolverAgent,            # <- real benchmark swaps in a chat client
        sandbox_factory=appworld_sandbox_factory(),   # <- live AppWorldSandbox per task
    )

It prints, per task: the verdict (success/collateral) and the full diagnostics (turns, blocks,
format/syntax/runtime failures, api-call count, observation truncations, api_docs usage), then the
aggregate ASR + diagnostic rates. Exit 0 iff >= 2 tasks reach success: True.

Run (WSL appworld venv + bwrap):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && export APPWORLD_ROOT=/home/michael/appworld-data \
    PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 && export PATH="$HOME/.local/bin:$PATH" \
    && ~/appworld-harness/venv/bin/python3 cli/tools/appworld_protocol_c_scripted.py --json'
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))

from localbench.scoring.agentic_exec.benchmark import (  # noqa: E402
    appworld_sandbox_factory,
    run_appworld_c_benchmark,
)
from localbench.scoring.agentic_exec.loop_config import LoopConfig  # noqa: E402
from localbench.scoring.agentic_exec.sandbox import resolve_bwrap  # noqa: E402
from localbench.scoring.agentic_exec.scripted_agent import ScriptedSolverAgent  # noqa: E402

_TASKS = ["fac291d_1", "50e1ac9_1"]


def main(emit_json: bool) -> int:
    print("=" * 100)
    print("PROTOCOL C LOOP — SCRIPTED (NON-LLM) AGENT THROUGH THE REAL SANDBOX")
    print("=" * 100)
    if not resolve_bwrap():
        print("[FATAL] bwrap not found; cannot run the real sandbox.")
        return 2
    print(f"APPWORLD_ROOT : {os.environ.get('APPWORLD_ROOT', '<unset>')}")
    print(f"tasks         : {_TASKS}")
    print(f"loop config   : max_turns={LoopConfig().max_turns} "
          f"max_output_tokens_per_turn={LoopConfig().max_output_tokens_per_turn} "
          f"max_observation_chars={LoopConfig().max_observation_chars}\n")

    report = run_appworld_c_benchmark(
        task_ids=_TASKS,
        model_factory=ScriptedSolverAgent,
        sandbox_factory=appworld_sandbox_factory(),
        config=LoopConfig(),
    )

    for r in report.results:
        d = r.diagnostics
        print(f"--- {r.task_id} ---")
        print(f"    success={r.success}  outcome={r.outcome.value}  collateral={r.collateral_damage}")
        print(f"    turns_used={d.turns_used}  blocks_run={d.blocks_run}  "
              f"total_api_calls={d.total_api_calls}  api_docs_uses={d.api_docs_uses}")
        print(f"    format_failures={d.format_failures}  syntax_errors={d.syntax_errors}  "
              f"runtime_errors={d.runtime_errors}  obs_truncations={d.observation_truncations}")
        print(f"    cap_exceeded={d.cap_exceeded}  total_output_tokens={d.total_output_tokens}")
        if d.finalize_error:
            print(f"    finalize_error={d.finalize_error}")

    print("\n" + "=" * 100)
    print("AGGREGATE")
    print(f"  ASR (agentic_success_rate)   : {report.agentic_success_rate:.3f} "
          f"({report.tasks_succeeded}/{report.tasks_total})")
    print(f"  collateral_damage_rate       : {report.collateral_damage_rate:.3f}")
    print(f"  cap_exceeded_rate            : {report.cap_exceeded_rate:.3f}")
    print(f"  no_final_answer_rate         : {report.no_final_answer_rate:.3f}")
    print(f"  harness_error_rate           : {report.harness_error_rate:.3f}")
    print(f"  format_failure_rate (/turn)  : {report.format_failure_rate:.3f}")
    print(f"  syntax_error_rate (/block)   : {report.syntax_error_rate:.3f}")
    print(f"  runtime_error_rate (/block)  : {report.runtime_error_rate:.3f}")
    print(f"  obs_truncation_rate (/block) : {report.observation_truncation_rate:.3f}")
    print(f"  api_docs_usage_rate (/task)  : {report.api_docs_usage_rate:.3f}")
    print(f"  mean_turns_used              : {report.mean_turns_used:.2f}")
    print(f"  mean_blocks_run              : {report.mean_blocks_run:.2f}")
    print(f"  mean_api_calls               : {report.mean_api_calls:.2f}")
    print(f"  mean_output_tokens           : {report.mean_output_tokens:.1f}")
    print(f"  outcome_counts               : {report.outcome_counts}")
    print("=" * 100)

    n_ok = report.tasks_succeeded
    print(f"\nRESULT: {n_ok}/{report.tasks_total} tasks reached success: True through the "
          f"Protocol C loop (gate requires >= 2)")
    if emit_json:
        print("\n--- JSON ---")
        print(json.dumps(report.as_dict(), indent=2))
    return 0 if n_ok >= 2 else 1


if __name__ == "__main__":
    _rc = main(emit_json=("--json" in sys.argv))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)
