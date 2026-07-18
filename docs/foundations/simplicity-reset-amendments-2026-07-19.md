# Simplicity Reset — red-team amendments (2026-07-19)

Source: GPT-5.6 Sol Pro (oracle) simplicity red-team of
`simplicity-reset-2026-07-19.md`. Verdict: **ship the reset** (~85% right as written).
These amendments are binding on the reset tracks; applied in the QA/redirect round.
Constitutional rule adopted verbatim:

> Pre-publication checks may protect the parser, the user's machine, the operator's bill,
> or legal survival. They may not adjudicate whether a complete score is truthful.

## Amendments to Track API (apply in QA round)
A1. **Server owns the composite.** Clients submit six axis scores (+ items); the server
    validates presence/range, computes the ONE official composite itself, and IGNORES any
    client-provided composite/rank. Not score verification — arithmetic consistency.
    (Supersedes "client-computed projection accepted as-is" — the projection is still
    submitted, but its composite fields are recomputed server-side.)
A2. **Badge, not chip.** Replace the two-value trust chip with a server-set
    `project run` badge ONLY (cannot be claimed by clients). Community = the unmarked
    default, not a lesser tier. Free-text handles render as "submitted as … — unverified"
    in row details, never as primary board identity. ("Names make spoofing evident" is
    wrong as anti-spoof theory; stop implying authentication instead.)
A3. **Structured artifact identity, never URLs.** Submission carries structured HF
    repo/revision/filename(/hash where practical) + quant + material inference settings;
    the site constructs all links itself and never renders submitter-provided URLs.
    Display name editable; artifact identity immutable.
A4. **Dedup trim.** Deduplicate byte-identical retries / idempotent resubmissions ONLY.
    Independent reproductions of the same model are VALUABLE — preserve them (median +
    spread on family pages later, when replication is actually observed).
A5. **Resource envelope, not trust gate.** One generous edge rate limit (no honest
    20–48h benchmarker can hit it) + bundle size cap ≈ 2× largest known legit bundle
    (~50MB today). Bundles: fixed format, immutable server-hashed object key, served as
    downloads (never inline user-controlled HTML).
A6. **Signed-manifest requirement dropped** (a signature proves key possession, not model
    provenance). CLI may keep emitting it; server stops requiring. Full removal in cleanup.
A7. Materialized board stays (static-site architecture requires it) but must be one
    idempotent post-publish rebuild that can NEVER block publication.

## Amendments to Track CLI (apply in QA round)
C1. **Coding sandbox hardening is mandatory + fail-closed** (the ONE place pre-execution
    friction is justified — we execute model-generated code): digest-pinned image,
    `--network none`, non-root, `--cap-drop ALL`, `--security-opt no-new-privileges`,
    read-only rootfs + bounded tmpfs work area, pids/memory/cpu/runtime/output limits,
    no host mounts (home/creds/models/workspace), NEVER the docker socket, default
    seccomp retained, force-kill on timeout. If controls can't be enforced → coding axis
    fails → run incomplete. Explicit consent: first-run acknowledgement or
    `--allow-untrusted-code` flag, with plain-language warning.
C2. Preflight the sandbox BEFORE GPU hours (already in spec — keep; extend to verify the
    hardening controls work, not just docker presence).
C3. Composite fields the CLI writes into the projection are advisory; the server's
    recomputation is authoritative (align with A1 — don't fight 400s over it).

## Deferred to site pass / cleanup (my calls, not blockers)
D1. Public protocol label: present the active protocol as a clean public identifier
    (e.g. `LB-2026-07`) at the DISPLAY layer; internal `index-v4.1` enum stays for now
    (renaming across schemas mid-reset = churn against the acceptance test).
D2. Family pages become the default/primary navigation; keep the one global board but
    demote global-#1 prestige treatments (filters: family, size, quant, RAM).
D3. Canonical-JSON machinery: no new work either way; server-side raw-byte hash is the
    bundle identity (already exists as raw_bundle_sha256).

## Policy adopted (docs, not machinery)
P1. **Post-publication leader audit** — a policy, not a workflow: new family leaders (or
    evidence-backed disputes) → `localbench verify` consistency-check from the bundle;
    independent RE-RUN only if consequential + suspicious/promoted; suppress on evidence.
    No pending state, no queue service, no rank exclusion while auditing.
P2. **Terminology discipline**: "consistency-checked" (outputs reproduce scores) ≠
    "reproduced" (independent run agrees). NEVER call re-scoring "verified".
P3. **Honest trust statement** on the site: results are community-reported, publish
    immediately; site preserves exact identity/protocol/scores/evidence bundle, computes
    the common composite, suppresses on demonstrated problems; NOT independently
    reproduced by default.
P4. **No speculative state machines** — new gate/tier/daemon/queue/identity/version
    branch only after: 2 production incidents of the same harm (or 1 threatening user
    machines / legal / unbounded cost), AND suppress-after has demonstrably failed, AND
    it deletes more than it adds, AND it has an owner + success metric + removal trigger,
    AND it keeps the maintainer's machine out of the happy path. Every review outputs
    DELETE / ACCEPT-AS-RISK / MEASURE / ADD — ADD expected empty.
P5. **Complexity budgets** (until ≥100 community rows or 2 substantiated abuse
    incidents): row states = visible|suppressed; 1 active suite; 1 active index; ≤1
    provenance badge; 0 critical-path daemons; 0 mandatory accounts; 0 pre-publish truth
    judgments. Exceptions: host-execution safety, legal, unbounded-spend controls.

## Flag for owner (non-blocking)
F1. One-time review of the six datasets' redistribution terms before treating full raw
    bundles as permanently public (LCB already carries the LeetCode source notice).

## Sharpened release test (adopted)
The reset is complete only when Bonsai-27B and Qwythos-9B submit through EXACTLY the
community path — with the maintainer's PC out of the publication loop — and appear
immediately as ordinary, complete, ranked rows.
