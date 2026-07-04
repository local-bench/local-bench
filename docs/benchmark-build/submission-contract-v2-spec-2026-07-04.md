# Submission Contract v2 — signed, origin-aware (launch security contract)

Date: 2026-07-04. Status: FROZEN (GPT-5.5 Pro red-team adopted; owner directive:
frictionless public benchmarker loop is launch-gating). This document is the contract of
record; Wave 1 implements the SERVER portion. Waves 2 (rescorer/attestations, Python) and
3 (CLI one-command submit) build against this same contract and MUST NOT be started in
Wave 1.

Branch: `codex/local-bench-online-backend`. Integrity pin: `cli/runs/board/board_v1.json`
must still `git hash-object` to `3d058e6074bd781cc488c03255904b5f9599e37e` when the wave
ends (do not touch it).

## 0. Threat model recap (why each rule exists)

Public ticket/upload routes are about to open to anonymous submitters identified only by
ed25519 pubkeys. The board's credibility claim is deterministic server-side re-scoring of
signed bundles. The contract must make these forgeries structurally impossible, not
review-dependent:

- T1 fabricated agentic (dynamic) verdicts riding the verdict-carry rescore path
  (50%-weighted axis, survives deterministic rescoring if not blocked).
- T2 client-supplied trust fields (origin, scores, rank scope, composite) leaking into
  projections or the board.
- T3 identity spoofing / ticket squatting (free-text submitter_id, unproven pubkeys,
  pre-registering someone else's bundle sha).
- T4 replay/duplicate inflation (same run re-signed under new keys posing as independent
  replications).
- T5 storage/CPU abuse (oversized uploads, unbounded ticket minting, worker OOM on read).

## 1. Envelope v2

- `SUBMISSION_ENVELOPE_SCHEMA_VERSION = "localbench.submission_envelope.v2"`.
- `origin: "project_anchor" | "community"` — derived SERVER-SIDE only:
  request passed `adminBlocked` check with valid `x-localbench-admin-secret` →
  `project_anchor`; otherwise `community`. `origin` is NEVER read from the request body
  (reject any body that includes it: `invalid_ticket_request`).
- D1 insert binds `ticket.origin` (replaces the hardcoded `"project_anchor"` literal in
  `insertTicketedSubmission`).
- Envelope gains `expires_at` (ISO, now+1h) — replaces decorative `expiry`; keep `expiry`
  emitted as an alias for one version for our own tooling, marked deprecated in the type.

## 2. Public ticket route (`POST /api/submissions/tickets`)

Community (no/invalid admin header) requirements — all hard-rejected with typed codes:

- `accepted_suite_terms: true` (exists).
- `public_key` (64-hex ed25519) REQUIRED; free-text `submitter_id` is REMOVED from the
  public schema (admin path may still pass it). `submitter_id` is derived server-side as
  `public_key:<hex>`.
- `expected_suite_release_id` + `expected_suite_manifest_sha256` REQUIRED (no defaulting
  for community) and the pair MUST match a registered release in the suite catalog →
  else `unknown_suite_release`. Extend each suite-catalog record with
  `static_benches: readonly string[]` (the benches with static item sources in that
  release; for `suite-v1-text-code-agentic-5axis-v1`: mmlu_pro, ifbench, tc_json_v1, lcb)
  so the worker can enforce §5 without reading suite files.
- `max_upload_bytes` REMOVED from the public schema; server-fixed cap (§6). Admin path
  may still override downward.
- **Proof-of-possession (PoP)**: request carries
  `pop: { timestamp: string (ISO8601), signature: string (128-hex ed25519) }` where the
  signature is over the UTF-8 canonical string:
  `localbench.ticket_pop.v1\n<bundle_sha256>\n<expected_suite_release_id>\n<expected_suite_manifest_sha256>\n<timestamp>`
  verified in the worker (WebCrypto Ed25519) against `public_key`. Reject when: bad
  signature (`pop_invalid`), |now − timestamp| > 10 min (`pop_stale`). Replay within the
  window is inert: the ticket row is keyed by bundle sha (§3), so a replayed request just
  rotates the same submitter's own ticket.
- Admin path (valid admin secret): PoP optional, pair optional (defaults apply), origin
  `project_anchor`, free-text submitter_id allowed. Our existing tooling keeps working.

## 3. Ticket idempotency (replaces silent no-insert)

On mint for `bundle_sha256` with existing row:

- existing.status == 'ticketed' AND uploaded_at IS NULL AND same submitter (same derived
  submitter_id) → ROTATE: update ticket_id + expires_at, return the persisted envelope
  (200). One live ticket per bundle.
- otherwise → `409 { code: "bundle_already_submitted", status: <existing.status>,
  submission_id }` (no envelope).
- No existing row → insert + 201 (current behavior).
- D1: unique index on `raw_bundle_sha256`; unique index on `ticket_id` (verify against
  existing migrations; add if missing).
- **Rotation lookup consistency (AS-BUILT model, reviewed and accepted 2026-07-04)**:
  the implementation resolves this differently from the original clause — `submission_id`
  and `ticket_id` move in LOCKSTEP on rotation (both become the new ticket id, updated in
  place on the same row). Consequences, all verified: the upload leg's submission-id
  lookup keeps working after any number of re-mints; the stale pre-rotation id dies
  (404 at request-upload — one live ticket per bundle); the identifier is mutable ONLY
  in the owner-only pre-upload window and immutable from upload onward (duplicate_of,
  projections, and publish flows only ever reference post-upload rows). This is simpler
  than the dual-identifier model (no second lookup path, no envelope change) and
  satisfies the invariant that motivated the clause. Pinned by contract test:
  rotate → request-upload with the NEW ticket_id succeeds; with the OLD ticket_id → 404.

## 4. Expiry enforcement (S2)

- New `expires_at` column. `request-upload` and `complete` reject rows where
  status=='ticketed' AND expires_at < now → `410 { code: "ticket_expired" }` (client
  remedy: re-mint, which rotates).
- Legacy rows with NULL expires_at are treated as valid (grandfathered; none are pending).

## 5. Community dynamic-item rejection (T1 — the launch blocker)

At `complete` (after schema parse, before markPendingVerification): when
row.origin == 'community', every `item.bench` in the bundle MUST be in the ticket
release's `static_benches` → else
`422 { code: "dynamic_items_not_accepted", benches: [<offenders>] }`. REJECT, never
strip (silent stripping hides the rule). Defense in depth: the Wave-2 rescorer enforces
the same rule origin-aware; Wave 1 only needs the server gate.

## 6. Upload size + read safety (T5, S4)

- `MAX_UPLOAD_BYTES` becomes a server constant sized from the real anchor bundle: measure
  `runs/bench/ranked-5axis-capped-2026-07-03/localbench-run.json` and set the constant to
  the next power-of-two ≥ 3× that size (expected 32 MiB; record the measured size in the
  AS-BUILT section).
- At `complete`: check the R2 object's stored size (R2 get returns object metadata /
  use head) BEFORE reading the body; oversize → `413 { code: "bundle_too_large" }`.
  Keep the zod `size_bytes` cap as belt.

## 7. Complete-route correctness (S5 + key binding + payload hash)

- Idempotent early-return fires ONLY when `existing.submission_id ===
  params.submissionId` (currently returns any sha-matching row for any id in the path).
- **Key binding (T3)**: locate the submitter public key embedded in the signed bundle
  (see `cli/src/localbench/submissions/` pack/signing code for the exact field path) and
  reject at complete when it differs from the ticket's public_key →
  `409 { code: "key_mismatch" }`. Admin/project_anchor rows: enforce when the ticket has
  a public_key-form submitter_id, else skip (legacy).
- **Canonical payload hash (T4)**: compute `run_payload_sha256` server-side = sha256 of a
  canonical JSON serialization (sorted keys, no whitespace — match the canonicalization
  already used by the CLI's canonical-json if one exists; document the exact algorithm)
  of the parsed bundle AFTER deleting the signature/envelope fields (locate exact field
  names in the CLI pack code; document the final exclusion list in AS-BUILT). Store it;
  index it. If another row already has the same payload hash → set `duplicate_of =
  <original submission_id>` on the new row (status proceeds normally, but Wave-2
  projection + publish tooling treat duplicate_of≠NULL as publish-blocked-by-default and
  NEVER as replication).

## 8. Rate limits (T5) — D1 counters as source of truth, WAF as belt

- `rate_counters(bucket_key TEXT PRIMARY KEY, window_start TEXT NOT NULL, count INTEGER
  NOT NULL)` with fixed windows; helper `rateLimited(env, key, limit, windowSeconds)`.
- Launch limits (constants, tuneable): tickets per pubkey 10/day; tickets per IP 30/hour
  (CF-Connecting-IP); request-upload per IP 60/hour; pending_verification concurrency
  per pubkey ≤ 2 (counted via SQL, not a counter row). Exceed → `429 { code:
  "rate_limited", retry_after_seconds }`. Structured-log every 429 and every typed
  rejection (code + origin + truncated ids; NEVER log secrets).
- Cloudflare WAF zone rules are an ops step (documented in §11 ops notes), not code.

## 9. Status/public shape

- `publicSubmission` drops `raw_bundle_r2_key`; adds `publish_state` (already),
  `duplicate_of`, `expires_at` (ticketed rows), and `status_reason` when status is
  rejected (safe text only — no internal paths).

## 10. Flip the defaults (safe now that community requires an explicit pair)

- `DEFAULT_SUITE_RELEASE_ID = "suite-v1-text-code-agentic-5axis-v1"`,
  `DEFAULT_SUITE_MANIFEST_SHA256 = "5a47282a55621cbb9be4b719c1f9bba2f740d7720ef594fa00e794355cc420f9"`.
  (Defaults now reach only the admin path.) Update tests that pin the old default.

## 11. Migration + ops notes

- New migration `web/migrations/` following existing naming: add `expires_at`,
  `run_payload_sha256`, `duplicate_of` columns; `rate_counters` table; unique/lookup
  indexes per §3/§7. Must apply cleanly to a DB that already has rows (backfill: none
  required; origin column already holds 'project_anchor' for existing rows).
- Ops (document at the END of this file in AS-BUILT, do not execute): R2 lifecycle rule
  expiring `pending/`-prefixed objects after 14 days; suggested WAF rate rules; Turnstile
  stays OFF behind `TURNSTILE_ENABLED` env check that is read but only ever short-circuits
  (prewire, no widget work).
- R2 key prefixes (`pending/`, `accepted/`, `rejected/`) may be deferred to Wave 2 if the
  move-on-decision touch is large; if deferred, say so in AS-BUILT.

## 12. Contract tests (vitest, alongside existing web tests — REQUIRED)

Matrix, each a named test: community ticket without pair → rejected; unregistered pair →
rejected; body-supplied origin → rejected; missing/invalid/stale PoP → pop_* codes;
free-text submitter_id on public path → rejected; admin path unchanged (mints
project_anchor, defaults apply); rotate-vs-409 matrix (§3); expired ticket → 410 at both
request-upload and complete; oversize → 413 pre-read; zip/binary body → invalid bundle;
community bundle containing `appworld_c` (or any non-static bench) items → 422
dynamic_items_not_accepted; key_mismatch at complete; S5 cross-id probe returns 404/409
not another row; duplicate payload under a second key → duplicate_of set; rate-limit 429
after N mints. Plus: existing test suites stay green; typecheck green.

## 13. Non-goals for Wave 1 (do NOT touch)

- No CLI (`cli/`) changes. No Python rescorer changes. No attestation work (Wave 2 will
  add project-signed per-verdict attestations for anchor dynamic verdicts, applying from
  this contract version FORWARD — the already-accepted ranked row is grandfathered under
  validator v1 rules by design). No site copy (`web/app/`). No Turnstile widget. No
  auto-submit. No board data regeneration.

## 14. Suite-catalog hash split + fetch-suite unbreak (live-verified 2026-07-04)

Live probe finding: `localbench fetch-suite --site <site> --suite <id>` FAILS for all three
catalog suites. Two root causes, both server-side fixable in this wave:

- The catalog's `suiteHash` for the two `suite-v1-*` releases carries the release-manifest
  canonical hash (e.g. 5-axis `5a47282a…`), but the legacy `GET /api/suites/{id}/manifest`
  schema's `suite_hash` is compared by the CLI against its executable DIR-hash
  (`suite_verify.suite_hash`). Verified dir-hashes: 5-axis `de25c8064f2342ef1f59a6a99065f7fe8dd17b389a899f0db3ce197f64f3fbf3`,
  4-axis `bf463bf8…` (compute and confirm), core-text `6b7b80de…` (already dir-type, correct).
  FIX: split the fields on the catalog record — `suiteHash` = DIR-hash (what the legacy
  manifest route serves as `suite_hash`), new `suiteManifestSha256` = release-manifest
  canonical hash. §2's registered-pair check validates community tickets against
  `suiteManifestSha256`. Correct the two suite-v1 records' values accordingly.
- `core-text-v1`'s catalog `files` list (11 entries) omits 4 `LICENSES/*` files that its
  own SHA256SUMS (14 entries) requires → CLI fails with `missing hashed file`. FIX: add
  the 4 entries (hashes from the deployed static files / local `web/public/suites/core-text-v1/`).

Acceptance for this section: `uv run localbench fetch-suite --site <local dev server or
wrangler pages dev> --suite <id> --accept-suite-terms` succeeds for all three suites
WITHOUT CLI changes (run the CLI read-only as the test client), or where a live server is
impractical in tests, unit-test that the manifest route now serves dir-hashes equal to
freshly computed `suite_verify.suite_hash` values over `web/public/suites/<id>/` and that
the files lists are supersets of each suite's SHA256SUMS entries.

## AS-BUILT (Wave 1 implementer fills this in)

- Measured anchor bundle size: 20,219,268 bytes for `runs/bench/ranked-5axis-capped-2026-07-03/localbench-run.json`.
- Final MAX_UPLOAD_BYTES: 67,108,864 bytes (64 MiB), the next power of two above 3x the measured anchor bundle.
- Bundle signature/envelope field names + payload-hash exclusion list: key binding reads `signature.public_key` from the uploaded JSON bundle when the ticket submitter is `public_key:<hex>`; the server-issued envelope is `localbench.submission_envelope.v2` with `expires_at` and deprecated alias `expiry`; `run_payload_sha256` excludes top-level `signature`, `envelope`, and `submission_envelope`.
- Canonicalization algorithm used for run_payload_sha256: recursively normalize JSON values by sorting object keys lexicographically, preserving array order, omitting `undefined`, rejecting non-finite numbers/non-JSON values, serializing with `JSON.stringify` and no whitespace, then SHA-256 hashing the UTF-8 bytes. This matches the CLI canonical JSON shape (`sort_keys=True`, compact separators, `ensure_ascii=False`, `allow_nan=False`) for JSON payloads.
- R2 prefix scoping: deferred. Wave 1 retains the existing `submissions/raw/<sha>.json` upload key; `pending/`, `accepted/`, and `rejected/` move-on-decision prefixes remain Wave 2 work.
- Migration filename: `web/migrations/0004_submission_contract_v2.sql`.
- Ops steps for owner (R2 lifecycle, WAF rules): add an R2 lifecycle rule to expire future `pending/` objects after 14 days; add WAF belt-and-suspenders limits matching server constants (tickets per public key 10/day, tickets per IP 30/hour, request-upload per IP 60/hour); keep Turnstile off unless `TURNSTILE_ENABLED` is intentionally set, which currently short-circuits instead of serving a widget.
- Deviations from spec (each with one-line reason): upload payload remains the existing JSON `result_bundle_v1` object in Wave 1, not a full CLI zip/archive, because the current server route and Wave 1 tests operate on raw result bundles; full archive handling and signature verification remain Wave 2/3. R2 prefix scoping is deferred as allowed by section 11. The cap is 64 MiB rather than the expected 32 MiB because the measured anchor bundle is 20.2 MiB and the frozen formula requires the next power of two above 3x size. Rotation uses the lockstep submission_id==ticket_id model rather than §3's original dual-identifier clause (reviewed and accepted; §3 amended; seam pinned by test).

Manager review addenda (2026-07-04, accepted-for-launch with follow-ups):
- N2: the ticket route's IP rate limiter runs AFTER PoP verification, so invalid-PoP spray
  is not metered by our counters (each request still costs only a JSON parse + one Ed25519
  verify; the WAF belt rules cover volumetric abuse). Follow-up: move the IP check ahead
  of PoP in a later wave.
- N3: `rate_counters` rows are never swept (unbounded growth across unique IPs/keys).
  Follow-up: periodic delete of stale windows (cron or lazy delete-on-roll).
- Ops reminder: applying migration 0004 to PROD rebuilds the submissions table
  (data-preserving insert-select). Take a `wrangler d1 export` backup first and verify the
  accepted ranked row (ticket_790a73b6…) survives with identical fields.
