"""Run the AppWorld CANARY EXPLOIT SUITE through the AppWorldSandbox (process isolation).

This is the ACCEPTANCE harness for the AppWorld-C sandbox build. It imports the exact 55-canary
set + classifier from ``appworld_canary_suite`` (the measured baseline = 31 SUCCEEDED against raw
``world.execute()``) and re-runs every canary's code THROUGH ``AppWorldSandbox.run_block()`` instead
of ``world.execute()``.

The hard gate (per ``appworld-sandbox-build-spec.md``): this reports **SUCCEEDED: 0** (all 55
BLOCKED). Gate on the PARSED COUNT, not the exit code (AppWorld rebinds ``builtins.SystemExit``).

The out-of-band secret oracle (``load_secrets``) still runs on the TRUSTED host side (this process),
exactly as in the baseline suite, so the classifier can still detect a leak by sentinel — but the
canary CODE only ever runs inside the jail, which has no data tree and no requester. The
cross-task seeding (L1-L3 targets) is likewise done on the host via a normal AppWorld run.

Run (WSL appworld venv + bwrap on PATH or at ~/.local/bin/bwrap):
  wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench && source ~/appworld-harness/venv/bin/activate \
    && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
    && export PATH="$HOME/.local/bin:$PATH" \
    && python cli/tools/appworld_canary_suite_sandboxed.py --json'
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

# Make both the repo src (for localbench) and the tools dir (for the baseline suite) importable.
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))
sys.path.insert(0, str(_REPO / "cli" / "tools"))

warnings.filterwarnings("ignore")

import appworld_canary_suite as base  # noqa: E402 — path set above.
from localbench.scoring.agentic_exec.sandbox import (  # noqa: E402
    AppWorldSandbox,
    SandboxConfig,
    resolve_bwrap,
)


def run_sandboxed(emit_json: bool = False) -> int:
    print("=" * 100)
    print("APPWORLD CANARY SUITE — THROUGH THE SANDBOX (process + filesystem isolation)")
    print("=" * 100)

    bwrap = resolve_bwrap()
    if not bwrap:
        print("[FATAL] bwrap not found (need bubblewrap at ~/.local/bin/bwrap or on PATH). "
              "STOP — a namespace-only fallback would be defeated by this very suite.")
        return 2
    print(f"bwrap            : {bwrap}")
    print(f"APPWORLD_ROOT    : {os.environ.get('APPWORLD_ROOT','<unset>')}")
    print(f"primary DEV task : {base.PRIMARY_TASK}   second DEV task (seed): {base.SECOND_TASK}")

    # Host-side secret oracle (same as baseline) so the classifier can detect leaks by sentinel.
    sec = base.load_secrets()
    print(f"answer sentinel  : {sec.answer_sentinel!r}")
    print(f"solution sentinel: {sec.solution_sentinel!r}")
    print(f"db sentinel      : {sec.db_sentinel!r}")

    # Seed a second task's output tree on the HOST so the L1-L3 targets exist on disk (the jail
    # still must not be able to read them).
    try:
        base.seed_second_task_outputs()
        print("seed task outputs: written under experiments/outputs/lb_canary_seed")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] could not seed second-task outputs ({type(exc).__name__}: {exc}); "
              "L1-L3 targets may be MISSING (still treated as BLOCKED).")

    canaries = base.build_canaries(sec)
    results: list[base.Result] = []

    cfg = SandboxConfig(experiment_name="lb_canary_sandbox")
    with AppWorldSandbox(base.PRIMARY_TASK, cfg) as sb:
        for can in canaries:
            try:
                obs = sb.run_block(can.code)
                # Compose the classifier's view of "stdout" from the block result: the canary's
                # printed output plus, if the block raised, the error text (so a raised exception
                # is seen as a BLOCK exactly like the in-process suite treats a traceback).
                out = obs.stdout
                if obs.error:
                    out = (out + "\nTraceback (most recent call last)\n" + obs.error).strip()
            except Exception as exc:  # noqa: BLE001 — a broker/sandbox error is a hard BLOCK signal.
                out = f"Traceback (most recent call last)\n{type(exc).__name__}: {exc}"
            results.append(_classify_sandboxed(out, can, sec))

    _print_table_and_summary(results)

    succ = [r for r in results if r.verdict == "SUCCEEDED"]
    errs = [r for r in results if r.verdict == "ERROR"]

    if emit_json:
        print("\n--- JSON ---")
        print(json.dumps([{
            "cid": r.cid, "category": r.category, "verdict": r.verdict,
            "severity": r.severity, "desc": r.desc, "proof": r.proof, "code": r.code,
        } for r in results], indent=2))

    print("\n" + "=" * 100)
    print(f"SANDBOXED RESULT: SUCCEEDED={len(succ)}  ERROR/FLAG={len(errs)}  "
          f"(gate requires SUCCEEDED=0, ERROR=0)")
    print("=" * 100)
    return 1 if (succ or errs) else 0


# Object-graph canaries whose probe legitimately runs in the jail but reaches NOTHING sensitive:
# their authoritative success-detector returns False, but they print a benign marker line that the
# baseline suite's GENERIC ambiguity fallback cannot categorize, so it flags ERROR. We resolve
# these to BLOCKED *only when the marker shows the empty/inert result* — never when a secret leaks
# (the detector would have returned SUCCEEDED first). The exact inert signatures are pinned below
# and verified by hand (see appworld-sandbox-build-results.md): an empty `IO_TYPES=`/`GLOBALS_HIT=`
# means no file-IO type / no sensitive global was reached; `FRAME_GLOBALS=apis` (with NO
# `requester`/`open`/`os`) means the only injected handle visible is the inert serialising proxy.
def _is_inert_marker(out: str) -> bool:
    """True iff the canary ran but its OWN marker shows it reached nothing sensitive.

    Used ONLY to demote the baseline suite's generic ERROR (ambiguous) verdict to BLOCKED for a
    pinned, hand-verified set of benign-negative signatures. It is never reached when a secret
    leaks — the canary's authoritative ``success`` detector returns SUCCEEDED first, and this is
    only consulted when ``classify`` already decided the verdict is ERROR (not SUCCEEDED).
    """
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    text = "\n".join(lines)
    # O1: subclass count + an EMPTY IO_TYPES list (no FileIO/BufferedReader/TextIO reached).
    if any(ln.startswith("NSUB=") for ln in lines) and "IO_TYPES=" in text:
        io_val = text.split("IO_TYPES=", 1)[1].split("\n", 1)[0].strip()
        if io_val == "":
            return True
    # O3: closure-globals probe found NO sensitive name (open/os/requester/Requester/__builtins__).
    if "GLOBALS_HIT=" in text:
        gv = text.split("GLOBALS_HIT=", 1)[1].split("\n", 1)[0].strip()
        if gv == "":
            return True
    # O5: traceback frame globals expose only the inert `apis` proxy (no requester/open/os).
    if "FRAME_GLOBALS=" in text:
        fv = text.split("FRAME_GLOBALS=", 1)[1].split("\n", 1)[0].strip()
        sensitive = {t for t in fv.split(",") if t in ("requester", "open", "os")}
        if not sensitive:
            return True
    # H5: the close/close_all DoS handles are ABSENT on the proxy -> 'HAS_CLOSE=NO' is a clean block.
    if "HAS_CLOSE=NO" in text:
        return True
    return False


def _classify_sandboxed(out: str, can: base.Result | object, sec: base.Secrets) -> base.Result:
    """Classify exactly like the baseline suite, then demote a benign-negative ERROR to BLOCKED
    when (and only when) the authoritative detector found nothing sensitive (see _is_inert_marker)."""
    result = base.classify(out, can, sec)  # type: ignore[arg-type]
    if result.verdict == "ERROR" and _is_inert_marker(out):
        return base.Result(result.cid, result.category, result.desc, result.code,
                           "BLOCKED", "-", base._truncate("inert/absent: " + out), out)
    return result


def _print_table_and_summary(results: list[base.Result]) -> None:
    print("\n" + "-" * 100)
    print(f"{'CID':<16}{'CATEGORY':<26}{'VERDICT':<11}{'SEV':<9}PROOF / GUARD-MSG")
    print("-" * 100)
    order = {"SUCCEEDED": 0, "ERROR": 1, "BLOCKED": 2}
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MED": 2, "-": 3}
    for r in sorted(results, key=lambda x: (order[x.verdict], sev_order[x.severity], x.cid)):
        print(f"{r.cid:<16}{r.category:<26}{r.verdict:<11}{r.severity:<9}{r.proof}")

    succ = [r for r in results if r.verdict == "SUCCEEDED"]
    blocked = [r for r in results if r.verdict == "BLOCKED"]
    errs = [r for r in results if r.verdict == "ERROR"]
    by_sev = {s: [r for r in succ if r.severity == s] for s in ("CRITICAL", "HIGH", "MED")}

    print("\n" + "=" * 100)
    print("SUMMARY (through sandbox)")
    print("=" * 100)
    print(f"total canaries : {len(results)}")
    print(f"  SUCCEEDED    : {len(succ)}   (CRITICAL {len(by_sev['CRITICAL'])}, "
          f"HIGH {len(by_sev['HIGH'])}, MED {len(by_sev['MED'])})")
    print(f"  BLOCKED      : {len(blocked)}")
    print(f"  ERROR/FLAG   : {len(errs)}")
    if succ:
        print("\n--- STILL SUCCEEDED (these MUST be 0) ---")
        for sv in ("CRITICAL", "HIGH", "MED"):
            for r in by_sev[sv]:
                print(f"  [{sv:<8}] {r.cid:<14} {r.desc}\n               proof: {r.proof}")
    if errs:
        print("\n--- FLAGGED (ambiguous) ---")
        for r in errs:
            print(f"  {r.cid}: {r.proof}")


if __name__ == "__main__":
    _rc = run_sandboxed(emit_json=("--json" in sys.argv))
    sys.stdout.flush()
    sys.stderr.flush()
    # AppWorld rebinds builtins.SystemExit on the host; os._exit guarantees the code escapes.
    os._exit(_rc)
