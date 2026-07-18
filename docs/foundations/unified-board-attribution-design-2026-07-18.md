# Unified board with submitter attribution (slice 2 design)

Status: DRAFT for owner review — supersedes the "community lane quarantine" as the
long-term display/ranking model. Written 2026-07-18 after the owner rejected the
permanent two-lane architecture. Nothing here is implemented; the open decisions at
the bottom need owner picks before any build starts.

## 1. The premise change

The site's purpose is a crowd-contributed benchmark. The coverage math is decisive:
one maintainer 5090 can produce a few hundred full suite runs per year against a
space of tens of thousands of model×quant×distill combinations. A board whose
trusted surface grows only at maintainer speed can never serve the purpose.

The core insight that makes crowd trust workable *here*, specifically: **the suite is
deterministic** (pinned tasks, pinned sampler, pinned seeds, pinned suite release).
Two honest submitters benching the same artifact should agree within a small
tolerance. Replication is therefore cheap, and disagreement is a loud signal. The
community is not just the source of rows — it is the verification workforce.

Consequence: **one board**. Trust becomes a per-row evidence tier (badge + filter),
not a page boundary. The current community pages become the ingestion/pending state,
not a permanent side-lane. Everything shipped to date (bundle byte-pinning, sandboxed
coding re-execution, Ed25519 receipts, suppression + snapshots, decision log, lineage
overlay) is the machinery underneath this model and is retained unchanged.

## 2. Submitter identity

Every submission is attributed to a named account. The maintainer submits as
`local-bench`; everyone else under their own handle.

Account mechanics (owner pick, §10-A):
- **A1. GitHub OAuth (recommended).** Cheap to build, anchors identity to an external
  account with visible age/history (raw material for standing, §5), and matches the
  audience. Handle = GitHub login.
- A2. Keypair-native: account = registered Ed25519 public key + handle. Most
  self-sovereign, weakest anti-sybil (keys are free).
- A3. Email + handle. Weakest; not recommended.

In all variants the submission bundle is signed by a per-account key bound at
registration, so rows are cryptographically attributable, and the existing admin
verification / decision-log flow records account identity.

## 3. Verification tiers

Visible on every row as a badge, filterable, and machine-readable in the projection:

| Tier | Name | Meaning |
|------|------|---------|
| T3 | maintainer-run | Reproduced by `local-bench` on the reference box (today's "ranked" semantics) |
| T2 | replicated | ≥N independent submissions of the same (artifact_sha256, quant, suite_release) agree within tolerance (§4), from accounts with independent standing (§5) |
| T1 | single-source | One submission; sandbox-verified coding subset; other axes re-scored but not re-executed |
| T0 | pending | Submitted, not yet through verification |

Identity is orthogonal and keeps its own label: artifact↔HF-repo binding is
`sha-proven` (the exact file exists in the claimed repo), `card-associated`
(slice-1 overlay semantics), or `unverified`.

## 4. Replication mechanics

- A replication is simply another submission of the same (artifact_sha256,
  quant_label, suite_release_id). No special mode; the CLI flow is identical.
- A matching engine groups such submissions into an **evidence group**: one displayed
  row, expandable to per-submitter results, with a replication count badge.
- Agreement rule: per-axis |Δ raw score| ≤ tolerance (default proposal: 1.5 pp per
  axis; coding compared at item level since it re-executes). Tolerances are pinned
  per suite release and shown in the methodology page.
- Divergence beyond tolerance → the group enters a visible **disputed** state, both
  rows flagged, queued for maintainer spot-check. Disputes are public.
- Tier upgrades are automatic when the agreement rule + standing rule pass; the
  decision log records every upgrade with the evidence-group inputs.

## 5. Sybil resistance (the central design problem)

Named accounts are free, so manufactured corroboration on long-tail models — a
fine-tune author "replicating" their own inflated scores from a second account — is
the main attack. No single mechanism kills it; the proposal is a stack (owner picks
the combination, §10-C):

- **S1. Standing gate (recommended).** Replications only count toward T2 from
  accounts with ≥X days age and ≥Y prior non-disputed submissions (defaults: 14 days,
  3 submissions). Slows sock-puppets to a crawl without blocking newcomers from
  submitting (their rows just start T1).
- **S2. Machine-independence heuristics (recommended).** Bundles already carry
  hardware/runtime fingerprints. Replications from an identical machine fingerprint
  do not count as independent. (ASN/IP diversity is possible but a privacy trade —
  default off.)
- **S3. Spot-check lottery (recommended).** Maintainer re-runs a random sample,
  weighted toward anomalies: single-source rows with outlier deltas vs base model,
  first-time accounts, disputed groups. A failed spot-check voids the account's
  standing and marks its rows; the deterrent is the lottery, not the coverage.
- **S4. Replicate-one-to-submit-one onboarding (recommended, lite form).** A new
  account's first action must include a replication of one existing verified row.
  Costs an attacker GPU-hours per puppet, grows coverage as a side effect, and gives
  every account a baseline honesty measurement for free.
- S5. Public challenge path: any account can flag a row with a reason; flags are
  visible and feed the lottery weighting. (Suppression stays maintainer-only.)

## 6. Surface changes

- **Leaderboard**: gains a tier filter. Default view (owner pick, §10-B): T2+T3
  ("verified view", preserves citability) with a one-click "show all" toggle, or
  default-all with badges. Index/composite ranking eligibility follows the same
  pick.
- **Model/family pages**: show all tiers with badges — fine-tunes and distills
  appear under their base family as soon as they exist at any tier. This is where
  the fine-tunes-first-class purpose is actually realized.
- **Community listing (slice 1)**: becomes the "recent submissions / pending
  verification" view.
- **Submitter pages**: `/submitter/<handle>` — their rows, standing, dispute
  history. Reputation made legible.

## 7. Submission contract additions

- Optional-but-default `hf_repo_id` (+ revision) at submission time; server attempts
  sha-match of the exact artifact against repo files → `sha-proven` identity when it
  hits; otherwise slice-1 card-association semantics apply automatically.
- Account binding: bundle signed by the account key; ticket carries the handle.
- Notifications: submitter gets state-change notices (accepted / tier change /
  disputed / published) via the account channel (GitHub notifications or email).

## 8. Migration

- Existing 5 ranked rows → T3 under `local-bench`.
- Qwythos-9B-v2 → T1 under `local-bench` (honestly labeled as the maintainer-run
  canary of the community pipeline), identity `card-associated`.
- Bonsai and future maintainer runs land as T3 exactly as today.
- The b2a publication machinery (snapshots, suppression, static export) is reused
  as-is; the mapper gains tier/attribution fields (schema v3).

## 9. Non-goals for slice 2

Paid features; full dispute-arbitration UI beyond flag/suppress/spot-check; ML-based
anomaly detection (the lottery weighting starts heuristic); federation.

## 10. Owner decisions needed

- **A. Account mechanism**: A1 GitHub OAuth (recommended) / A2 keypair / A3 email.
- **B. Default board view**: verified-only default with show-all toggle
  (recommended) vs show-all default with badges. Plus: do T1 rows enter the ranked
  composite at all, or display-only until T2?
- **C. Sybil stack**: which of S1–S5 (recommendation: S1+S2+S3+S4-lite+S5).
- **D. Replication parameters**: N=2? tolerance 1.5 pp? standing thresholds (14
  days / 3 submissions)?
- **E. Naming**: tier labels as T1/T2/T3 vs words ("maintainer-run",
  "replicated ×N", "single-source") — recommendation: words, never numbers, in UI.

## Appendix: what today's slice 1 already settled

Discoverability (nav + listing + detail), HF-card-declared lineage display with
provenance-honest labeling, network-free publication builds via the reviewed
lineage overlay, hardened merge validation (path traversal, suppression
stale-file removal, score-shape checks), and the display-vs-rank separation as it
stands until this design replaces it.
