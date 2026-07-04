"""Acceptance test: the Protocol C LOOP drives the scripted agent through the REAL sandbox.

Complements the host-agnostic loop units (``test_appworld_protocol_c_units.py``, which use a
FakeSandbox) and the sandbox gates (``test_appworld_sandbox_acceptance.py``). This runs the
ACTUAL ``AppWorldSandbox`` (bwrap + appworld) under the Protocol C loop with the deterministic
``ScriptedSolverAgent`` — i.e. the exact path the GPU benchmark will take, minus the model.

GATE: the scripted agent, driven by ``run_task`` over the real sandbox, reaches ``success: True``
on >= 2 real dev tasks AND the diagnostics are populated (blocks_run > 0, no harness error).

Skips cleanly where appworld/bwrap/APPWORLD_ROOT are absent (e.g. Windows). Run under WSL:

    wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && export APPWORLD_ROOT=/home/michael/appworld-data \
      PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 && export PATH="$HOME/.local/bin:$PATH" \
      && ~/appworld-harness/venv/bin/python3 -m pytest cli/tests/test_appworld_protocol_c_acceptance.py -v -s'
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))


def _appworld_available() -> bool:
    return importlib.util.find_spec("appworld") is not None


def _bwrap_available() -> bool:
    from localbench.scoring.agentic_exec.sandbox import resolve_bwrap

    return resolve_bwrap() is not None


pytestmark = pytest.mark.skipif(
    not (_appworld_available() and os.environ.get("APPWORLD_ROOT") and _bwrap_available()),
    reason=(
        "requires the WSL appworld venv + bubblewrap (run the WSL command in the module "
        "docstring); this host lacks appworld and/or bwrap"
    ),
)

_TASKS = ["fac291d_1", "50e1ac9_1"]


def test_protocol_c_scripted_agent_solves_two_dev_tasks_through_real_sandbox() -> None:
    """The Protocol C loop + scripted agent reach success: True on >= 2 dev tasks, with diagnostics."""
    from localbench.scoring.agentic_exec.benchmark import (
        appworld_sandbox_factory,
        run_appworld_c_benchmark,
    )
    from localbench.scoring.agentic_exec.loop_config import LoopConfig
    from localbench.scoring.agentic_exec.loop_types import TaskOutcome
    from localbench.scoring.agentic_exec.scripted_agent import ScriptedSolverAgent

    report = run_appworld_c_benchmark(
        task_ids=_TASKS,
        model_factory=ScriptedSolverAgent,
        sandbox_factory=appworld_sandbox_factory(),
        config=LoopConfig(),
    )

    assert report.tasks_total == 2
    assert report.tasks_succeeded >= 2, (
        "scripted agent did not solve both tasks through the loop: "
        + str([(r.task_id, r.outcome.value, r.diagnostics.finalize_error) for r in report.results])
    )
    for r in report.results:
        assert r.success is True, f"{r.task_id} outcome={r.outcome.value}"
        assert r.outcome == TaskOutcome.SUCCESS
        assert r.collateral_damage is False
        # diagnostics must actually be recorded (the loop ran real blocks).
        assert r.diagnostics.blocks_run > 0
        assert r.diagnostics.total_api_calls > 0
        assert r.diagnostics.finalize_error is None
    # harness-level health: no cap-exceeded, no harness errors on these known-solvable tasks.
    assert report.cap_exceeded_rate == 0.0
    assert report.harness_error_rate == 0.0
