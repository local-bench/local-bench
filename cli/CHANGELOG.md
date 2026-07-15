# Changelog

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
