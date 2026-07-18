# Publish-then-moderate: the unified community board (v2)

Status: **APPROVED DIRECTION** (owner, 2026-07-18) — this version supersedes the v1
draft's verify-first framing, its T0-pending gate, and the sybil stack. v1's mistake,
per the owner: the pipeline was designed like a bank (nothing visible until a human
verifies) when the product is a community site (everything visible, attributed, and
moderated after the fact). Implementation is in flight under this doc.

## 0. Owner directive (verbatim intent)

One-line CLI → run → submit → the result is **visible on the site within minutes**,
under the right base-model family, attributed to the submitter. The site's job is to
accept crowd-submitted benchmark data and organize it so each base model page
encapsulates all quants, fine-tunes, and distills, answering "which variant is most
performant, and do any fine-tunes beat base?" The maintainer cannot run 10,000
benchmarks; crowdsourcing is the point. Spoofing risk is accepted as low-incentive and
handled by attribution + expected-delta flags + after-the-fact removal, not by
pre-publication gates. Human judgment moves AFTER publication.

## 1. Trust model

- **Publish by default.** A submission that passes *automatic machine verification*
  publishes with no human in the loop. Human actions are after-the-fact: suppression,
  flags, spot-checks, tier upgrades.
- **Attribution is the trust primitive.** Every row shows who submitted it (display
  name + key fingerprint now; GitHub handle when OAuth lands). Maintainer rows say
  `local-bench`.
- **Tiers are upgrade badges, not gates.** A row's evidence level is displayed and
  filterable, never a precondition for visibility.
- **Determinism makes replication cheap** (pinned tasks/sampler/seeds/suite). Two
  honest runs of the same artifact agree within tolerance; disagreement is a loud,
  visible signal. Replication counting is phase 3.

Tier ladder (words in UI, never numbers):

| Tier | Meaning | How a row gets it |
|---|---|---|
| maintainer-run | run + verified on the reference box (today's ranked semantics) | origin `project_anchor` |
| replicated ×N | ≥N independent submissions of same (artifact, quant, suite) agree | phase 3 matching engine |
| re-scored | axis scores recomputed by the auto-validator from the raw per-item records | automatic, minutes after upload |
| self-reported | displayed from submitter data, not yet re-scored | only while the validator is catching up |

Orthogonal per-axis chips: coding `pending verification` → `verified` (sandbox
re-exec receipt); agentic `self-reported` → `attested`. Identity: `unverified` /
`card-associated` / `sha-proven` / `maintainer-verified` — evidence-derived, not
origin-derived.

## 2. Target pipeline

```
CLI submit (3-leg presigned upload, PoP, byte-pinned — UNCHANGED, works for 0.4.2)
  → /complete: size cap + streaming sha256 match (UNCHANGED) → status pending_verification
      · immediately visible: /api/submissions/queue + submissions page ("received — scoring queued")
  → AUTO-VALIDATOR (maintainer box daemon, zero human): download bundle → foundation
      validation → full re-score from run.original.json → POST /verification
      (accept + projection | reject + blocking_reasons — both visible states)
  → server AUTO-PUBLISHES on accept (publish_state=published, published_at set)
  → row live on site ≤60s later (live board endpoint, edge-cached)
  → upgrades, all non-blocking: coding re-exec receipt → coding verified;
      replication (phase 3); OAuth handle binding (phase 2)
  → moderation: suppress/withdraw evicts from live board within cache TTL (≤60s,
      beats the old 300s snapshot SLA); anomaly flag = outlier vs base/family delta
```

Latency budget upload→live: **~3–8 min** (validator poll ≤120s + rescore + 60s edge
cache). Degradation when the maintainer box is off: submissions sit in honest visible
states ("received — scoring queued"), drain FIFO on return. That dependency is
accepted for v1: the box is the trust anchor (re-scored > self-reported) and runs
24/7; if volume ever outgrows it, the CLI self-report card (§9) flips rows to
self-reported-first without waiting.

## 3. Server changes (Track A — web/functions)

A1. **Public live board endpoint** `GET /api/board/community.json`.
   Live D1 query — same predicate as the snapshot serve (`status='accepted' AND
   publish_state='published' AND NOT edge-blocked`) but against current rows, no
   snapshot indirection. Joins each row's projection object from R2
   (`projections/sha256/{sha}.json`), trims to the board-row contract (§6). Edge
   Cache API + `cache-control: public, max-age=0, s-maxage=60` (same pattern as the
   queue endpoint). No admin fields, no R2 keys, no internal ids beyond
   submission_id/group_id. Response is deterministic (stable ordering by
   published_at desc, submission_id asc).

A2. **Auto-publish on accept.** In `handleApplyVerificationUpdate`: when the update
   is `accepted` and `ops_settings.auto_publish='on'`, set
   `publish_state='published'` + `published_at` in the same transaction (transition
   recorded). The ZT-1 preview + daily publish-batch path is bypassed for this flow
   (batch endpoint remains but is no longer load-bearing). **Freeze-alarm
   kill-switch retained**: alarms still auto-flip `auto_publish` off, which cleanly
   reverts the system to manual publishing.

A3. **Re-verification of accepted rows.** `POST /verification` currently only
   transitions `pending_verification → accepted|rejected`. Allow re-POST on
   `accepted` rows as a **projection refresh** (same byte-pinning checks, projection
   stored create-only content-addressed as today, columns updated, transition
   `reverified` recorded, `publication_revision++`). This is how coding-receipt
   upgrades and future replication merges land without new endpoints.

A4. **Admin raw-bundle download** `GET /api/admin/submissions/{id}/bundle` —
   streams the R2 raw object to the validator daemon (admin secret). Today no
   download path exists.

A5. **Throughput caps relaxed for the automated queue**: global pending 20 → 200,
   per-submitter pending 5 → 10. Ticket rate limits (20/day/key, IP caps), 64 MiB
   size cap, PoP, and idempotency are UNCHANGED — they are abuse control, not
   review throttles. FIFO cohort gate stays; the daemon drains in FIFO order.

A6. **Display-name backfill (small)**: admin PATCH to set `submitter_display_name`
   on an existing submission (for the two maintainer tickets submitted before
   `--display-name` was used).

Tests (Miniflare vitest, existing patterns): end-to-end complete→verify→auto-publish
→appears in live board; suppression disappears from live board without any snapshot
action; rejected/hidden/preview rows never appear; cache headers; no-secret-leak
assertion on the public payload; A3 refresh bumps revision and swaps projection.

## 4. Auto-validator daemon (Track C — scripts/, maintainer box)

`scripts/auto_validator.py` (repo, not packaged; runs in the 0.4.2 venv on the
maintainer box under a scheduled task).

Loop: `GET /api/admin/submissions?status=pending_verification` → FIFO → download
bundle (A4) → `verify_submission` (existing foundation validation + full re-score;
UNCHANGED machinery) → `POST /verification` (accept with projection, or reject with
blocking_reasons) → append signed local decision log (`actor=auto-validator`).
Invalid bundles are auto-rejected with reasons — garbage never publishes, and the
rejection is visible on the status page. PID lockfile; exponential backoff on API
errors; one submission at a time; structured log file.

**Coding pass is separate and explicitly started** (`--coding-pass`): docker
re-exec with digest-pinned image + receipt signing, then A3 re-verification.
HARD GUARD: refuses to start while a GPU suite/WSL appliance run is active on the
box (checks for the bench process/lockfile) — process-exhaustion rule.

Server-side D1 decision log keeps recording auto events (actor `auto-validator`);
the maintainer's signed hash-chained local log records the same actions — the two
logs cross-check.

## 5. Site changes (Track B — web/, additive overlay)

B1. **Live overlay, not a rewrite.** The baked `public/data/community/*` path stays
   (SEO, no-JS, API-down fallback, and the publication blackbox gate stays valid
   untouched). A client component fetches `/api/board/community.json` (same-origin,
   `pending-verification-queue.tsx` pattern: useEffect + AbortController + Zod
   parse) and **reconciles by submission_id**: live wins over baked, live-only rows
   append, baked rows absent from live (suppressed) are dropped. Freshness
   indicator: "live · updated Ns ago"; on fetch failure render baked data
   unchanged. Applied to: leaderboard community section, /community listing,
   model-page family sections, community detail pages.

B2. **Submissions page** `/submissions`: public pipeline view — every ticket with
   state (received → scoring → published(tier) | rejected(reasons) | suppressed),
   from `/api/submissions/queue` + `/api/feed/accepted.json` + the live board.
   Extends the existing by-id `/submission` page; nav link + sitemap. This is the
   owner's "as the owner I can't see anything" fix, and the submitter's too.

B3. **Family spine.** `/model/<slug>` static params extend to base models that have
   ≥1 community variant (from baked lineage bases ∪ catalog); catalog-only shell
   renders without `models/<slug>.json` ("base not yet benchmarked — queued" when
   applicable). Live overlay fills variants. Known limit (documented): a family
   first seen live-only gets its page at the next site publish; until then its rows
   are on the leaderboard + /community listing.

B4. **Axis cells + badges.** Live rows carry per-axis scores (§6) — render them
   (replacing "not published in v2" blanks) with tier badge from
   `trust_label`/`verification_level`, coding chip `pending verification` for
   `not_measured/not_run` (never 0.0), agentic `self-reported` chip as today.
   Reuse `staticTrustChip`/`agenticProvenanceLabel`/`AttributionChip`.

B5. Tests: live-surface pattern (handler test + client parser test, no SSR
   assertions); existing static-markup tests stay valid because the baked path
   still renders; e2e additions for /submissions and one live-overlay smoke.
   `data-integrity.test.ts` and `LAUNCH_FREEZE` untouched — ranked bytes are
   outside this change entirely.

## 6. Contract: `localbench.community_live_board.v1`

```jsonc
{
  "schema_version": "localbench.community_live_board.v1",
  "generated_at": "<iso8601>",
  "publication_revision": 0, "edge_block_revision": 0,
  "rows": [{
    "submission_id": "ticket_<32hex>",
    "community_model_group_id": "community-group:<32hex>",
    "submitter": { "display_name": "<str|null>", "key_fingerprint": "<12hex|null>" },
    "origin": "community",
    "model": { "display_name": "", "declared_name": "", "family": "", "quant_label": "",
                "file_sha256": "<64hex>", "identity_status": "unverified|maintainer_verified",
                "model_system_key": "artifact:<64hex>" },
    "lineage": { "base_model": [] },
    "suite_release_id": "", "scorecard_id": "",
    "scores": { "partial_composite": null, "headline_score": null },
    "axes": { "<axis>": { "score": 0.0, "n": 0, "ci": null,
                           "status": "measured|not_measured|invalid" } },
    "trust": { "tier": "re-scored|self-reported", "trust_label": "community_re_scored|community_self_submitted",
                "verification_level": "bundle_rescored", "coding_state": "pending|verified",
                "agentic_provenance": "self-reported|attested", "replicated": false },
    "timestamps": { "submitted_at": "", "validated_at": "", "published_at": "" }
  }]
}
```

Derived entirely from existing D1 columns + the stored projection object; no new
storage. Site re-validates with strict Zod (reject unknown keys, bound strings —
same hardening class as `community-data.ts`).

## 7. What this removes or demotes (the simplification)

| Was (required, human) | Becomes |
|---|---|
| `submit admin-verify` per submission | optional maintainer tool (spot-checks, coding pass) — the daemon runs the same code automatically |
| `submit admin-decision` publish flip | automatic on accept (`auto_publish=on`) |
| ZT-1 preview state + daily publish-batch (1/identity/day, limit 10) | bypassed; batch endpoint dormant |
| Snapshot create→activate→export→rebake to become visible | live endpoint; snapshots remain only as the bake/fallback path |
| FIFO human review cohort | daemon drains FIFO |
| Admission caps sized for manual review (20 global) | 200 global / 10 per-submitter |

Human steps between a community upload and a visible scored row: **zero**.

## 8. What stays (invisible, cheap, load-bearing)

Three-leg presigned upload, PoP signature, byte pinning, idempotency; foundation
validation + full re-score (automated — garbage is auto-rejected with visible
reasons); 64 MiB cap and all ticket rate limits; suppression + edge blocks (now
effective ≤60s on the live board); freeze alarms as the auto-publish kill-switch;
both decision logs; the ranked frozen board, its byte pins, and the entire
`publish-board` pipeline (maintainer lane untouched); the publication blackbox gate.

## 9. Phases

- **Phase 1 (this build)**: A1–A6 + daemon + B1–B5 + migration (§10). Deploy gate:
  red-team verdict folded, full local gates green, live probe.
- **Phase 2**: GitHub OAuth on the Worker (creds staged) + CLI `localbench login`
  in 0.4.3 (pure CLI release — no appliance rebuild needed, confirmed) + handle
  binding to submitter keys. Also 0.4.3: CLI self-report card at submit (compact
  aggregates) so rows can go self-reported-first if validator latency ever matters,
  and `--display-name` defaulting.
- **Phase 3**: replication matching engine (evidence groups, tolerance vs pinned
  per-suite values, disputed state), anomaly flag v1 (site-side outlier-vs-base
  delta), spot-check lottery lite.

## 10. Migration

- Bonsai static ticket (`ticket_10c6…`) = the daemon's first customer: auto-verify →
  auto-publish → first live board row. Its full-run sibling (submitting ~Sat) becomes
  the first same-artifact replication pair.
- Qwythos row: unchanged projection, now also served live; display name backfilled
  to `local-bench` (A6) along with Bonsai's.
- Ranked five: untouched.

## 11. Risks and mitigations

- **Worker memory**: never parse raw bundles in Functions (21.6 MB real case) — the
  daemon does all heavy lifting; Functions only join small projection objects.
- **R2 join cost on cache miss**: bounded by row count; edge cache 60s; materialize
  a single live-board object on write events if row count × miss rate ever matters.
- **Baked/live divergence**: reconcile keyed on submission_id, live wins, suppressed
  drop; bake refresh happens at every site publish as today.
- **Abuse of auto-publish**: rate limits + PoP + auto-reject on validation failure +
  suppression ≤60s + freeze alarms auto-reverting to manual + attribution on every
  row. Displayed numbers are re-scored from raw records, not taken from aggregates.
- **0.4.2 compatibility**: all changes are server/daemon/site-side; existing CLIs
  gain the new behavior with zero client change.

## 12. Red-team amendments (BINDING — Sol x-high verification review, 2026-07-18)

The review verdict on §§1–11 as originally specced was NO-GO with 13 findings
(evidence in `scratchpad/redteam-ptm-sol-xhigh.log`). The spec is amended as
follows; where §§1–11 conflict with this section, this section wins.

1. **Rejection is projection-free and idempotent** (F2 — the single most
   important change). `StatusUpdateSchema` becomes a discriminated union:
   `accepted` requires the full projection + hashes; `rejected` carries ONLY
   bounded reason codes (enum, ≤24 codes + optional detail ≤300 chars) and NO
   projection fields. The daemon wraps its entire verify path in a catch-all:
   any load/validation/rescore exception → terminal `rejected` POST with a
   mapped reason code. Re-POST of an identical rejection is a 200 no-op.
   The server/documentation enum is `bundle_unreadable`, `manifest_invalid`,
   `schema_violation`, `suite_mismatch`, `identity_mismatch`, `rescore_failed`,
   `item_count_mismatch`, `sampler_violation`, `signature_invalid`,
   `size_violation`, `internal_error`, plus `metadata_unsafe` for the dedicated
   ZT-1 metadata-safety mapping in amendment 4.
2. **Ingest budgets** (F1): community-model-group creation moves behind the same
   PoP + rate-limit envelope as ticket issuance (group row created only after
   checks pass; the standalone endpoint gains per-IP 10/day + PoP requirement or
   is folded into the ticket flow). `/complete` failures after upload (caps,
   mismatch) DELETE the R2 object. GC deletes raw R2 objects for `expired` and
   `rejected` rows past a 7-day retention. Daily global upload-byte budget
   (8 GiB) enforced at request-upload.
3. **Freeze alarms rebased for the automated lane** (F3): replace
   `pending_gt_20 / submissions_gt_50_day / accepts_gt_10_day` with:
   oldest-pending age > 6 h; rejects_24h ≥ 20 AND reject-rate > 50 %;
   upload bytes_24h > 8 GiB; accepts_24h > 200. Alarm semantics unchanged
   (auto-flip `auto_publish` off → system reverts to manual). Alarms are
   evaluated IN the verification handler before the publish step (prospective:
   the row being accepted counts), plus on every daemon cycle via the digest
   endpoint. Any alarm blocks the publish step of that request.
4. **ZT-1 is retained and remapped, not bypassed** (F4): the ZT-1 evaluation
   still runs on every accept and still populates its columns. Outcome mapping
   under publish-then-moderate: `publishable` → publish immediately (preview +
   daily batch skipped); escalation reasons split — `duplicate_artifact` and
   `protected_identity` remain HARD holds (stay hidden, visible state "held for
   review", maintainer resolves); `unsafe_metadata` → auto-reject with reason
   code; the community self-reported-coding escalation trigger is REMOVED
   (coding renders as `pending verification` instead — §1 tier chips).
   Duplicate detection stays a hard integrity gate. Existing `preview` /
   provisional rows are migrated (publishable+non-escalated → published) in a
   one-time admin migration step executed at deploy.
5. **Suppression SLA stated honestly + auto-rebake** (F5): live surfaces (JS
   clients) drop suppressed rows ≤60 s. Static baked HTML shows them until the
   next deploy — same as today, NOT a regression. The suppression runbook/script
   chains an immediate rebake+deploy; SLA documented as "≤60 s live surfaces,
   next deploy (minutes, operator-chained) for static HTML". Baked fallback
   rendering is retained (availability > the no-JS stale window).
6. **Live board = materialized object, not read-time fan-out** (F12, and
   simplifies F6): on every publish / suppress / withdraw / refresh event the
   Worker rebuilds ONE canonical object `board/community-live.json` in R2
   (build: full snapshot-eligibility predicate — `origin='community'`,
   `status='accepted'`, `publish_state='published'`, projection + group non-null,
   `zt1_decision <> 'escalated'`, not edge-blocked — then per-row strict parse
   of the projection; invalid/missing rows are OMITTED and counted in
   `omitted_rows`, never a build failure). The public endpoint serves that
   object: fixed query-free cache key, unknown query params → 400, edge cache
   60 s, miss rate-limit like the queue endpoint, payload cap (≤500 rows).
   An admin rebuild endpoint exists for recovery.
7. **Refresh protocol** (F7): verification POST gains explicit
   `operation: "initial_decision" | "projection_refresh"`. Refresh requires
   `expected_state_revision`, `previous_projection_object_sha256`, and a
   strictly newer `validated_at`; mismatch → 409; identical re-POST → 200 no-op
   without revision bump; transition `reverified` recorded. Initial decisions on
   already-accepted rows → 409 (no silent refresh).
8. **Contract v1 completed + per-field reconcile** (F8): the §6 contract
   additionally carries `group_path`, `coverage_profile_id`, `index_version`,
   `headline_complete`, the FULL `scores` object as stored (composite fields,
   weights, scopes), `conformance`, `receipt_references`, `rescore_modes`,
   `provenance_notes`, and `lineage_enrichment` (see next). Site reconcile is
   PER-FIELD, not row-replace: live wins for scores/axes/trust/timestamps/
   publish-state; **baked maintainer-reviewed `lineage_enrichment` wins over
   live declared lineage** when present (the overlay is reviewed evidence; the
   projection's `base_model` is empty today). Family association uses the merged
   lineage. Trust-label mapping table: `community_re_scored → re-scored`,
   `community_self_submitted → self-reported`, `project_anchor → maintainer-run`;
   agentic provenance underscore values mapped to hyphenated UI labels.
9. **Live-only detail links suppressed until next deploy** (F9): rows for groups
   absent from the baked index render WITHOUT a detail link (tooltip: "detail
   page publishes with the next site deploy"); `/submission?id=` remains the
   per-submission live view. No query-string shell in phase 1.
10. **String bounds are a shared spec** (F10): server projection validation AND
    client Zod enforce identical bounds — display/declared name ≤120,
    display_name (submitter) ≤80, family ≤64, quant_label ≤32, repo/lineage ids
    ≤140, axis keys ≤40, axes ≤16, lineage entries ≤8, reason detail ≤300; all
    strings reject C0/C1 controls + bidi controls (same class as
    `community-data.ts` hardening). Client parses PER ROW: an invalid row is
    dropped + counted, never the whole board. A6 display-name backfill uses the
    same schema.
11. **Validator credential + intent log** (F11): new secret
    `VALIDATOR_API_SECRET` (header `x-localbench-validator-secret`) accepted
    ONLY on: admin submissions list (read), bundle download (read), verification
    POST. All other admin routes remain admin-secret-only. Transition actor
    recorded as `auto-validator` when the validator secret authenticated the
    request. The daemon writes a local intent record before each POST and an
    outcome record after; on startup it reconciles dangling intents against
    server state before processing anything new.
12. **Public lifecycle listing** (F13): new paginated public endpoint
    `GET /api/submissions/list?cursor=` — sanitized lifecycle view of ALL
    submissions (id, declared slug, display name, state, bounded reason codes
    for rejected, timestamps; cursor pagination, ≤50/page; no capability or
    internal fields). `/submissions` consumes it (plus the live board for tier
    badges) instead of stitching queue+feed.
13. **Disclosure delta acknowledged** (F6): the live payload exposes submitter
    key fingerprint, exact timestamps, scorecard id, trust state, per-axis n/CI —
    deliberate under attribution-as-trust; documented on the methodology page in
    Track B.
