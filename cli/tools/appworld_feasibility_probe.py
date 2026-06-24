"""AppWorld agentic-axis feasibility probe (CPU-only, NON-LLM, no network).

GO/NO-GO evidence generator for `agentic_exec_appworld_lite_v0`. Proves (or disproves) that the
harness's strict one-JSON-tool-call-per-turn protocol can drive REAL AppWorld end-to-end within a
sane tool-call budget. NO model, NO GPU, NO llama-server: the "agent" is a hand-scripted,
deterministic sequence of single `apis.<app>.<api>(**args)` calls, each executed exactly the way
the built adapter intends (synthesize a one-line `print(apis...)` program -> world.execute ->
capture stdout).

What it proves:
  1. Protocol drives real AppWorld: a scripted single-JSON-call sequence solves real dev tasks
     through the synthesize->execute->capture loop; real API outputs captured per turn.
  2. evaluate() key map: dumps world.evaluate().to_dict() on a SOLVED task (success True) and an
     INCOMPLETE task (success False) so the pass/fail + collateral signal is authoritative.
  3. Budget adequacy: counts the single-JSON-calls each solved task needs and compares to the
     harness budget (max_tool_calls=11), plus reads the gold num_api_calls distribution.

Run (WSL appworld venv + APPWORLD_ROOT set):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && source ~/appworld-harness/venv/bin/activate \
    && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
    && python cli/tools/appworld_feasibility_probe.py'
"""

from __future__ import annotations

import ast
import json
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from appworld import AppWorld

ROOT = Path(os.environ["APPWORLD_ROOT"]) / "data"
BUDGET_MAX_TOOL_CALLS = 11  # from cli/.../agentic_exec/config.py
BUDGET_MAX_TURNS = 12


# ---------------------------------------------------------------------------------------------
# The harness seam, reproduced faithfully: synthesize ONE call -> world.execute -> capture stdout.
# This mirrors what AppWorldLiteAdapter.execute_tool_call() must do against real AppWorld:
#   build `print(apis.<app>.<api>(**arguments))`, run it through world.execute, parse stdout back.
# Exactly ONE apis.* call per turn (the protocol invariant). No multi-statement code.
# ---------------------------------------------------------------------------------------------
@dataclass
class TurnResult:
    turn: int
    tool: str
    arguments: dict[str, Any]
    program: str
    stdout: str
    parsed: Any
    error: str | None


@dataclass
class TaskRun:
    task_id: str
    instruction: str
    turns: list[TurnResult] = field(default_factory=list)
    tool_calls: int = 0  # single-JSON tool calls excluding the final complete_task ceremony
    eval_dict: dict[str, Any] | None = None
    success: bool | None = None


def _synthesize(tool: str, arguments: dict[str, Any]) -> str:
    """Build the exact one-line program the adapter synthesizes for one JSON tool call."""
    app, api = tool.split(".", 1)
    # Render args as a Python kwargs literal deterministically (sorted keys), like the adapter
    # passing **arguments. repr() of JSON-decoded scalars/containers is valid Python.
    kwargs = ", ".join(f"{k}={arguments[k]!r}" for k in sorted(arguments))
    return f"print(apis.{app}.{api}({kwargs}))"


def _parse_stdout(stdout: str) -> Any:
    """Parse captured stdout back to a Python/JSON value, like the adapter would."""
    s = stdout.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        return ast.literal_eval(s)
    except Exception:
        return s  # opaque string observation


def call_one(world: AppWorld, run: TaskRun, tool: str, arguments: dict[str, Any],
             *, count: bool = True) -> Any:
    """Execute exactly one JSON tool call through the synthesize->execute->capture loop."""
    program = _synthesize(tool, arguments)
    error = None
    try:
        stdout = world.execute(program)
    except Exception as exc:  # AppWorld raised -> harness would surface TOOL_ERROR
        stdout = ""
        error = f"{type(exc).__name__}: {exc}"
    parsed = _parse_stdout(stdout) if error is None else None
    run.turns.append(TurnResult(
        turn=len(run.turns) + 1, tool=tool, arguments=arguments,
        program=program, stdout=(stdout or "")[:600], parsed=parsed, error=error,
    ))
    if count:
        run.tool_calls += 1
    return parsed


# ---------------------------------------------------------------------------------------------
# Scripted gold paths for two REAL dev tasks (read off the AppWorld gold solution.py — NOT an LLM).
# Each path is a sequence of single apis.<app>.<api> calls + a final supervisor.complete_task.
# The login secret is read at runtime from the real supervisor app (no hardcoded password).
# ---------------------------------------------------------------------------------------------
def _spotify_login(world: AppWorld, run: TaskRun, email: str) -> str:
    """Auth as the real JSON-agent would: read passwords, then login. Returns access_token."""
    pwds = call_one(world, run, "supervisor.show_account_passwords", {})
    # pwds is a list of {account_name, password}; find the spotify one deterministically.
    password = None
    if isinstance(pwds, list):
        for row in pwds:
            if isinstance(row, dict) and row.get("account_name") == "spotify":
                password = row.get("password")
                break
    token_obj = call_one(world, run, "spotify.login", {"username": email, "password": password})
    if isinstance(token_obj, dict):
        return token_obj.get("access_token")
    return token_obj


def run_6bdbc26_1(world: AppWorld) -> TaskRun:
    """Read task: 'How many people follow the artist of the currently playing song?' -> 20."""
    run = TaskRun(task_id="6bdbc26_1", instruction=world.task.instruction)
    email = world.task.supervisor.email
    token = _spotify_login(world, run, email)
    current = call_one(world, run, "spotify.show_current_song", {"access_token": token})
    artist_id = None
    if isinstance(current, dict):
        artists = current.get("artists") or []
        if artists and isinstance(artists[0], dict):
            artist_id = artists[0].get("id")
    artist = call_one(world, run, "spotify.show_artist", {"artist_id": artist_id})
    answer = artist.get("follower_count") if isinstance(artist, dict) else artist
    # final_answer: the harness calls supervisor.complete_task itself (NOT counted as a tool call).
    call_one(world, run, "supervisor.complete_task",
             {"answer": answer, "status": "success"}, count=False)
    return run


def _finish_eval(world: AppWorld, run: TaskRun) -> None:
    ev = world.evaluate()
    run.eval_dict = ev.to_dict()
    run.success = bool(run.eval_dict.get("success"))


# ---------------------------------------------------------------------------------------------
# Gold num_api_calls distribution across the full dev split (the budget-vs-reality envelope).
# ---------------------------------------------------------------------------------------------
def dev_call_distribution() -> dict[str, Any]:
    dev_ids = (ROOT / "datasets" / "dev.txt").read_text().split()
    calls: list[int] = []
    per_task: list[tuple[str, int, int]] = []
    for tid in dev_ids:
        mp = ROOT / "tasks" / tid / "ground_truth" / "metadata.json"
        if mp.exists():
            m = json.loads(mp.read_text())
            calls.append(m["num_api_calls"])
            per_task.append((tid, m["num_api_calls"], m.get("difficulty")))
    cs = sorted(calls)

    def pct(p: float) -> float:
        k = (len(cs) - 1) * p
        f = int(k)
        c = min(f + 1, len(cs) - 1)
        return cs[f] + (cs[c] - cs[f]) * (k - f)

    return {
        "n": len(calls),
        "min": min(calls), "p10": pct(0.10), "median": statistics.median(calls),
        "p90": pct(0.90), "max": max(calls), "mean": round(statistics.mean(calls), 1),
        "fit_le_11": sum(1 for c in calls if c <= 11),
        "fit_le_8": sum(1 for c in calls if c <= 8),
        "smallest": sorted(per_task, key=lambda x: x[1])[:6],
    }


def main() -> None:
    print("=" * 88)
    print("APPWORLD AGENTIC-AXIS FEASIBILITY PROBE  (CPU-only, NON-LLM, no network)")
    print("=" * 88)

    # ---- POINT 3 (envelope): gold call-count distribution over the whole dev split ----
    dist = dev_call_distribution()
    print("\n### [POINT 3] Gold num_api_calls distribution over ALL dev tasks")
    print(f"  n={dist['n']}  min={dist['min']}  p10={dist['p10']:.0f}  median={dist['median']:.0f}"
          f"  p90={dist['p90']:.0f}  max={dist['max']}  mean={dist['mean']}")
    print(f"  GOLD path fits harness budget (<= {BUDGET_MAX_TOOL_CALLS} calls): "
          f"{dist['fit_le_11']}/{dist['n']} ({100*dist['fit_le_11']//dist['n']}%)   "
          f"(<= 8 calls: {dist['fit_le_8']}/{dist['n']})")
    print("  smallest dev tasks (tid, gold_calls, difficulty):")
    for tid, c, d in dist["smallest"]:
        print(f"      {tid}  calls={c}  difficulty={d}")

    # ---- POINT 1 + 2(pass side): drive a real read task to a PASS via the protocol ----
    print("\n### [POINT 1] Driving REAL dev task 6bdbc26_1 via single-JSON-call protocol")
    with AppWorld(task_id="6bdbc26_1", experiment_name="lb_feasibility_solved") as world:
        run = run_6bdbc26_1(world)
        for t in run.turns:
            mark = "ERR" if t.error else "ok "
            shown = t.error if t.error else (repr(t.parsed)[:90])
            print(f"  turn {t.turn} [{mark}] {t.program[:70]:<70} -> {shown}")
        _finish_eval(world, run)
        print(f"  >> single-JSON tool calls used (excl. complete_task): {run.tool_calls}")
        print(f"  >> evaluate().to_dict() KEYS: {list(run.eval_dict.keys())}")
        print(f"  >> SUCCESS signal (eval['success']): {run.success}")
        solved_eval = run.eval_dict
        solved_calls = run.tool_calls

    # ---- POINT 2 (fail side): same task, deliberately INCOMPLETE (never submit answer) ----
    print("\n### [POINT 2] Same task left INCOMPLETE (no complete_task) -> fail-side eval map")
    with AppWorld(task_id="6bdbc26_1", experiment_name="lb_feasibility_incomplete") as world2:
        run2 = TaskRun(task_id="6bdbc26_1", instruction=world2.task.instruction)
        # Do a couple of read calls but NEVER call complete_task.
        email = world2.task.supervisor.email
        _spotify_login(world2, run2, email)
        _finish_eval(world2, run2)
        print(f"  >> tool calls used: {run2.tool_calls} (answer intentionally NOT submitted)")
        print(f"  >> evaluate().to_dict() KEYS: {list(run2.eval_dict.keys())}")
        print(f"  >> SUCCESS signal (eval['success']): {run2.success}")
        incomplete_eval = run2.eval_dict

    # ---- Eval map: print the structure of passes/failures (the collateral signal lives here) ----
    print("\n### [POINT 2] AUTHORITATIVE evaluate() KEY MAP")
    print("  SOLVED task eval (success=%s):" % solved_eval.get("success"))
    print(json.dumps(solved_eval, indent=2, default=str)[:1400])
    print("\n  INCOMPLETE task eval (success=%s):" % incomplete_eval.get("success"))
    print(json.dumps(incomplete_eval, indent=2, default=str)[:1400])

    # ---- Verdict math for point 3 on the task we actually solved ----
    print("\n### [POINT 3] Min single-JSON-calls on the task we drove to PASS")
    print(f"  6bdbc26_1 (difficulty 1, the EASIEST tier): solved in {solved_calls} "
          f"single-JSON calls vs budget {BUDGET_MAX_TOOL_CALLS} -> "
          f"{'FITS' if solved_calls <= BUDGET_MAX_TOOL_CALLS else 'EXCEEDS'}")
    print(f"  But median dev task needs {dist['median']:.0f} gold calls "
          f"and p90 needs {dist['p90']:.0f} -> only {dist['fit_le_11']}/{dist['n']} dev tasks "
          f"can EVER fit {BUDGET_MAX_TOOL_CALLS} single-call turns.")

    print("\n" + "=" * 88)
    print("PROBE COMPLETE — see appworld-feasibility-proof.md for the GO/NO-GO verdict.")
    print("=" * 88)


if __name__ == "__main__":
    main()
