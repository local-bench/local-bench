# CODING-EXEC MODULE — DESIGN SPEC + BUILD (2026-06-19)

> **STATUS: BENCHMARK-READY (built + unit-tested, no run yet).** Commits on suite/v1-quant-wedge:
> 24ee12c (hardened sandbox) · 5566234 (vendor BigCodeBench-Hard, 148) · f605c65 (exec harness) ·
> 94f9782 (`localbench code` orchestration + CLI). Security design red-teamed by BOTH frontier models
> (Gemini PASS-with-fixes + GPT-5.5 deep threat-model, 2026-06-19); every MANDATORY finding from both is
> folded into `coding_exec/sandbox.py` + the new fail-closed `preflight_checks` gate (see §Security, the
> "folded in" list). The discrimination run is GPU + Docker gated: needs a digest-pinned image + Michael's go.


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
- Linux: a SECOND isolation boundary is REQUIRED, not optional (GPT-5.5's single biggest finding — rootful
  Docker shares the host kernel, so an N-day LPE in io_uring/eBPF escapes to host and no cap-drop compensates).
  `preflight_checks` auto-selects `--runtime=runsc` (gVisor) when present and FAILS CLOSED on rootful bare-Linux
  Docker with neither gVisor nor rootless, unless the user passes `--allow-unsafe-sandbox`. Mac/Windows get a
  Docker-Desktop VM boundary already — preflight passes them and documents the difference.
- Execution is OFF unless the user passes explicit `--coding-exec`, which prints the "runs model-generated code in
  a sandboxed container" warning.
- The frozen task set + image digest + hardening flags go in the manifest (provenance).

### Folded in from the GPT-5.5 deep threat-model (2026-06-19)
GPT-5.5 confirmed the existing flags as a strong base "for accidental bad code" and named the gaps. All MANDATORY
items it raised are now in code (`coding_exec/sandbox.py`, asserted by `test_coding_exec_sandbox.py`):
- **`--log-driver none`** — dockerd's own log file is NOT bounded by our host stdout reader (a "scream"
  generation could still fill disk via the daemon log). Added to `MANDATORY_SECURITY_FLAGS`.
- **ulimits the cgroup caps miss:** `--ulimit nofile` (FD-exhaustion DoS), `--ulimit fsize` pinned to the tmpfs
  scratch size (no oversized single-file write), `--ulimit core=0` (no core dumps — large + leak in-memory data).
  (No `--ulimit nproc`: process count is the cgroup's job via `--pids-limit`; RLIMIT_NPROC is per-host-uid and
  would false-fail legit code.)
- **No TTY/console** — we never allocate `-t` (reduces exposure to /dev/console runtime bugs, e.g. CVE-2025-52565).
- **Fail-closed preflight (`preflight_checks` + `probe_docker_env`):** the second-boundary requirement above,
  PLUS a **runc CVE floor** (refuse runc < 1.1.12, the CVE-2024-21626 host-fd-leak escape, when runc is the
  executing runtime — skipped under gVisor since runsc replaces runc). Decision logic is injectable → unit-tested
  without Docker; the real probe shells out at run time (gated).

**Deferred to the gated run (documented, not yet built — they need a live Docker/image to validate safely):**
- **Custom seccomp profile** beyond Docker's default (deny io_uring + the residual dangerous syscalls). Held back
  because an over-tight syscall denylist can silently false-fail BigCodeBench solutions; it gets validated against
  real task execution during the Stage-1 throughput probe, not blind.
- **Per-task container isolation option.** v1 runs all tasks in ONE container (each task already in its own fresh
  subprocess; the score is computed by the trusted runner from exit codes, never self-reported — so a malicious
  generation can't false-PASS). GPT-5.5 wants one container per task for stronger cross-task isolation; we'll add
  `--isolation per-task` (recreate the container per task) as the paranoid/ranked path, defaulting to per-run for
  speed, and measure the wall-clock cost of per-task at Stage 1 before choosing the ranked-run default.
- **Image supply chain:** SBOM + signature/provenance + a vulnerability scan of the pinned bigcode image, and
  `--pull=never` after install. Done at the `docker pull` + digest-pin step (itself a no-GPU prep gate).
- **microVM (Firecracker/Kata)** as an even-stronger boundary for non-expert users — future, post-v1.

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
- **Ranked eligibility (oracle #13, ENFORCED — `coding_exec/orchestrate.ranked_eligibility`):** a coding-exec run
  counts as RANKED only if its execution environment is fully pinned — the image is digest-pinned (`@sha256:`,
  which IS the container dependency lock), the in-container `runner.py` is hashed into the manifest
  (`runner_sha256`, harness provenance), and the `--allow-unsafe-sandbox` override was NOT used. The manifest
  records `ranked_eligible` + `ranked_ineligible_reasons`; `localbench code` prints the verdict. A non-pinned or
  unsafe-override run is community/diagnostic, never ranked.

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
