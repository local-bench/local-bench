# Submission #0 canary — findings (2026-07-01)

Dogfooded the live (private-gated) submission path end-to-end with the calibration pilot bundle,
as user #0. Found and fixed one backend bug; found and precisely isolated a second. This is exactly
the pre-flight value a #0 canary is meant to deliver.

## Bug 1 — remote D1 `submissions` schema was stale (FIXED)
- **Symptom:** `POST /api/submissions/tickets` → 500 (after gate + admin auth passed).
- **Root cause:** remote D1 `localbench_prod` had the OLD `0001` `submissions` schema
  (`public_key/server_nonce/r2_key/bundle_sha256/...`), while the current
  `insertTicketedSubmission` writes the NEW schema
  (`origin/submitter_id/ticket_id/raw_bundle_sha256/raw_bundle_r2_key/suite_release_id/
  suite_manifest_sha256/idempotency_key/bundle_schema_version`). Migration `0002` (the new schema)
  was **unapplied on remote**, and its `create table if not exists submissions` cannot migrate over
  the existing `0001` table — worse, `0002`'s `create index … on submissions(publish_state)` would
  *fail* against the old table (no such column). So `migrations apply` alone could not fix it.
- **Fix (remote, empty table `n=0`, pre-launch):** `DROP TABLE submissions` →
  `wrangler d1 migrations apply localbench_prod --remote` (applies `0002`, wrangler auto-confirms in
  non-interactive mode) → new `submissions` + `board_entries` + indexes created. Verified schema.
- **After fix:** `submit ticket` → **201** ✓ (`ticket_f9a28f16…`); `request-upload` + R2 PUT ✓
  (object present in `localbench-submissions`).
- **LATENT (fresh-DB) bug remains:** `0001` creates the old `submissions`, `0002`'s `if not exists`
  won't override it → any *fresh* `migrations apply` from scratch is broken. **Proper fix:** make
  `0002` drop-first, or add a reconciling `0003`. Remote is fixed; a from-scratch rebuild is not.

## Bug 2 — `complete`/finalize throws an uncaught SyntaxError (OPEN — needs local repro)
- **Symptom:** `POST /api/submissions/{ticket_id}/complete` → **500**. Cloudflare `pages deployment
  tail` captured:
  `SyntaxError: Expected property name or '}' in JSON at position 1`, `outcome: "exception"`,
  `at async handleFinalizeSubmission (functionsWorker…js:14540:50)`.
- **Isolation (all reproduced on the live deployment `f260bf31`, commit `2e4ca56`):**
  - body `{}` → handled **400** `invalid_complete_request` ⇒ `await request.json()` works fine.
  - body with a **non-matching** sha → handled **409** `bundle_sha_mismatch`.
  - body with the **matching** sha (79 KB well-formed bundle) → **500**. So the throw is strictly in
    the `readRawBundle → parseJson → ResultBundleSchema.safeParse → markPendingVerification` region.
  - The 79 KB bundle has every required field: `serving_mode`, `tier`,
    `manifest.suite.{suite_release_id, suite_manifest_sha256, coverage_profile_id}`. A failed
    `ResultBundleSchema.safeParse` returns a *handled* 400, so that isn't it either.
- **Why it's subtle:** `web/functions` contains **exactly one `JSON.parse`** — `parseJson`, which is
  `try/catch`-guarded (returns `null` on `SyntaxError`). Deployed == local. The middleware never
  reads the body. So the uncaught `SyntaxError` does not correspond to any *visible* unguarded parse
  → likely a bundler inlining artifact, a dependency call, or a runtime interaction (e.g. something
  in the R2 read/`object.text()` path or a D1 driver path). **Needs `wrangler pages dev` with source
  maps** to resolve `functionsWorker…js:14540:50` to a real source line. Do NOT blind-fix + redeploy.
- **Repro handle:** ticket `ticket_812bdbf38343494b9fdeef70b2553a3d`, sha
  `657a88ec585417e19fba8be0d7ed115fc02e6d12c8745846b2778e6087d7591d`, object present in R2.
  Local repro bundle: `scratchpad/canary/small-bundle.json` (79 KB) / `pilot-bundle.json` (19 MB).
- **Impact:** blocks submission **finalization** for ALL bundles ⇒ the submit leg (this canary AND
  the eventual first Gemma-12B run) cannot complete until fixed. Ticket + upload legs work.

### Bug 2 — Codex fix attempt (2026-07-01, STAGED uncommitted, NOT redeployed)
Codex (job `task-mr1yuy9e`) wrapped the finalize path in try/catch: `await request.json()` → 400 on
SyntaxError; the matched-sha `readRawBundle→parseJson→safeParse→markPendingVerification` region →
**500 `submission_finalize_failed`** on SyntaxError; + a cross-realm `isSyntaxError` helper; + a
regression test. web/ only, `board_v1` frozen, 99 web tests pass, typecheck + build pass.
- **Claude review verdict: DEFENSIVE HARDENING, not a confirmed root-cause fix.** Codex's regression
  test **simulates** a D1 `.run()` SyntaxError via a mock (`options.runErrorMessage`) — it did NOT
  reproduce the ACTUAL cause. So this converts the uncaught Worker crash into a structured error, but
  the submission likely still won't *finalize* (would return a clean 500 instead of 200
  `pending_verification`), and the caught error is **swallowed** (no logging) — impeding diagnosis.
- **Root cause still unconfirmed.** Live error = `SyntaxError: Expected property name or '}' at
  position 1` from the finalize region; source has no unguarded `JSON.parse`. Leading hypothesis: the
  D1 `.run()` on the `markPendingVerification` UPDATE receives a non-JSON error response from the D1
  service (i.e. the UPDATE is failing server-side for an unknown reason) and the D1 client's internal
  `JSON.parse` throws. Needs live confirmation.
- **Recommended next (deliberate, not blind-night):** (1) add `console.error(error)` in the finalize
  catch so `pages deployment tail` shows the real D1 error; (2) redeploy the private site; (3) re-run
  `launch-smoke.ps1 -ExpectedMode Private` (gate must hold); (4) re-run the canary `complete`
  (`ticket_812bdbf3…`, sha `657a88ec`) — 200 `pending_verification` = fixed; 500
  `submission_finalize_failed` = read tail for the real D1 error + fix the UPDATE. Keep Codex's
  hardening regardless (it is a correct improvement). Staged in the worktree for Michael's review.

## State / guardrails respected
- `board_v1.json` untouched (frozen). No `web/` code change, no redeploy. Only remote D1 changed
  (the migration fix). Everything else left as-is for review.
- Recommended next: reproduce Bug 2 under `wrangler pages dev` to get the real line, fix + redeploy
  (private site, low risk), re-run `launch-smoke.ps1 -ExpectedMode Private` (gate must hold), then
  re-run the canary `complete` → expect 200 `pending_verification`, then `admin-verify` → expect
  `rejected` with the 5 known publish blockers. Also land the latent-migration fix (Bug 1 tail).
