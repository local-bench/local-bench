# Sound coding-exec grading: out-of-process value-marshalling (spec, not yet built)

**Date:** 2026-07-07
**Status:** DESIGN SPEC for maintainer greenlight. This is the *only* design that makes coding
grading forgery-proof against adversarial submissions. It is a real rewrite with genuine
result-preservation risk; do **not** land it unsupervised or under time pressure. Motivating
finding: `coding-exec-framewalk-forgery-2026-07-07.md`.

## Why the current (and any in-process) design can't be sound
The trusted grader and the untrusted solution share one interpreter. Untrusted code can reach
the grader's secret (nonce) and output channel (`os.write`) via frames, tracebacks, or gc, and
forge a passing sentinel. Proven with three independent vectors; a `sys.addaudithook` lockdown
is bypassed by the traceback-frame path. **The secret must not exist in any process that runs
untrusted code.**

## The design
Invert the trust boundary so untrusted code only ever sees *inputs* and returns *outputs* — it
never sees an assertion, a nonce, a pass/fail channel, or the grader's frames.

```
Parent (TRUSTED, never execs untrusted code)          Worker subprocess (UNTRUSTED)
--------------------------------------------          -----------------------------
loads the BigCodeBench test module                    execs ONLY the model solution
runs the test's assertions itself                     into a namespace; no test, no
   task_func(...)  ── proxied call ──►  RPC over pipe  nonce, no grader, no secret
   assertEqual(returned_value, ...)  ◄── result ─────  returns whatever task_func returns
verdict = tests passed (parent decides)
```

* The parent imports the trusted test and runs it. `task_func` in the test's namespace is a
  **proxy object**: calling it pickles the args, sends them over a pipe to the worker, the
  worker calls the real (untrusted) `task_func`, pickles the return value (or the raised
  exception type), sends it back; the proxy returns/raises it in the parent.
* The parent computes pass/fail by running the real assertions on real returned values. There
  is **nothing for the worker to forge** — a wrong answer cannot make `assertEqual` pass.
* The worker has no nonce and no grading code; recovering its own frames yields nothing useful.
* Verdict never crosses a channel the worker controls.

## The hard part — result-preservation (must be measured, not assumed)
Some BigCodeBench-Hard tests will not survive naive call-proxying. Enumerate and handle each,
gated by re-running the **148 canonical solutions + Gemma's 148 real generations** and requiring
**0 verdict changes** before/after:

1. **Unpicklable args/returns** (file handles, sockets, lambdas, live DataFrames with custom
   dtypes). Mitigation: a richer codec (cloudpickle) or, where a value can't cross, run that
   whole test *inside the worker* under the existing (tamper-evident-only) harness and mark the
   item `worker_local` (still contained by no-auto-rank).
2. **Tests that patch the solution's own module internals** (`@patch("__main__.helper")`) —
   the patch must apply in the worker, not the parent. Requires forwarding patches into the
   worker namespace, or running such tests worker-local.
3. **Side effects** (task_func writes files / mutates globals the test then inspects). The test's
   inspection runs in the parent but the effect happened in the worker. Requires either
   mirroring the effect back or running worker-local.
4. **Tests that pass callables/objects to task_func and expect identity** — proxying breaks
   identity. Worker-local fallback.
5. **Performance** — one worker RPC per `task_func` call across 141 scoreable items × N calls.
   Keep one warm worker per item (not per call); measure wall-clock vs the current harness.

Design implication: this is a **hybrid** — pure marshalling for the tests that support it
(the forgery-proof majority), worker-local execution for the rest (contained, not sound). Report
the split honestly per item (`grade_mode: marshalled | worker_local`) so the methodology page can
state exactly what fraction is forgery-proof. Do **not** silently fall back and imply full soundness.

## Acceptance gate
* 148 canonical + 148 Gemma generations: 0 verdict changes vs the pre-change harness.
* All three forgery vectors (E1/E2/E3 in `test_coding_exec_known_residual_forgery.py`) flip to
  `passed=False` for the marshalled items; worker-local items documented as still tamper-evident-only.
* Wall-clock within a stated budget of the current harness.
* Independent review (not the implementer model) of the parent/worker trust boundary.

## Lower-effort alternative if soundness isn't yet a goal
Formally adopt "tamper-evidence + out-of-process guarantee" as the coding-axis posture:
1. State it plainly on the methodology page (no "forgery-safe" claims for the sentinel). *(open)*
2. **Turn the architectural no-auto-rank into an explicit, tested guard** in `web/build_data.py`.
   ✅ **DONE 2026-07-07** — `_assert_ranked_coding_provenance` fails the build if a ranked row
   whose composite includes the coding axis is not maintainer-verified (trust_label `project_anchor`
   AND verdict_source `verifier`). **Hardened after a GPT-5.5 red-team** (was bypassable): the guard
   keys on the **scored coding axis**, not `has_code_artifacts` — coding is scored from bench/item
   correctness independent of any `code_artifact`, so an artifact-keyed guard skipped a coding-scored
   run that carried no `code_artifact`. Also `_code_verdict_source` now **fails closed** (a single
   `submitter` item aggregates to `submitter`, not `verifier`, so mixed provenance can't pass).
   Regression tests in `cli/tests/test_web_build_data.py`.
3. Fix the forgeable `self_reported_exec` gate in `submission-zt1-decision.ts`.
   ✅ **DONE 2026-07-07** — `codingStateFor` honors coding trust ONLY from a server-assigned
   `project_anchor` origin (admin-secret; not self-declarable) with all items verifier-sourced.
   **Hardened after the red-team** (was bypassable): **ANY community coding now escalates**
   (`self_reported_exec` → hidden) regardless of verdict_source — the old `generated_unverified`
   auto-accept let a community submitter dodge review with an empty `code_artifact` (null
   verdict_source) while claiming passing items. NOTE: the review's "reuse the existing Ed25519
   `trustedAttesterSigned`" was NOT the right wiring — that attester is agentic-bound
   (`{success, collateral_damage}` schema) and there is no coding-bound signer, so reusing it would
   spuriously accept an unrelated AppWorld attestation as "coding is verified." A per-coding-verdict
   attestation scheme (over the `CodeVerdict` + `assembled_program_sha256`) is the future path to
   let a trusted community coding claim through; tests in `web/tests/submission-zt1-auto-publish.test.ts`.
