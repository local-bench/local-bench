# Changelog

## 0.4.6 - Unreleased

- Resumed runs report cumulative benched wall time; previously only the final resume
  segment was counted.
- One-shot `submit run` can present the admin secret when minting a ticket, so maintainer
  submissions are born as project-anchor tickets and labeled `project run` instead of
  community. Anonymous submissions are unchanged and send no admin-secret header.
- Persisted agentic run provenance now records `distribution_version_skew` with the
  worker and host versions whenever a permitted skew is present.
- C4 agentic runtime identity now records the worker-reported LocalBench distribution
  version when available, with host identity retained only as the compatibility fallback.
- Worker/host distribution skew warnings are emitted once per CLI process instead of
  once per sandbox spawn; the warning text and hard worker-content digest gate are unchanged.

## 0.4.5 - 2026-07-22

- Disabled llama.cpp's cross-request host prompt-state cache (`--cache-ram 0`) for canonical ranked
  runs, and pinned context-checkpoint behavior (`--ctx-checkpoints 32`,
  `--checkpoint-min-step 8192`) at current upstream defaults so future llama.cpp default changes
  cannot silently alter the serve contract. Model weights, context size, f16 K/V precision,
  sampling, and slot count are unchanged. The prompt cache is a performance facility; exact bitwise
  token identity with cache-enabled executions is not guaranteed, and the new policy is reflected
  in the serve fingerprint. Note: an interrupted 0.4.4 run cannot be `--resume`'d under 0.4.5
  (resume identity fails closed by design).
- Agentic preflight now tolerates worker/host distribution version skew with a warning
  instead of failing: the signed worker rootfs releases on its own cadence, and the
  `worker_content_sha256` digest comparison remains the binding integrity gate (a
  byte-identical worker under an older version label passes; any content change still
  fails closed). This restores the agentic axis on fresh installs pairing the 0.4.3
  signed appliance worker with a newer host CLI.

## 0.4.4 - 2026-07-21

- `bench --allow-untrusted-code` now chains the coding verifier automatically after the
  run completes, so a finished bench is submit-ready; on verifier failure the run keeps
  its `generated_unverified` state and the exact manual `code` command is printed.
- `code --pending-run` accepts a run directory as well as the run-document file, and the
  submit `incomplete_run` error prints an invocation-derived remediation command.
- WSL transport teardown after a fully-scored run is best-effort: a discover/teardown
  failure (e.g. process exhaustion after heavy sandbox churn) retries once, is recorded
  in the run document, and no longer fails a completed multi-hour run.
- Coding preflight pulls the sandbox image as an explicit step with its own timeout
  before the control probe, and detects daemon transports that drop attach output
  (Windows + WSL2 localhost relay) with a targeted diagnostic.
- Advanced bench pre-caches the `--hf-model-id` tokenizer automatically when online
  (recording the resolved revision in provenance); `--offline` still refuses.
- One-shot raw-HF-repo runs print why they are a local preview and the ready-to-paste
  ranked recipe derived from the invocation; stale version strings removed from
  eligibility messages.
- New docs: `docs/coding-sandbox-windows-wsl.md` (Windows CLI with a WSL2-hosted Docker
  engine: rootless vs rootful stores, adapter-IP transport, keepalive patterns).
- Project metadata: the PyPI Repository link now points at the project site
  (the historical source mirror is not maintained).

## 0.4.3 - 2026-07-20

- Projections now carry run environment provenance (runtime name/version/backend, first
  GPU + VRAM, decode throughput, wall time, median completion tokens) so board rows can
  show hardware and runtime for community submissions.
- `submit upload` builds and sends the same client-reported projection as `submit run`
  (previously it burned the bundle digest on a guaranteed server rejection), and
  `submit run --base-model <hf-repo>` records declared lineage in the projection.
- Ticket-specific upload byte limits are enforced server-side at request-upload and at
  completion reconcile; `upload_byte_budget_exceeded` now maps to the retryable 429 exit.
- Coding completeness predicates are shared between grading finalize and projection, so
  extraction-failure items count as terminally graded everywhere.
- README and CLI copy describe publish-on-submit (rows publish immediately with
  attribution and post-hoc moderation) and the five-headline-axis index.
- The Coding axis is scored over the 141 sandbox-scoreable BigCodeBench-Hard items in
  both lanes, matching the published methodology; legacy aggregates that inclusively
  counted the 7 network-dependent items are normalized at rescore time.
- `setup-agentic` now provisions the same signed, pinned appliance on Windows through
  managed WSL2 or natively on Linux under mandatory bubblewrap isolation, with lifecycle,
  integrity, preflight, and attestation parity across both host paths.

## 0.4.3.dev0 - 2026-07-19

- Corrects the unequal Agentic scoring protocol in index-v4.2: every ranked row now uses AppWorld task-goal completion on the same fixed 96-task subset. The 25% weight is unchanged; BFCL v3 multi-turn base remains available as a frozen, unweighted diagnostic. Raw inference outputs are unchanged and no model is re-run.
- Requires complete five-headline-axis runs for submission and removes the partial `--static-only` path.
- Grades coding locally in the pinned, network-disabled Docker sandbox before submission; adds
  `grade-coding` for existing run JSON and offline bundles.
- Sends the raw bundle with its client-reported v2 projection and preserves carried coding and
  agentic verdicts through offline verification.
- Maps the complete five-headline-axis editorial profile to index-v4.2 and derives dynamic benches from
  the suite release manifest, with legacy SCORECARD fallback.

## 0.4.2 - 2026-07-18

### Agentic appliance c0v4

- The pinned agentic sandbox appliance moves to c0v4 with a 0.4.2 worker.
  0.4.1 hosts fail closed against the c0v3-r2 appliance (its baked worker is
  0.4.0, and worker/host distribution versions must match exactly), which made
  agentic scoring unreachable on 0.4.1; installing 0.4.2 and re-running
  `setup-agentic` provisions the matching runtime.

## 0.4.1 - 2026-07-17

### Custom-runtime support: agent-isolation reconciliation

- `--no-agent` is now reconciled against the server's actual feature surface:
  builds whose `--help` exposes no agent feature at all (e.g. the PrismML
  ternary fork, base b9594) cannot enable server-side agent execution, so the
  flag is inherently satisfied and is dropped from the launch argv instead of
  failing the strict-flag gate. Builds that expose agent flags without a
  `--no-agent` disable are still rejected, and modern mainline builds are
  unchanged. Provenance is unaffected: build identity records the full help
  text + sha256 and the fingerprint records the argv actually used.
- The strict-flag rejection message now names a known-good mainline build
  (b10050+) instead of leaving the minimum requirement unstated.

First exercised by Bonsai-27B ternary (`Q2_0` group-128 GGUF) on the PrismML
llama.cpp fork - the first non-stock-runtime model benchmarked end-to-end
through the public CLI.

### JCS projection digests (first-exercise fix)

- Projection object/semantic digests are now computed over JCS/ECMA-formatted
  canonical bytes matching the Worker's `canonicalJson` re-serialization.
  Python's `json.dumps` float formatting ("0.0", "1e+16") cannot survive a
  JSON round-trip through the server and 409'd the first real accepted
  verification (`projection_object_sha_mismatch`).
- Verdict attestations (the other client-signed surface the server
  re-serializes before verifying) sign and digest over the same JCS bytes.
  Byte-identical for the current bool-only verdicts; closes the latent
  divergence a future numeric verdict field would have triggered.

### Agentic axis rename + index-v4.1 reweight (owner directive 2026-07-17)

- Renames the season-2 macro-axis display label from "Tool Use" to "Agentic" everywhere user-facing (CLI registry display, site axis columns, methodology). Structural identifiers are unchanged: axis key/web key `tool_use`, facet keys `agentic` / `multi_turn_tool_control`, bench ids, coverage profile `full-exec-tooluse-5axis-v2`, and all stored-run/projection data keys.
- Reweights the headline composite to index-v4.1: Agentic 0.20 -> 0.25; Knowledge/Instruction-Following/Coding 0.24 -> 0.225 and Math 0.08 -> 0.075 (the 5 points come proportionally from the four other weighted axes, a 15/16 scale; weights sum to exactly 1.0). Facet split (10/17, 7/17) unchanged. Long-Context stays 0.
- Bumps `SCORECARD_VERSION` to "6" (weights and the display label are hashed into the registry digest), so new runs carry a new `scorecard_id` and suite-v2 manifest identity; frozen v1 profile identities are untouched.
- index-v4.0 (20/24/24/24/8) remains a distinct historical editorial scale; ranked rows must be re-scored to move to index-v4.1, and the cross-season comparison guards treat v4.0 vs v4.1 as different scales.
- The frozen accepted-result projection v2 contract was widened (owner-gated, additive-only) to admit index-v4.1 alongside index-v3.0/index-v4.0; shipped 0.3.x/0.4.0 clients keep submitting their own labels and are re-projected maintainer-side. The enum is never narrowed after public exposure.

## 0.4.0 - 2026-07-16

Changes are relative to the verified 0.3.2 source point (`8c242b2`) and its
streaming-file-hash release fix.

### Appliance (C1/C2)

- Adds reproducible signed runtime artifacts with complete rootfs inventory, package/content admission, and offline signing inputs.
- Adds transactional WSL provisioning, marker-backed ownership checks, resumable downloads, import recovery, and explicit cleanup operations.

### Bridge (C3)

- Pins Windows worker launches to the provisioned managed distro and installed worker module; native Linux uses direct execution.
- Reasserts worker identity on every spawn and reports launch, pipe, handshake, and teardown failures as agentic infrastructure errors.

### Runtime identity (C4)

- Defines a canonical path- and host-independent agentic runtime identity from the runtime, worker, AppWorld, task, contract, scorer, and installed distribution inputs.
- Carries the identity object and digest through run records and submission bundles without changing the frozen accepted-result projection.
- Uses verified cached runtime manifests offline and rechecks ownership before an active-runtime handshake.

### Crash-safe journal and resume (C5)

- Commits finalized task results to a checksummed append-only journal after verified teardown, with exclusive-writer locking and torn-final-record recovery.
- Resumes from the committed task set, refuses identity drift, preserves conditional third-run decisions, and derives stage reports from journal state.

### Rank gate and fault injection (C6)

- Adds contract-conditional whole-task retry and rank-gate evaluation, including journaled gate verdicts and retained failed-attempt evidence.
- Adds fault injection at worker startup, open, block RPC, model transport, finalize, close, and teardown boundaries.
- Adds the read-only historical impact scan and deterministic unsigned v4 payload builder.

### V3 inertness

- Keeps the active v3 contract on zero whole-task retries and the legacy all-manifest-task denominator.
- Activates non-measurement infrastructure semantics only for a future contract that explicitly carries the required fields.
- Leaves existing board scores, rank status, and frozen projection contracts unchanged.

### Publication and season 2

- Adds strict projection-v2 hash domains, immutable snapshot lineage, isolated trusted/community populations, and deterministic publication mutation gates.
- Adds the season-2 BFCL multi-turn split, tool-use macro axis, cross-season guard, coverage/facet backfill checks, and index-v4 board cutover.
- Verifies coding receipts during admission and keeps the B2a current/previous-client compatibility checks reproducible from pinned wheels.

### Fixes

- Stabilizes GPU resume identity against volatile device-memory text and preserves bounded C6 recovery behavior.
- Hardens managed-worker pinning, process-group teardown, timeout provenance, contract activation, rootfs ELF scanning, and release manifest canonicalization.
- Binds the B2a RC source provenance to the repository HEAD and requires a clean tracked tree before the positive compatibility gate runs.
- Makes fresh test environments use the declared dev dependency group and removes the BFCL tests' dependency on an aged virtual-environment checkout.

## 0.3.1 - 2026-07-10

- Checks AppWorld agentic eligibility before downloading tokenizer or GGUF assets and reports missing harness setup with dedicated exit code 15.
- Adds `--static-only` for an explicit five-axis run under the existing `static-exec-5axis-v1` coverage identity, with the full-index consequence shown before work starts.
- Removes maintainer-specific WSL and AppWorld paths from defaults and help output; agentic runs now require explicit harness configuration.
- Keeps the 0.3.0 recoverable empty-turn behavior for transport/HTTP failures, with additive typed diagnostics. The accepted behavioral deltas are precisely: (1) generations lasting 121-600 seconds now complete instead of timing out; and (2) a turn reached after task transport-deadline exhaustion returns the recoverable empty turn without making an HTTP request. Nothing else changes versus 0.3.0 transport semantics. A task-wide monotonic deadline, socket cancellation, and joined teardown bound the longer request floor.
- Records WSL bridge operation timeouts as infrastructure timeouts visible in run diagnostics.
- Includes the 1,800-second per-task watchdog for supported slow local hardware.
