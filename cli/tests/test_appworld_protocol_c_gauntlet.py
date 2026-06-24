"""Phase-2 VALIDATION GAUNTLET for the AppWorld-C Protocol C loop (oracle launch plan).

These are the gates that must pass BEFORE any scored GPU run. They are GPU-free and model-free:
the only "agent" is the deterministic ``ScriptedSolverAgent`` and the canary payloads. They build
on the already-proven loop (``test_appworld_protocol_c_acceptance.py`` = scripted agent solves 2/2
dev tasks through the real sandbox) and the sandbox security gates
(``test_appworld_sandbox_acceptance.py`` = 55 canaries blocked via ``run_block``).

What this file ADDS (the remaining gauntlet gates):

  GATE 1  — 55-canary THROUGH the FULL LOOP. The existing canary gate drives ``run_block``
            directly; this drives every canary as a model-emitted block through the loop's
            ``parse_turn -> run_block`` path and asserts SUCCEEDED=0 / ERROR=0 (no NEW escape from
            the parse step). Plus the HARNESS-BLOCK AUDIT (model-free) — the two blocks the loop
            injects (bootstrap instruction-fetch + finalize answer-read-back) are harness-
            controlled and cannot exfiltrate.
  GATE 2  — TRACE-REPLAY EXACTNESS. Record a scripted task's emitted code blocks; replay the exact
            blocks through a FRESH sandbox (same task = same frozen data tree) and confirm the SAME
            success bool + verdict. Validates harness reproducibility (recorded trace -> same
            verdict).
  GATE 3  — ENV VALIDATION UNDER PINNED HASH. Re-confirm AppWorld's own gold solutions evaluate as
            success under pinned ``appworld==0.1.3.post1`` + the captured data-tree hash.
  GATE 4  — ROLLBACK (added separately in this file once the save_state/load_state assessment is
            complete; see ``test_gate4_*``).

GATE 1's harness-block AUDIT and the host-agnostic helper assertions also live as pure units in
``test_appworld_protocol_c_units.py`` so they run in CI without WSL. The gates here that touch the
real sandbox SKIP cleanly off-WSL.

Run (WSL):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && export APPWORLD_ROOT=/home/michael/appworld-data \
    PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 && export PATH="$HOME/.local/bin:$PATH" \
    && ~/appworld-harness/venv/bin/python3 -m pytest cli/tests/test_appworld_protocol_c_gauntlet.py -v -s'
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

_needs_sandbox = pytest.mark.skipif(
    not (_appworld_available() and os.environ.get("APPWORLD_ROOT") and _bwrap_available()),
    reason=_SKIP_REASON,
)

# Pinned AppWorld build the whole gauntlet is validated against (gate 3 asserts this).
_PINNED_APPWORLD_VERSION = "0.1.3.post1"
_TASKS = ["fac291d_1", "50e1ac9_1"]


# ==================================================================================================
# GATE 1 — harness-block audit (PURE: runs everywhere, no sandbox)
# ==================================================================================================
def test_gate1_harness_block_audit_passes() -> None:
    """The two harness-injected blocks are harness-controlled and cannot exfiltrate (model-free)."""
    import appworld_canary_through_loop as ctl

    ok, findings = ctl.audit_harness_blocks()
    assert ok, "harness-block audit FAILED:\n" + "\n".join(findings)
    # Spot-check the load-bearing findings are present (not just an empty pass).
    joined = "\n".join(findings)
    assert "read-back block is a module constant" in joined
    assert "bootstrap block is a static literal" in joined
    assert "every sandbox.run_block call passes a constant or parse_turn's parsed.code" in joined
    assert "env-host forbids the model calling" in joined


def test_gate1_run_block_callsites_are_constants_or_parsed_code() -> None:
    """Independent of the audit aggregate: enumerate run_block call args and pin them exactly."""
    import appworld_canary_through_loop as ctl
    from localbench.scoring.agentic_exec import protocol_c_loop as loop

    src = Path(loop.__file__).read_text(encoding="utf-8")
    args = ctl._run_block_call_args(src)
    # Exactly the bootstrap local const (`code`), the read-back module const, and the model block.
    assert set(args) == {"code", "_READBACK_CODE", "parsed.code"}, args
    # parse_turn's output is the ONLY model-derived argument, and it is run verbatim (no f-string).
    assert "parsed.code" in args


# ==================================================================================================
# GATE 1 — 55 canaries through the FULL LOOP (parse_turn -> run_block). WSL only.
# ==================================================================================================
@_needs_sandbox
def test_gate1_all_canaries_blocked_through_the_full_loop() -> None:
    """Every canary, driven as a model block through parse_turn -> run_block, is BLOCKED.

    This is STRICTLY the loop path (not raw run_block): each canary's code is wrapped as a fenced
    python turn, parsed by the loop's ``parse_turn``, and only the extracted block is executed —
    exactly as ``run_task`` handles a model turn. Gate: SUCCEEDED=0, ERROR=0, total=55.
    """
    import appworld_canary_suite as base
    import appworld_canary_suite_sandboxed as sandboxed
    import appworld_canary_through_loop as ctl
    from localbench.scoring.agentic_exec.sandbox import AppWorldSandbox, SandboxConfig

    sec = base.load_secrets()
    try:
        base.seed_second_task_outputs()
    except Exception:  # noqa: BLE001 — L1-L3 still classify BLOCKED if seeding can't run.
        pass

    canaries = base.build_canaries(sec)
    results: list[base.Result] = []
    parser_rejected: list[str] = []
    with AppWorldSandbox(base.PRIMARY_TASK, SandboxConfig(experiment_name="lb_pytest_loop_canary")) as sb:
        for can in canaries:
            # Confirm we are exercising the loop's parse step (informational record).
            from localbench.scoring.agentic_exec.block_parser import BlockFormatError, parse_turn
            if isinstance(parse_turn(ctl._as_model_block(can.code)), BlockFormatError):
                parser_rejected.append(can.cid)
            out = ctl._drive_through_loop_parse(sb, can.code)
            results.append(sandboxed._classify_sandboxed(out, can, sec))

    succeeded = [r for r in results if r.verdict == "SUCCEEDED"]
    errors = [r for r in results if r.verdict == "ERROR"]
    blocked = [r for r in results if r.verdict == "BLOCKED"]

    assert len(results) == 55
    assert not succeeded, (
        "canaries SUCCEEDED through the LOOP path (must be 0): "
        + str([(r.cid, r.severity, r.proof) for r in succeeded])
    )
    assert not errors, f"canaries ambiguous/ERROR through the loop (must be 0): " \
                       f"{[(r.cid, r.proof) for r in errors]}"
    assert len(blocked) == 55


# ==================================================================================================
# GATE 2 — trace-replay exactness. WSL only.
# ==================================================================================================
@_needs_sandbox
@pytest.mark.parametrize("task_id", _TASKS)
def test_gate2_trace_replay_is_exact(task_id: str) -> None:
    """Record a scripted task's emitted blocks, replay them through a fresh sandbox -> same verdict.

    RECORD pass: run the loop with ``ScriptedSolverAgent`` over the real sandbox and capture, in
    order, the exact code blocks the loop executed (via parse_turn) plus the final ``answer`` it
    finalized with.
    REPLAY pass: open a FRESH sandbox for the SAME task (same frozen data tree -> same DB), run
    the captured blocks verbatim through ``run_block`` in order, finalize with the captured answer,
    and assert the success bool + verdict match the recording. This proves the harness is
    reproducible: a recorded trace re-evaluates to the same verdict.
    """
    from localbench.scoring.agentic_exec.protocol_c_loop import run_task
    from localbench.scoring.agentic_exec.sandbox import AppWorldSandbox, SandboxConfig
    from localbench.scoring.agentic_exec.scripted_agent import ScriptedSolverAgent

    # ---- RECORD: wrap a real sandbox to capture the exact executed blocks + finalize answer. ----
    class _RecordingSandbox:
        """Transparent proxy over a live ``AppWorldSandbox`` that records executed blocks/answer.

        Records ONLY the blocks the loop actually executes (the bootstrap + read-back harness
        blocks pass through too, but we tag which is which by content so replay can reproduce the
        model-visible block sequence exactly — and we capture the finalize answer the harness read
        back from the model's ``answer`` variable).
        """

        def __init__(self, inner: AppWorldSandbox) -> None:
            self._inner = inner
            self.executed_blocks: list[str] = []
            self.finalize_answer: object = None

        def run_block(self, code: str):
            self.executed_blocks.append(code)
            return self._inner.run_block(code)

        def finalize(self, answer: object):
            self.finalize_answer = answer
            return self._inner.finalize(answer)

    cfg = SandboxConfig(experiment_name=f"lb_pytest_trace_rec_{task_id}")
    with AppWorldSandbox(task_id, cfg) as inner:
        rec = _RecordingSandbox(inner)
        rec_result = run_task(rec, ScriptedSolverAgent(task_id), task_id)

    assert rec_result.success is True, (
        f"record pass did not solve {task_id}: outcome={rec_result.outcome.value} "
        f"finalize_error={rec_result.diagnostics.finalize_error}"
    )
    recorded_blocks = list(rec.executed_blocks)
    recorded_answer = rec.finalize_answer
    assert recorded_blocks, "no blocks were recorded"
    assert recorded_answer is not None, "no finalize answer was recorded"

    # ---- REPLAY: a FRESH sandbox (same task => same frozen data), exact blocks, same answer. ----
    # We replay the model-visible blocks: drop the trailing harness read-back block (the loop's
    # _READBACK_CODE), then call finalize ourselves with the recorded answer — i.e. reproduce the
    # exact trusted-side sequence the loop produced, deterministically and without the model.
    from localbench.scoring.agentic_exec.protocol_c_loop import _READBACK_CODE, _bootstrap_task_context

    replay_blocks = [b for b in recorded_blocks if b != _READBACK_CODE]
    cfg2 = SandboxConfig(experiment_name=f"lb_pytest_trace_rep_{task_id}")
    with AppWorldSandbox(task_id, cfg2) as sb2:
        # Reproduce the bootstrap (harness-owned, same as the loop) so the world is in the same
        # post-bootstrap state, then run the recorded model blocks verbatim.
        _bootstrap_task_context(sb2)
        for code in replay_blocks:
            # The bootstrap block was already issued above; skip its duplicate if present in the
            # recorded sequence (the loop issues it once before the model turns).
            if "__LB_CTX__" in code:
                continue
            obs = sb2.run_block(code)
            # A replayed model block must not error (it succeeded during record on identical data).
            assert obs.error is None, f"replay block raised on {task_id}: {obs.error}\ncode:\n{code}"
        replay_verdict = sb2.finalize(recorded_answer)

    # ---- EXACTNESS: same success bool + same verdict shape on the frozen data. ----
    assert replay_verdict.success == rec_result.success == True, (  # noqa: E712 — explicit bool gate
        f"trace replay verdict.success={replay_verdict.success} != recorded "
        f"success={rec_result.success} for {task_id}; failures={replay_verdict.failures}"
    )
    assert replay_verdict.collateral_damage == rec_result.collateral_damage
    # The verdict's PASS set is the harness's reproducible signal: same answer + same data => same
    # passes/failures. (We compare the boolean + collateral; the pass/fail lists are AppWorld's and
    # are deterministic for a fixed answer on a fixed task.)


# ==================================================================================================
# GATE 3 — env validation under the pinned appworld build + data-tree hash. WSL only.
# ==================================================================================================
@_needs_sandbox
def test_gate3_pinned_appworld_version() -> None:
    """The installed AppWorld is the pinned build the whole axis is validated against."""
    import appworld

    version = getattr(appworld, "__version__", None)
    if version is None:
        import importlib.metadata as md
        version = md.version("appworld")
    assert version == _PINNED_APPWORLD_VERSION, (
        f"appworld=={version} but the gauntlet is pinned to {_PINNED_APPWORLD_VERSION}; "
        "re-pin the env or re-validate the gates against the new build."
    )


@_needs_sandbox
@pytest.mark.parametrize("task_id", _TASKS)
def test_gate3_gold_solution_evaluates_success_under_pinned_env(task_id: str) -> None:
    """AppWorld's OWN gold solution for a dev task evaluates as success under the pinned build.

    This validates the EVALUATION SEAM independently of our loop: load the task, execute its
    ground-truth solution program in AppWorld's own session, complete + evaluate, and assert
    ``success`` is True. If AppWorld's gold no longer passes its own evaluator, the env/data is
    broken and no loop result on it would be trustworthy. Uses ONLY the trusted env-host-side
    world (no jail needed — this is an env-integrity check, not a security check).
    """
    import appworld_gold_eval as gold_eval

    verdict = gold_eval.evaluate_gold_solution(task_id)
    assert verdict.found_solution, (
        f"no gold solution found for {task_id} at {verdict.solution_path!r}; "
        "cannot validate the evaluation seam"
    )
    assert verdict.success is True, (
        f"AppWorld's OWN gold solution for {task_id} did NOT evaluate as success under "
        f"appworld=={_PINNED_APPWORLD_VERSION}: failures={verdict.failures}"
    )


@_needs_sandbox
def test_gate3_data_tree_hash_is_stable_and_reported() -> None:
    """Capture + report the frozen data-tree hash (the 'same frozen data' anchor for gates 2/3).

    The hash makes 'same frozen data' concrete: gate 2's record/replay and gate 3's gold eval are
    only meaningful on a fixed data tree. This computes a stable digest over the task DB + ground
    truth inputs and asserts it is non-empty + reproducible within the run (two calls agree).
    """
    import appworld_gold_eval as gold_eval

    h1 = gold_eval.data_tree_hash(_TASKS)
    h2 = gold_eval.data_tree_hash(_TASKS)
    assert h1 and isinstance(h1, str) and len(h1) == 64, f"bad data-tree hash: {h1!r}"
    assert h1 == h2, "data-tree hash is not reproducible within the run"
    print(f"\n[gate3] frozen data-tree hash ({'+'.join(_TASKS)}): {h1}")


# ==================================================================================================
# GATE 4 — rollback ASSESSMENT: the partial-mutation edge + the (unwired) rollback primitive.
#
# DECISION (documented, NOT implemented): a block timed out by the per-block wall-clock cap is
# killed by SIGTERM/SIGKILL of the RUNNER from OUTSIDE; that does not interrupt an in-flight
# ``world.execute`` on the trusted env-host, and a block routinely makes MANY ``apis.*`` calls (each
# a separate committing RPC). So calls #1..k of a killed block are already committed on the env-host
# and not rolled back -> can register as ``collateral_damage`` on the final eval. AppWorld's
# ``save_state``/``load_state`` CAN revert such a mutation (proven below), but wiring
# rollback-on-timeout to be USEFUL needs continue-after-timeout (keep the env-host alive past a
# runner timeout AND re-spawn the killed runner to continue the task) — a sandbox-lifecycle change
# that is NOT low-risk. Today a timed-out block aborts the whole task, so there is nothing to
# continue into and rollback buys nothing. Hence: DOCUMENT the edge as a known limitation; keep the
# proven-safe primitive available for a future continue-after-timeout build behind a trusted RPC.
#
# These tests (a) PROVE the edge is real, (b) PROVE the rollback primitive is sound (so the
# limitation is backed by "the fix exists but isn't wired"), and (c) lock the security invariant
# that the model can NEVER drive save/load — which must hold whether or not rollback is ever wired.
# ==================================================================================================
def test_gate4_model_cannot_drive_state_ops() -> None:
    """SECURITY INVARIANT (pure): env-host forbids the model calling save_state/load_state/close_all.

    Rollback, if ever wired, must be harness-only. This holds today and must keep holding: the
    untrusted runner can never check/rollback state. Runs anywhere (no sandbox needed).
    """
    from localbench.scoring.agentic_exec import env_host

    for name in ("save_state", "load_state", "close_all", "close", "complete_task", "evaluate"):
        assert name in env_host._FORBIDDEN_API_NAMES, (
            f"{name} must be forbidden to untrusted model code (harness-only)"
        )


@_needs_sandbox
def test_gate4_partial_mutation_edge_is_real() -> None:
    """The edge a timed-out block exposes: a mutation COMMITS without finalize (not rolled back).

    Applies a mutation via ``world.execute`` (exactly how a real ``call_api`` RPC commits) and never
    finalizes — the analogue of "the runner was killed after committing calls #1..k of the block".
    Asserts the mutation is committed + visible, i.e. it WOULD count against the final eval. This is
    the known limitation, made concrete.
    """
    import appworld_rollback_probe as probe

    edge = probe.demonstrate_partial_mutation_edge("50e1ac9_1")
    assert edge.count_after_mutation == edge.count_before + 1, (
        f"expected the mutation to commit (before={edge.count_before}, "
        f"after={edge.count_after_mutation})"
    )
    assert edge.mutation_committed is True, (
        "a mutation applied without finalize was NOT committed/visible — the partial-mutation "
        "edge characterisation is wrong; re-examine before relying on the known-limitation note"
    )


@_needs_sandbox
def test_gate4_rollback_primitive_is_sound() -> None:
    """The (unwired) rollback primitive works: save_state -> mutate -> load_state REVERTS it.

    Proves that IF a future continue-after-timeout build adopts ``save_state``/``load_state`` (behind
    a trusted RPC), the rollback semantics are correct: the mutation is undone AND ``apis.*`` still
    works after ``load_state``. This is what makes the 'documented, not implemented' decision safe —
    the limitation is curable; it is just not low-risk to wire today.
    """
    import appworld_rollback_probe as probe

    rb = probe.demonstrate_rollback_primitive("50e1ac9_1")
    assert rb.count_after_mutation == rb.count_before + 1, "mutation did not take before rollback"
    assert rb.apis_work_after_rollback is True, "apis.* broke after load_state (rollback unsafe)"
    assert rb.count_after_rollback == rb.count_before, (
        f"load_state did not revert the count ({rb.count_before} -> {rb.count_after_mutation} -> "
        f"{rb.count_after_rollback})"
    )
    assert rb.created_note_exists_after_rollback is False, "the mutated row survived rollback"
    assert rb.reverted is True
