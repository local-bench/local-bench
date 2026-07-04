"""Acceptance tests for the AppWorld-C process-isolation sandbox (the two HARD gates).

These run the REAL sandbox and therefore require the WSL appworld venv + bubblewrap. On any host
where that environment is absent (e.g. Windows CI, or Linux without appworld/bwrap), they SKIP with
a clear reason rather than fail — the canonical way to run them is the WSL command in each docstring
and in ``docs/foundations/appworld-sandbox-build-results.md``.

GATE 1 (security): every one of the 55 canaries is BLOCKED when run THROUGH the sandbox
                   (baseline against raw ``world.execute()`` = 31 SUCCEEDED). Parsed count, not exit
                   code (AppWorld rebinds ``builtins.SystemExit``).
GATE 2 (utility):  a scripted NON-LLM agent solves >= 2 real dev tasks end-to-end through the
                   sandbox, reaching ``success: True``.

Run (WSL)::

    wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && export APPWORLD_ROOT=/home/michael/appworld-data \
      PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 && export PATH="$HOME/.local/bin:$PATH" \
      && ~/appworld-harness/venv/bin/python3 -m pytest cli/tests/test_appworld_sandbox_acceptance.py -v -s'
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))
sys.path.insert(0, str(_REPO / "cli" / "tools"))


def _appworld_available() -> bool:
    return importlib.util.find_spec("appworld") is not None


def _bwrap_available() -> bool:
    from localbench.scoring.agentic_exec.sandbox import resolve_bwrap

    return resolve_bwrap() is not None


_SKIP_REASON = (
    "requires the WSL appworld venv + bubblewrap (run the WSL command in the module docstring); "
    "this host lacks appworld and/or bwrap"
)

pytestmark = pytest.mark.skipif(
    not (_appworld_available() and os.environ.get("APPWORLD_ROOT") and _bwrap_available()),
    reason=_SKIP_REASON,
)


def test_gate1_all_canaries_blocked_through_sandbox() -> None:
    """GATE 1: the 55-canary suite reports SUCCEEDED=0 and ERROR=0 through the sandbox."""
    import appworld_canary_suite as base
    from localbench.scoring.agentic_exec.sandbox import AppWorldSandbox, SandboxConfig

    sec = base.load_secrets()
    try:
        base.seed_second_task_outputs()
    except Exception:  # noqa: BLE001 — L1-L3 still classify as BLOCKED if seeding can't run.
        pass

    # local copy of the harness's classify-with-inert-objgraph resolution, to keep the test
    # self-contained and independent of the tool module's main().
    import appworld_canary_suite_sandboxed as sandboxed

    canaries = base.build_canaries(sec)
    results: list[base.Result] = []
    with AppWorldSandbox(base.PRIMARY_TASK, SandboxConfig(experiment_name="lb_pytest_canary")) as sb:
        for can in canaries:
            obs = sb.run_block(can.code)
            out = obs.stdout
            if obs.error:
                out = (out + "\nTraceback (most recent call last)\n" + obs.error).strip()
            results.append(sandboxed._classify_sandboxed(out, can, sec))

    succeeded = [r for r in results if r.verdict == "SUCCEEDED"]
    errors = [r for r in results if r.verdict == "ERROR"]
    blocked = [r for r in results if r.verdict == "BLOCKED"]

    assert len(results) == 55
    assert not succeeded, f"canaries still SUCCEEDED (must be 0): {[r.cid for r in succeeded]}"
    assert not errors, f"canaries ambiguous/ERROR (must be 0): {[(r.cid, r.proof) for r in errors]}"
    assert len(blocked) == 55


def test_gate2_scripted_agent_solves_two_dev_tasks_through_sandbox() -> None:
    """GATE 2: a scripted NON-LLM agent reaches success: True on >= 2 real dev tasks."""
    import appworld_scripted_solve_sandboxed as solver
    from localbench.scoring.agentic_exec.sandbox import AppWorldSandbox, SandboxConfig

    verdicts = {}
    for task_id, solve in (("fac291d_1", solver.solve_fac291d), ("50e1ac9_1", solver.solve_50e1ac9)):
        with AppWorldSandbox(task_id, SandboxConfig(experiment_name=f"lb_pytest_{task_id}")) as sb:
            _answer, verdict = solve(sb)
        verdicts[task_id] = verdict

    for task_id, verdict in verdicts.items():
        assert verdict.success is True, (
            f"{task_id} did not reach success: failures={verdict.failures}"
        )
        assert verdict.collateral_damage is False, f"{task_id} caused collateral damage"

    n_ok = sum(1 for v in verdicts.values() if v.success)
    assert n_ok >= 2
