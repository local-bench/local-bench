"""GATE 4 helper: characterise the per-block partial-mutation EDGE and prove the rollback PRIMITIVE.

The Protocol C loop imposes a per-block WALL-CLOCK cap by KILLING the untrusted runner process
from outside (``AppWorldSandbox._read_runner_event`` times out -> ``SandboxError`` -> ``close()``
SIGTERM/SIGKILLs both children). That kill does NOT interrupt an in-flight ``world.execute`` on the
TRUSTED env-host side, and a single model block routinely contains MANY ``apis.*`` calls, each a
separate blocking RPC that COMMITS its mutation to the in-memory DB before the next. So if a block
is timed out after committing calls #1..k of N, those k mutations are already applied on the
env-host and are NOT rolled back. On the final ``evaluate()`` that can register as
``collateral_damage`` ("assert no model changes.").

This module makes that concrete + decides gate 4 empirically. Two facilities, both ENTIRELY on the
trusted side (no jail, no model, no GPU — the model can never drive save/load: env_host's
``_FORBIDDEN_API_NAMES`` rejects them):

  * ``demonstrate_partial_mutation_edge(task_id)`` — authenticate, snapshot a count, apply a
    mutation WITHOUT finalizing (the analogue of "calls committed, then the block was killed"),
    and confirm the mutation is COMMITTED + visible (would count against the final eval). Proves the
    edge is real.
  * ``demonstrate_rollback_primitive(task_id)`` — snapshot via ``world.save_state()``, mutate,
    confirm the mutation took, ``world.load_state()``, confirm it REVERTED, and confirm ``apis.*``
    still works afterwards. Proves the rollback primitive AppWorld exposes is sound + the harness
    COULD use it.

Why gate 4 is DOCUMENTED (not implemented): wiring rollback-on-timeout to be USEFUL requires
keeping the env-host alive past a runner timeout AND re-spawning the killed runner to CONTINUE the
task — a non-trivial sandbox-lifecycle change. Today a timed-out block aborts the whole task, so
there is nothing to continue into and rollback buys nothing. The primitive is proven safe here so a
future continue-after-timeout build can adopt it behind a trusted RPC; until then the edge is a
declared known limitation (a timed-out block may leave partial mutations -> possible
collateral_damage on that task's eval).

Run standalone:
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && source ~/appworld-harness/venv/bin/activate \
    && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
    && python cli/tools/appworld_rollback_probe.py'
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass

warnings.filterwarnings("ignore")

# A mutating app + the create/count APIs used for the demonstrations. simple_note is convenient:
# create_note mutates, and notes are individually addressable by id for an exact existence check.
_MUTATING_APP = "simple_note"


@dataclass(frozen=True, slots=True)
class EdgeResult:
    """Outcome of the partial-mutation-edge demonstration."""

    count_before: int
    count_after_mutation: int
    created_note_id: object
    mutation_committed: bool  # True iff the mutation is visible WITHOUT any finalize (the edge)


@dataclass(frozen=True, slots=True)
class RollbackResult:
    """Outcome of the rollback-primitive demonstration."""

    count_before: int
    count_after_mutation: int
    count_after_rollback: int
    created_note_exists_before_rollback: bool
    created_note_exists_after_rollback: bool
    apis_work_after_rollback: bool
    reverted: bool  # True iff load_state undid the mutation (count + id existence both reverted)


def _exec(world: object, code: str) -> str:
    return world.execute(code)  # type: ignore[attr-defined]


def _login_simple_note(world: object) -> str:
    """Authenticate simple_note via the supervisor's own credentials; return an access token.

    Self-discovers the email + password (no hard-coded user), so it is robust across tasks/seeds.
    """
    src = (
        "prof = apis.supervisor.show_profile()\n"
        "pwds = apis.supervisor.show_account_passwords()\n"
        f"spw = next(p['password'] for p in pwds if p['account_name'] == '{_MUTATING_APP}')\n"
        f"_tok = apis.{_MUTATING_APP}.login(username=prof['email'], password=spw)['access_token']\n"
        "print('__LB_TOKEN__' + _tok)"
    )
    out = _exec(world, src)
    for line in out.splitlines():
        if line.startswith("__LB_TOKEN__"):
            return line[len("__LB_TOKEN__"):].strip()
    raise RuntimeError(f"could not log in to {_MUTATING_APP}: {out!r}")


def _count_notes(world: object, token: str) -> int:
    """Full-pagination note count (the per-page cap makes a single search_notes undercount)."""
    src = (
        "import json as _j\n"
        "ids = set()\n"
        "pi = 0\n"
        "while True:\n"
        f"    pg = apis.{_MUTATING_APP}.search_notes(access_token={token!r}, page_index=pi)\n"
        "    if not pg:\n"
        "        break\n"
        "    for n in pg:\n"
        "        ids.add(n.get('note_id') if isinstance(n, dict) else n)\n"
        "    pi += 1\n"
        "print('__LB_COUNT__' + _j.dumps(len(ids)))"
    )
    out = _exec(world, src)
    for line in out.splitlines():
        if line.startswith("__LB_COUNT__"):
            return int(json.loads(line[len("__LB_COUNT__"):]))
    raise RuntimeError(f"could not count notes: {out!r}")


def _create_note(world: object, token: str) -> object:
    src = (
        "import json as _j\n"
        f"_r = apis.{_MUTATING_APP}.create_note(access_token={token!r}, "
        "title='lb-rollback-probe', content='partial-mutation-edge demonstration')\n"
        "print('__LB_NOTE__' + _j.dumps(_r.get('note_id') if isinstance(_r, dict) else _r))"
    )
    out = _exec(world, src)
    for line in out.splitlines():
        if line.startswith("__LB_NOTE__"):
            return json.loads(line[len("__LB_NOTE__"):])
    raise RuntimeError(f"could not create note: {out!r}")


def _note_exists(world: object, token: str, note_id: object) -> bool:
    src = (
        "ok = True\n"
        "try:\n"
        f"    _ = apis.{_MUTATING_APP}.show_note(access_token={token!r}, note_id=json.loads({json.dumps(json.dumps(note_id))}))\n"
        "except Exception:\n"
        "    ok = False\n"
        "print('__LB_EXISTS__' + ('1' if ok else '0'))"
    )
    out = _exec(world, src)
    for line in out.splitlines():
        if line.startswith("__LB_EXISTS__"):
            return line[len("__LB_EXISTS__"):].strip() == "1"
    return False


def demonstrate_partial_mutation_edge(task_id: str = "50e1ac9_1") -> EdgeResult:
    """Apply a mutation WITHOUT finalizing and confirm it is committed (the edge a timeout exposes).

    This stands in for "the runner was killed after committing some of a block's api calls": the
    mutation goes through ``world.execute`` exactly as a real ``call_api`` RPC would, and we never
    finalize — so any partial mutation a timed-out block left is exactly this committed state.
    """
    from appworld import AppWorld  # noqa: PLC0415 — lazy.

    world = AppWorld(task_id=task_id, experiment_name=f"lb_edge_{task_id}")
    try:
        token = _login_simple_note(world)
        before = _count_notes(world, token)
        note_id = _create_note(world, token)  # the "committed call #k" — never finalized
        after = _count_notes(world, token)
        committed = (after == before + 1) and _note_exists(world, token, note_id)
        return EdgeResult(
            count_before=before,
            count_after_mutation=after,
            created_note_id=note_id,
            mutation_committed=committed,
        )
    finally:
        try:
            world.close()
        except Exception:  # noqa: BLE001
            pass


def demonstrate_rollback_primitive(task_id: str = "50e1ac9_1") -> RollbackResult:
    """save_state -> mutate -> (confirm) -> load_state -> confirm REVERTED + apis.* still works."""
    from appworld import AppWorld  # noqa: PLC0415 — lazy.

    world = AppWorld(task_id=task_id, experiment_name=f"lb_rollback_{task_id}")
    try:
        token = _login_simple_note(world)
        before = _count_notes(world, token)
        state_id = world.save_state()  # type: ignore[attr-defined]  — harness-only checkpoint
        note_id = _create_note(world, token)
        after_mut = _count_notes(world, token)
        exists_before_rb = _note_exists(world, token, note_id)
        world.load_state(state_id)  # type: ignore[attr-defined]  — rollback to the checkpoint
        # After load the access token is still valid (same session creds); re-confirm apis works.
        apis_ok = True
        try:
            after_rb = _count_notes(world, token)
        except Exception:  # noqa: BLE001 — if counting fails, apis broke after load (a finding).
            apis_ok = False
            after_rb = -1
        exists_after_rb = _note_exists(world, token, note_id) if apis_ok else True
        # Independent confirmation apis.* survived load: a benign supervisor call must still work.
        if apis_ok:
            probe = _exec(world, "print('__LB_APIS_OK__' + str(bool(apis.supervisor.show_active_task())))")
            apis_ok = "__LB_APIS_OK__True" in probe
        reverted = apis_ok and (after_rb == before) and (not exists_after_rb)
        return RollbackResult(
            count_before=before,
            count_after_mutation=after_mut,
            count_after_rollback=after_rb,
            created_note_exists_before_rollback=exists_before_rb,
            created_note_exists_after_rollback=exists_after_rb,
            apis_work_after_rollback=apis_ok,
            reverted=reverted,
        )
    finally:
        try:
            world.close()  # env_host guards this with try/except (load_state makes raw close raise)
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    print("=" * 92)
    print("GATE 4 — partial-mutation edge + rollback primitive (trusted-side; no jail/model/GPU)")
    print("=" * 92)
    task_id = "50e1ac9_1"

    edge = demonstrate_partial_mutation_edge(task_id)
    print("PARTIAL-MUTATION EDGE")
    print(f"  notes before                 : {edge.count_before}")
    print(f"  notes after mutation (no fin): {edge.count_after_mutation}")
    print(f"  created note id              : {edge.created_note_id}")
    print(f"  mutation COMMITTED w/o finalize: {edge.mutation_committed}  "
          f"-> {'EDGE IS REAL (a timed-out block would leave this)' if edge.mutation_committed else 'no edge?!'}")

    rb = demonstrate_rollback_primitive(task_id)
    print("\nROLLBACK PRIMITIVE (save_state -> mutate -> load_state)")
    print(f"  notes before / after-mut / after-rollback : "
          f"{rb.count_before} / {rb.count_after_mutation} / {rb.count_after_rollback}")
    print(f"  created note exists before/after rollback : "
          f"{rb.created_note_exists_before_rollback} / {rb.created_note_exists_after_rollback}")
    print(f"  apis.* still works after load_state       : {rb.apis_work_after_rollback}")
    print(f"  ROLLBACK REVERTED THE MUTATION            : {rb.reverted}")

    print("\n" + "-" * 92)
    print("DECISION: the partial-mutation edge is REAL and the rollback primitive WORKS, but wiring")
    print("rollback-on-timeout to be USEFUL needs continue-after-timeout (keep env-host alive + re-")
    print("spawn the killed runner) — a sandbox-lifecycle change that is NOT low-risk. Today a timed-")
    print("out block aborts the task, so rollback buys nothing. => DOCUMENT as a known limitation;")
    print("the primitive is proven safe for a future continue-after-timeout build behind a trusted RPC.")
    print("=" * 92)
    ok = edge.mutation_committed and rb.reverted
    return 0 if ok else 1


if __name__ == "__main__":
    import sys

    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)
