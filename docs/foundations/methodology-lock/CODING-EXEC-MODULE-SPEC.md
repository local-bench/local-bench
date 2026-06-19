# CODING-EXEC MODULE — DESIGN SPEC (2026-06-19, pre-build, pre-security-red-team)

*Michael chose (2026-06-19, after the dual red-team) to BUILD the opt-in code-EXECUTION axis — the path both
GPT-5.5 and Gemini said real coding coverage requires. This widens the locked judge-free core (METHODOLOGY-v1.2
stands); it does not unlock it. This is a DESIGN for sign-off; nothing is built yet, and no run happens without
GPU sign-off.*

## Why this exists
The dual red-team verdict: judge-free coding proxies (CodeMMLU MCQ, CRUXEval I/O) measure code *reasoning/trivia*,
not code *generation*. A credible "can your local model actually write working code vs frontier" axis requires
EXECUTING the generated code against tests. That is the deliberate relaxation of the no-exec constraint — scoped,
sandboxed, and OPT-IN, so the reproducible judge-free headline is unaffected for users who don't run it.

## THE architectural decision (needs Michael) — where does execution happen?
- **(A) LOCAL opt-in [RECOMMENDED].** The user runs the hardened Docker harness on THEIR machine: their model
  generates the code (their GPU/endpoint), the code executes in a sandboxed container locally, only the pass/fail
  test results + transcript are uploaded; the server re-scores from the transcript (and can re-execute a sample
  for a "verified" badge later). **We never execute untrusted code on our infra in v1.** This matches the
  product's "you bring the compute" model, has direct precedent (bigcode-evaluation-harness PR-submission;
  EvalPlus `ganler/evalplus` image), and is the right risk posture for a solo builder.
- (B) SERVER-SIDE. User's model generates code; code ships to OUR sandbox fleet (gVisor/Firecracker) to execute.
  More verifiable, but a real ops + security + liability commitment (container-escape CVEs, a fleet, monitoring).
- (C) HYBRID. Local by default + server-side re-execution of a sample for the badge.

**Recommendation: ship (A) now, leave a clean seam for (C) later.** The rest of this spec assumes (A).

## Benchmark choice (first exec axis)
- **BigCodeBench-Hard [RECOMMENDED]** — Apache-2.0, ~148 tasks, CPU-only Docker, unit-test scored, MEASURED
  spread 18% (7B) → 27% (32B) → ~60% (frontier): discriminates the whole local→frontier range, not saturated,
  lightweight to run. Official images: `bigcodebench/bigcodebench-evaluate`.
- NOT SWE-bench for v1 — it needs per-task images, ~128 GB RAM, and an agent scaffold (much heavier); revisit as
  a second exec rung once the harness exists.
- Coding-EXEC only for v1. Agentic-exec (real tool environments) is deferred — heavier, and the red-team said
  agentic needs a real environment we don't yet have.

## Security model (this is the load-bearing part — to be red-teamed before build)
Execution is user-side (A), so OUR liability is bounded, but the harness we ship must still be a real sandbox so
WE aren't the reason a user's machine gets owned by a malicious/buggy generation:
**LOCKED after the dual security red-team (GPT-5.5 + Gemini 3.1 Pro, 2026-06-19).** Gemini verdict: user-side
opt-in Docker is a PASS for v1 hobbyist local execution WITH the mandatory fixes below (and an explicit FAIL for
any server-side multi-tenant design — confirming the local-only posture).

MANDATORY host-OS hardening (every `docker run`, default-on — encoded in `coding_exec/sandbox.py`, asserted by tests):
- Base = vendored **bigcode evaluate image pinned by SHA256 digest**; `--rm`.
- Generation (model → code) STRICTLY separated from execution (code → tests); the executor has NO network, NO model.
- `--network none` · `--read-only` rootfs · `--user` non-root · `--cap-drop ALL` · **`--security-opt
  no-new-privileges`** · default seccomp active (blocks unshare/ptrace/bpf) · `--pids-limit` · `--memory` +
  **`--memory-swap` = `--memory`** (disable swap so a generation can't thrash host disk) · `--cpus` ·
  **`--tmpfs /tmp:rw,size=<N>m,mode=1777`** (bounded scratch — unbounded tmpfs can eat 50% of host RAM) ·
  **`--init`** (reap zombies + propagate SIGKILL on timeout) · `--ipc none`.
- **Host-side output truncation (the "scream" attack):** read container stdout/stderr in bounded chunks and KILL
  past a cap (~5 MB) — else endless output OOMs our OWN host process despite the container memory cap.
- **No writable host bind-mount, ever.** Results leave via bounded stdout, not a mounted file; the only mount is a
  READ-ONLY mount of the generated-code/task file.
- Linux: offer `--runtime=runsc` (gVisor) and recommend it (shared host kernel → an N-day LPE in io_uring/eBPF
  escapes to host); Mac/Windows get a Docker-Desktop VM boundary already — document the difference.
- Execution is OFF unless the user passes explicit `--coding-exec`, which prints the "runs model-generated code in
  a sandboxed container" warning.
- The frozen task set + image digest + hardening flags go in the manifest (provenance).

**SCORE-INTEGRITY isolation (Gemini's "biggest thing you're not seeing"):** the benchmark's own unit tests must
NOT run in the same Python process as the untrusted generated code — a malicious generation can monkeypatch
`unittest`/`pytest` to always-pass or exfiltrate hidden tests into the transcript. Inside the container each task's
generated code runs in a FRESH subprocess and the verdict is computed by the trusted harness, never self-reported;
the server re-derives the score from the structured result, never from a model-emitted "I passed." This is
host-safety-independent and ties to our trust model (replication, never "verified").

## Integration + scoring
- New lane, clearly labeled **"exec"** — never pooled with the judge-free headline lane; a coding-exec score is
  shown as its own axis with its own CI, opt-in.
- CLI: `localbench code --endpoint ... --model ...` (or `localbench run --coding-exec`) → pull frozen
  BigCodeBench-Hard items → drive the user's endpoint to generate → run the hardened Docker harness → parse the
  pass/fail result JSON → emit a coding-exec axis score with bootstrap CI.
- Scoring is deterministic (tests pass/fail), server-re-scored from the uploaded transcript + results.

## The measurement-before-lock gate (non-negotiable, GPU+exec-gated)
Building the harness does NOT make coding a headline axis. Before it's weighted in:
- Run BigCodeBench-Hard reasoning-on across **≥3 model families × 3 sizes + ≥1 frontier anchor** on our harness.
- Confirm it DISCRIMINATES (clean local→frontier spread, non-overlapping CIs) AND check Gemini's cross-family
  **parse/extraction-failure** flag (code-block extraction must not fail at wildly different rates across
  families — else it's a formatting test).
- Only then promote coding-exec from candidate → headline with a spread-proportional weight (registry edit).

## Build sequence (no GPU, no exec runs until the gate)
1. **Security red-team the sandbox design** (GPT-5.5 + Gemini) — a botched sandbox is the real risk.
2. Vendor BigCodeBench-Hard (Apache-2.0) + pin the eval image digest; audit existing harness infra to reuse.
3. Build the local exec harness (hardened Docker runner) + the result-parsing scorer + `localbench code` CLI +
   manifest fields; unit-test the scorer + harness wiring against captured fixtures (NO model runs).
4. Gated validation run (the measurement gate above) — only on Michael's GPU sign-off.
