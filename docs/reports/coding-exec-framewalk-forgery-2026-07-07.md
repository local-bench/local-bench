# Coding-exec sentinel forgery is NOT closed by #42 — frame/traceback/gc recovery of the nonce

**Date:** 2026-07-07 (early AM, Brisbane)
**Author:** Claude (audit pass, at Michael's request to *test* the overnight #42 work)
**Status:** OPEN finding. The #42 invert-control redesign (commits `41dbe8d`, `7ef6deb`) is an
improvement over the trivial `raise SystemExit(0)` + cleartext-`__file__`-nonce exploit it
replaced, but it does **not** close the sentinel-forgery vector. This report supersedes the
"closes the P1" language in `cli/src/localbench/coding_exec/program.py` and the
"#42 coding forgery FIXED" claim in the 2026-07-06 close-out memo.

## TL;DR
A submitter's untrusted BigCodeBench solution can still forge a passing coding verdict with the
correct per-task nonce. The nonce lives in the trusted driver's process; untrusted code runs in
that same process and can recover the driver's private globals — including `_nonce`, the
pre-captured `os.write`, and `os` itself — through at least **three independent** paths, then
emit a forged `<SENTINEL>` and `os._exit(0)` before the driver grades anything. All three pass
the AST gate. Empirically reproduced against committed code.

## Why the #42 design does not hold
The driver execs the untrusted solution via `exec(compile(_solution, ...), _mod.__dict__)` from
its own top-level frame. Everything the driver needs to keep secret is reachable from inside the
same interpreter:

| Vector | Mechanism | Passes AST gate? | Committed driver | + `sys.addaudithook` lockdown |
|---|---|---|---|---|
| **E1 getframe-walk** | `sys._getframe()` then walk `.f_back` to the frame whose `f_globals` holds `_nonce` | yes | **FORGES** | blocked (audit event `sys._getframe`) |
| **E2 traceback-walk** | raise+catch, read `sys.exc_info()[2].tb_frame`, walk `.f_back` | yes | **FORGES** | **STILL FORGES** — tb-frame access fires no audit event |
| **E3 gc-walk** | `gc.get_objects()`, find the displaced real `__main__` module object by its `_nonce`/`_write` attrs, recover `_os` from it | yes | **FORGES** | blocked (audit event `gc.get_objects`) |

Honest controls behave correctly throughout (wrong solution → fail, correct solution → pass;
plain/numpy/pandas honest solutions still pass under the audit-hook lockdown), so the harness
itself is sound — it is the *secret-in-process* model that fails.

### The AST gate does not stop it
`ast_gate.py` allows top-level assignments to plain names with an **arbitrary right-hand side**
(`_top_level_violation` → `ast.Assign` with plain-name targets), and does not restrict
`sys._getframe`, frame attribute access (`f_back`, `f_globals`), `tb_frame`, or `gc.*`. So the
whole exploit is a few `name = <arbitrary expr>` statements plus helper `def`s (loops live inside
the helpers, which the gate does not inspect for control flow). Tightening the gate is
whack-a-mole against obfuscation (`getattr(x, "f_"+"back")`, building names from chars, etc.).

### An audit hook is insufficient
`sys.addaudithook` is C-level and unremovable, and it *does* cleanly stop E1 and E3. But E2 —
obtaining a frame from a caught exception's traceback — triggers no audit event, so it walks to
the driver globals and forges a pass **with the hook installed**. There is always another frame
source (generator `gi_frame`, C-level `ctypes`, …). Enumerating them is a losing game.

## The load-bearing conclusion
**In-process grading of adversarial Python cannot be made forgery-proof.** Wherever the trusted
grader shares an interpreter with untrusted code, the untrusted code can read the grader's
secret and fabricate its output. The nonce/sentinel is therefore **tamper-evidence and a
casual-forgery deterrent, not a soundness guarantee.** Any claim that the coding axis is
"forgery-safe" purely from the in-process sentinel is false.

The coding axis's real soundness must come from **out of process**:
1. **Coding rows never auto-rank** — community coding scores are held for maintainer review, never
   promoted to the ranked board by the automated pipeline. (See the blast-radius section — this
   must be *enforced in code*, not merely documented. Now enforced: `build_data.py`'s
   `_assert_ranked_coding_provenance` fails the build if a ranked row carries a non-maintainer-verified
   coding verdict.)
2. **The board holds only the maintainer's own (non-adversarial) model runs.** This — not
   re-execution — is what makes today's board safe: the maintainer benchmarks their own models and
   has no incentive to forge against themselves.
3. **Container isolation** — the hardened, network-off, read-only-rootfs container bounds the blast
   radius of any single run to its own subprocess + tmpfs.

**NOT a defense: maintainer re-execution.** An earlier draft listed "the maintainer re-runs the
coding in the hardened container" as a soundness pillar. It is not one. Re-running the *same
forgeable harness* on an adversarial generation just re-confirms the forged pass — a frame-walking
`task_func` forges whoever runs it. Re-execution defends against non-determinism and environment
drift, not against forgery. Once community coding is ever eligible to rank, re-execution alone will
not protect the board — you need either the worker-marshalling fix or manual code inspection of the
generation (a human reading the source would spot the frame-walk; the interpreter will not).

## The one sound fix (for when automated coding-row trust is actually wanted)
Out-of-process **value-marshalling** (see `coding-exec-worker-marshalling-spec-2026-07-07.md`):
the trusted parent runs the BigCodeBench assertions; each `task_func(...)` invocation is proxied
to a worker subprocess that contains *only* the untrusted solution — no test, no nonce, no grader,
no reachable secret. Untrusted code only ever receives inputs and returns outputs, so there is
nothing to forge. This is the only design that removes the in-process secret entirely. **Cost:**
a real rewrite with genuine result-preservation risk (mocks, side effects, patching solution
internals, unpicklable args in some BigCodeBench-Hard tests). Not a rushed/unsupervised change.

## Reproduction
`scratchpad/exploit_framewalk.py` (E1, minimal) and `scratchpad/exploit_decisive.py` (E1/E2/E3 +
audit-hook matrix + honest-solution regression) in session `badb6de7`. Run with the pinned 3.14
interpreter against `cli/src`. E1 output:

```
passed            = True
grading_integrity = sentinel_ok
forged sentinel   = <SENTINEL> {"err": 0, "fail": 0, "nonce": "<the real per-task nonce>", "run": 1}
```

## Recommended actions
1. **Now (safe, no regression):** correct the overclaiming docstring + memory to the truth above.
2. **Now (verify):** confirm in code that forged coding cannot auto-reach the ranked board
   (no-auto-rank enforcement). If it can, that is a live P1 for the moderation layer, not just the
   harness.
3. **Track, don't silently fix:** land the three vectors as a `known-residual` test so no future
   change can claim "closed" without a proof that all three (and the class) are addressed.
4. **Decide:** greenlight the worker-marshalling rewrite if automated coding-row trust is a goal;
   otherwise formally accept "tamper-evidence + out-of-process guarantee" as the coding-axis
   security posture and document it as such on the methodology page.
