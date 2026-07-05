# Zero-touch moderation — owner-zero for routine cases

Status: **APPROVED DIRECTION 2026-07-05** (owner asked for a plan removing him from day-to-day
operations; design red-teamed by GPT-5.5 Pro, oracle session `zerotouch-moderation-design` —
full transcript retained; its three structural corrections are adopted below). One policy
refinement awaits explicit owner sign-off (§Rank containment).

## Goal

Community submissions flow from `localbench submit run` to the public board with NO owner
involvement for routine cases. The owner's remaining surface: a weekly digest, plus an
owner-only decision class (policy, disputes, legal, protected-name mappings, kill-switch lifts,
secret rotation). An AI agent-maintainer handles escalations under hard policy constraints.

## The three oracle corrections (adopted)

1. **"Accepted" is three states, not one**: *bundle-valid* (fully automatable) →
   *board-row-resolved* (automatable via identity display, not identity trust) →
   *ranked-public* (automatic only for low-blast-radius rows). The draft conflated them.
2. **Rank containment > plausibility bands.** A band only filters cartoon fraud (an attacker
   submits band-max − ε). The real control: any HIGH-IMPACT row (would enter top-10 overall,
   top-3 in size class, #1 for a family, beat prior #1 by >1.5 composite points, or first page
   from a first-time key) publishes as **provisional** — visible, labeled, no medals/#1 badges/
   feed highlights, excluded from the default verified view — until spot-replicated or aged out.
3. **Automate identity display, not identity trust.** Unknown models never block on curation and
   never merge into official catalog rows from HF metadata (repo-editable, not proof): they
   auto-publish as "community-declared · identity unverified" rows keyed by artifact sha256.
   Exact known catalog artifact hash → known identity. Protected/official-looking names or the
   first official row of a major family → owner-only.

## Rank containment refinement (needs owner nod)

Standing policy (owner, 2026-07-05 morning): self-reported agentic ranks WITH a label until
replication ships. Refinement recommended by the red-team and by me: keep exactly that for
low-impact rows; add the provisional quarantine ONLY for high-impact rows (list above) — 24h for
first-key/unknown-identity/self-reported-agentic rows, 72h-or-until-replication for
top-impact rows. This is a narrowing, not a reversal. DEFAULT = adopt unless owner objects.

## Submission state machine (typed, replaces ad-hoc statuses)

pending → bundle_valid | rejected(typed reason)
bundle_valid → accepted_validated → published_provisional | published_ranked |
published_static_only | accepted_identity_unverified (auto-row, unverified identity)
any published → withdrawn | suppressed_abuse (row-level, without full deploy rollback)

## Decision policy (server-side, automatic)

- AUTO-REJECT: every mechanical failure (already typed today): schema, unknown release, digest
  mismatch, missing item, duplicate bundle, conformance, re-score mismatch, non-canonical
  sampler/profile/budget, quota.
- AUTO-ACCEPT (ranked-public only when ALL): hard gates green; static re-score canonical;
  no duplicate/near-duplicate/rate/anomaly flag; display metadata sanitizes (length-capped,
  no markup/links); identity = exact known artifact hash OR auto-created unverified row;
  agentic absent OR (green band AND low rank impact).
- PROVISIONAL: green-band high-impact; first-key rows; unknown identities; self-reported-agentic
  rows per §Rank containment.
- ESCALATE (agent queue): yellow band; ambiguous/protected identity; sybil-pattern flags.
- HOLD ("agentic plausibility hold", not reject): red band — static axes may publish, agentic
  and full-index rank withheld.

## Agentic plausibility band (wave 3 of this plan)

Reference data = TRUSTED ROWS ONLY (project-run, maintainer-run, spot-replicated) — community
self-reports never train the band. Caps per oracle formulas: static_cap (p90 of trusted AppWorld
among rows within ±8 static points, +8pp), size_cap (p90 same-or-next param bucket, +8pp),
family_cap (max exact-family trusted, +5pp, known families only); minimum reference support
(≥5 rows size_cap, ≥8 static_cap; widen once, else no green auto-accept for agentic).
green ≤ min-cap composite; yellow = green+10; red above. Cold start (today): bands inactive —
static publishes normally; agentic self-reports rank only for exact known families with enough
trusted priors, else "self-reported, not rank-bearing". Rank-impact override applies inside green.

## Agent-maintainer (wave 2 of this plan) — two-part, constrained

- RESEARCH AGENT (scheduled Claude session): inspects escalations, fetches public HF metadata,
  proposes typed JSON decisions. Holds NO admin secret, NO deploy key.
- SIGNER/DEPLOYER (policy-enforcing CLI/daemon on the maintainer machine): accepts only typed
  decisions; enforces invariants REGARDLESS of what the agent asks: cannot change policy/
  thresholds/allowlists/weights/label semantics; cannot delete bundles or permanently ban;
  cannot deploy on failed tests/parity/integrity pins; caps: ≤5 accepts/day, ≤10 identity
  mappings/day, ≤20 rejects/day, 0 top-impact accepts without owner or replication; can flip
  AUTO_PUBLISH off, can never flip it back on after an owner/security disable.
- Logging: private signed decision log (full record per oracle schema) + public sanitized ledger
  (hashes, statuses, reason codes, actor class, policy version).
- Owner-only forever: legal/takedown/trademark; disputes/appeals; permanent bans; policy/release/
  weight changes; "verified" semantics; first official mapping of a protected family; kill-switch
  lift after suspected compromise; secret rotation.

## Publication pipeline

Batched deploys, max once daily (agent/owner may force). One command each:
`publish-board` (curation/board regen → tests+parity+integrity-pin gates → deploy → live verify →
public snapshot), `suppress-row <id> --reason` (row-level revert + regen + deploy),
`revert-last-board-deploy`. Board artifact embeds a signed per-row manifest (submission id,
bundle/artifact sha, status, decision actor, policy version, published_at, superseded_by).
AUTO_PUBLISH kill-switch env; auto-freeze alarms: pending>20, submissions_24h>50,
r2_ingress_24h>2GiB, validation queue age p95>30m, escalations_24h>10, accepts_24h>10,
sybil-pattern, any deploy-gate failure.

## Abuse controls (ship with wave 1)

One-use tickets, TTL ≤15m, declared content-length; bundle: 64MiB cap + max file count +
max decompressed size + max transcript length + zip-bomb rejection + streaming validation;
rates: per-IP/hour+day, per-/24+IPv6-prefix/day, per-key/day, per-key cumulative pending bytes,
global/day caps; queues: separate validation/identity/publication with concurrency caps;
board: one best visible row per artifact sha/lane, near-duplicates collapsed, unverified grouped;
R2 lifecycle: pending 24h, rejected 7-14d, accepted-raw 90d, board artifacts forever.
Proof-of-work: NOT now — dynamic (pressure/attack modes) later.

## Submitter feedback (no accounts)

Public per-submission status URL + accepted-rows RSS/JSON feed. `--notify-url` webhooks are
REJECTED for now (SSRF surface not worth it at this volume; full hardening list recorded in the
oracle transcript if ever demanded).

## Implementation waves (this plan's own numbering)

- **ZT-0 Foundation** (no autonomy, pure owner-time savings): typed state machine; public status
  URL; accepted feed; suppress-row/withdraw + revert-last-deploy + one-command publish-board;
  AUTO_PUBLISH kill-switch; R2 lifecycle rules; signed private decision log.
- **ZT-1 Minimum viable zero-touch** (ship this month): auto-reject class (exists) + the narrow
  auto-accept class + auto-created unverified-identity rows + provisional labeling + daily batch
  (≤10 rows) + freeze alarms. No lineage agent, no webhooks.
- **ZT-2 Constrained agent-maintainer**: escalation processing via typed decisions through the
  policy-enforcing signer; daily owner digest (ntfy); owner pinged only for owner-only classes.
- **ZT-3 Agentic containment**: plausibility bands + cold-start rules + rank-impact quarantine +
  spot-replication queue (prioritize top-impact/yellow/first-key/unknown-identity/high-agentic)
  + replication-mismatch annotation; replicated rows become band reference data.
- **ZT-4 Traction hardening** (only at volume): dynamic PoW, sybil heuristics, per-ASN quotas,
  public append-only ledger, appeals process, optional webhook worker.

Interleaving with existing work: ZT-0/ZT-1 slot in after wave-4 site flip; the wave-3 GPU results
review (imminent) is the last manual-maintainer pass done by the agent under current rules, and
doubles as the runbook source for ZT-2's typed decisions.
