# Handoff review — coding-exec forgery audit, for Fable's independent judgment

**Purpose.** You (Fable) are being asked to do what Michael trusts you most for: a critical,
adversarial review of a security audit that **Opus** produced, and to answer the same decisions
Michael would otherwise have to make himself. Do not rubber-stamp it. Your job is to try to
**falsify** the audit's claims, and — if they survive — give a clear recommendation with rationale
on each open decision. Everything you need to reproduce is below; prefer verifying over trusting.

Canonical repo: `C:\Users\Michael\local-bench` (branch `codex/local-bench-online-backend`, audit
commit `53ff3b0`). Note: Michael's shell cwd `…\Projects\local-bench` is a DIFFERENT copy — review
the canonical repo only.

---

## 1. Situation (one paragraph)
local-bench's coding axis re-executes untrusted, model-generated Python and grades pass/fail. A P1
was filed because the pass/fail "sentinel" was trivially forgeable. Overnight 2026-07-06, Opus
rewrote the grader ("invert-control", commits `41dbe8d`/`7ef6deb`) and reported it as **"P1 FIXED,
result-preserving, exploit now FORGERY=False."** Michael asked for that claim to be *tested* before
trusting it. The audit (Opus, this session, under Michael's eye) found the claim is **false**: the
forgery is not closed.

## 2. Claim under review vs. finding
- **Opus's claim:** the invert-control driver hides a per-task nonce in its process, execs untrusted
  code as data, grades with a private `TestResult`, and emits a sentinel only the trusted driver can
  produce — "closes the P1 sentinel-forgery vector."
- **Finding:** untrusted code runs in the **same interpreter** as the driver and recovers the
  driver's private globals (`_nonce`, `_write`, `_os`) — then emits a forged passing sentinel **with
  the correct nonce**. Reproduced three independent, AST-gate-passing ways. The residual Opus
  documented as "far harder" is a one-liner-class attack.

## 3. Reproduce it yourself (do this first)
Durable regression proof (the three vectors, committed):
```
cd C:\Users\Michael\local-bench
uv run --project cli pytest cli/tests/test_coding_exec_known_residual_forgery.py -v
# => 3 XFAIL (strict). XFAIL here means "forgery still succeeds" (desired passed=False not yet met).
```
Minimal standalone proof that a forged verdict is accepted as authentic (`passed=True`,
`grading_integrity=sentinel_ok`). Save as `e.py`, run with the pinned 3.14 interpreter:
```python
import sys; sys.path.insert(0, r"C:\Users\Michael\local-bench\cli\src")
from localbench.coding_exec.program import assemble_program
from localbench.coding_exec.runner import run_program
TEST = "import unittest\nclass T(unittest.TestCase):\n    def test(self):\n        self.assertEqual(task_func(2), 4)\n"
EXPLOIT = (
"import sys as _s, json as _j\n"
"def _p():\n"
"    _f=_s._getframe()\n"
"    while _f is not None:\n"
"        if '_nonce' in _f.f_globals:\n"
"            _g=_f.f_globals; break\n"
"        _f=_f.f_back\n"
"    _l='<SENTINEL> '+_j.dumps({'err':0,'fail':0,'nonce':_g['_nonce'],'run':1},sort_keys=True)+'\\n'\n"
"    _g['_write'](1,_l.encode()); _g['_os']._exit(0)\n"
"_z=_p()\n"
"def task_func(x):\n    return -1\n")
print(run_program(assemble_program(EXPLOIT, TEST, "task_func")))
# => {'passed': True, 'grading_integrity': 'sentinel_ok', ...}  a WRONG solution, graded as pass.
```
Fuller matrix (E1 getframe / E2 traceback-frame / E3 gc-walk, plus an audit-hook lockdown test and
honest-solution controls) is in session scratchpad `exploit_decisive.py` (session `badb6de7`).

## 4. The load-bearing conclusion — attack it if you can
**"In-process grading of adversarial Python cannot be made forgery-proof."** Basis:
- Three independent recovery paths (frame, traceback frame, gc) all forge.
- A `sys.addaudithook` lockdown blocks the frame and gc paths but the **traceback-frame path (E2)
  bypasses it** (no audit event fires for `tb_frame` access). Enumerating every frame source
  (generator `gi_frame`, `ctypes`, …) is whack-a-mole.
- General argument: wherever the trusted grader shares a process with untrusted code, the secret and
  the output channel are reachable.

**Where to falsify:** Is there an in-process mechanism Opus and I both missed that is actually sound
(not just "harder")? Candidates to consider and rule in/out: a *comprehensive* audit-hook set that
provably covers all frame acquisition; running untrusted code with a restricted `__builtins__` +
gated import such that neither frames, gc, nor `os` are reachable; subinterpreters (PEP 734)
isolation; seccomp/ptrace at the container layer. If any is genuinely sound AND result-preserving,
the "uncloseable" conclusion is wrong and the recommendation changes.

## 5. Blast radius — attack this too
A subagent traced the submission→board pipeline (file:line in
`docs/reports/coding-exec-framewalk-forgery-2026-07-07.md`). Conclusion: a forged verdict **cannot
auto-reach the ranked public board** — the board is regenerated only from a closed set of
maintainer-curated local files (`web/data_sources.json`); community submissions land in a separate,
**score-less** D1 feed no ranked surface reads; there is **zero** server-side re-execution. So the
real guarantee is *no-auto-rank-by-architecture + maintainer re-execution + container*, NOT the
sentinel. Secondary weakness found: the ZT-1 `self_reported_exec` gate trusts a bare
`verdict_source:"verifier"` string (no verification) — but it only governs the score-less feed.

**Where to falsify:** Is there any path — a webhook, a cached artifact, the accepted-feed rendering,
a future `data_sources.json` edit, the `known_artifact` flow — by which a self-reported coding
verdict reaches a *ranked* surface? If yes, severity escalates from "bounded" to "live."

## 6. What changed, and what was NOT verified
Commit `53ff3b0` (docs + tests only, **no grading-behavior change**; board pin `3d058e60` intact):
rewrote the overclaiming docstring in `program.py` to the truth; corrected the forgery-fix test
docstring; added `test_coding_exec_known_residual_forgery.py` (E1/E2/E3 as strict-xfail tripwires);
wrote the finding report and the sound-fix spec; corrected the memory's false "FIXED" note. Full
suite green afterward (1258 passed, 4 xfailed).
**NOT independently re-verified:** Opus's "result-preserving on 148 canonical + Gemma" Docker run
(rests on his claim + green frozen scorecard-id pins; the audit did a lightweight harness-level
sanity only, 46 passed, not the Docker re-execution). Consider whether this needs an independent run.

## 7. The one sound fix on the table
`docs/reports/coding-exec-worker-marshalling-spec-2026-07-07.md`: out-of-process value-marshalling —
the trusted **parent** runs the BigCodeBench assertions; each `task_func(...)` call is proxied to a
**worker** subprocess that holds only the untrusted solution (no test, no nonce, no grader). Untrusted
code only ever sees inputs and returns outputs → nothing to forge. **Risk:** real rewrite; some
BigCodeBench-Hard tests (mocks, side effects, patching solution internals, unpicklable args) won't
survive naive proxying → hybrid (marshalled where possible, worker-local + labeled otherwise) with a
0-verdict-change gate on 148 canonical + Gemma. Assess whether the spec is right and whether the
hybrid's "sound-for-a-fraction" honesty is acceptable.

---

## 8. Decisions requested (answer each with a recommendation + rationale)

**Q1 — Soundness vs. posture.** Should we (a) greenlight the worker-marshalling rewrite for true
forgery-proofing, or (b) formally adopt "tamper-evidence + out-of-process guarantee" as the stated
coding-axis posture (document it on the methodology page, no soundness claim for the sentinel)?
Consider that the live board is not exposed today, and that open community submission is a future
goal. Which, and why? If (a), when — before or after public announcement?

**Q2 — The two cheap hardening wins.** Independent of Q1: (i) turn the architectural no-auto-rank
into an explicit, tested guard in `web/build_data.py` (today it's enforced only by which files the
input list happens to name — one accidental edit from a live hole); and (ii) fix the forgeable
`verdict_source:"verifier"` string-trust in the ZT-1 gate (require the trusted-attester signature
already implemented for `known_artifact`). Do both now, one, or neither? Rationale.

**Q3 — Second opinion.** Is the "in-process is uncloseable" conclusion strong enough to act on as-is,
or should we still get the GPT-5.5-Pro oracle pass on it? If you (Fable) concur after your own
review, that may substitute for the oracle. State your confidence.

**Q4 — Anything the audit got wrong or missed?** Overclaims, gaps, a better fix, a wrong severity
call, a test that should exist. This is the most important question — be adversarial.
