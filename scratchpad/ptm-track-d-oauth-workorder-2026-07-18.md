# Track D workorder: GitHub OAuth accounts + attribution (server-side, feature-flagged)

Design context: docs/foundations/unified-board-attribution-design-2026-07-18.md §2
(account mechanism A1 = GitHub OAuth, owner-picked) + §12. Goal: submitter identity
becomes a GitHub handle bound to their existing Ed25519 submitter key. Server-side
lands NOW feature-flagged; the CLI `localbench login` command ships in 0.4.3 — nothing
in this track may break 0.4.2 submitters (who remain key+display-name attributed).

Repo: this repo, branch `ptm/track-d`. Work under `web/functions/`, `web/migrations/`,
`web/tests/`, small site chip in `web/components/` + `web/lib/`.

## GitHub app facts (already created)

- client_id: `Ov23liGbCyw1WtlJ0jmj` (public, may be committed)
- Client secret: NEVER in the repo — read from env `GITHUB_OAUTH_CLIENT_SECRET`
  (set via wrangler at deploy; add the name to `SubmissionApiEnv`).
- Callback URL registered: `https://local-bench.ai/api/auth/github/callback`
- Device flow: ENABLED.
- Feature flag: env `GITHUB_OAUTH_ENABLED` — when not `"on"`, every new endpoint
  returns 404-shaped `{code:"oauth_disabled"}` with 503. All tests cover both states.

## Deliverables

1. **Migration `web/migrations/0015_accounts.sql`** (append-only, new file):
   `accounts` (account_id pk `acct_<32hex>`, github_user_id UNIQUE, github_login,
   created_at, revoked_at NULL) and `account_keys` (public_key_hex pk, account_id fk,
   bound_at, binding_signature) — one account per GitHub user, many keys per account.
2. **Device flow endpoints** (for the 0.4.3 CLI):
   - `POST /api/auth/github/device/start` → proxies GitHub device-code request
     (client_id only), returns `{device_code_handle, user_code, verification_uri,
     interval, expires_in}`. The raw GitHub `device_code` NEVER leaves the server:
     store it in D1 keyed by an opaque `device_code_handle` (single-use, TTL).
   - `POST /api/auth/github/device/poll` `{device_code_handle, public_key, pop}` →
     polls GitHub's token endpoint server-side; on success fetches the GitHub user
     (id+login), upserts the account, binds `public_key` to it. The `pop` is an
     Ed25519 signature over `localbench.account_bind.v1\n{github_user_id}\n{timestamp}`
     verified against `public_key` (10-min freshness) — proves the CLI holds the key
     it is binding. GitHub access tokens are used ONCE to fetch the user and are
     NEVER stored.
3. **Web callback** `GET /api/auth/github/callback` — minimal: exchanges code,
   fetches user, then renders a static HTML page instructing the user to finish
   binding from the CLI (`localbench login`). No cookies, no sessions — the site has
   no logged-in state in this phase. (state param: require + verify a `state` issued
   by `GET /api/auth/github/start` redirect helper stored single-use in D1.)
4. **Attribution plumbing**: ticket issuance (`submission-ticket-api.ts`) resolves
   `account_id` + `github_login` from `account_keys` by the submitting public_key and
   stamps them on the submission row (nullable columns via migration 0015:
   `account_id`, `github_login` on `submissions`). The live board builder
   (`community-live-board.ts`) adds `submitter.github_login` (nullable) to the row
   payload — additive optional field, client schema tolerant.
5. **Site chip**: where submitter display name renders (community rows/lifecycle),
   if `github_login` present show it as the primary label (plain text, bounded ≤40,
   same unsafe-char rules; display_name becomes secondary). NO link in this slice
   (link target debate deferred).
6. **Rate limits**: device/start 10/IP/hr, device/poll 60/IP/hr, callback 30/IP/hr
   (existing `rate_counters` helper).

## Tests (Miniflare vitest, mock GitHub with an injectable fetch)

Both flag states; device flow happy path (handle opacity — raw device_code absent
from every response body); poll with bad PoP → 401; expired handle → 410; account
upsert idempotency (same github_user_id twice = one account, second key binds to
same account); token never persisted (assert D1 tables + R2 contain no `gho_`/
`ghu_` strings after flow); ticket stamping (bound key → account_id+login on row;
unbound key → nulls); live board carries github_login when present; rate limits;
callback state verification (missing/reused state → 400).

## Hard constraints

- Secrets only via env; never logged; no tokens at rest. No cookies/sessions.
- 0.4.2 submit flow untouched and green (existing submission tests all pass).
- Never-touch list as always (board data, launch-freeze, data-integrity, blackbox).
- `npm run test`, `npm run typecheck`, `npm run build` green in `web/`.
- Small conventional commits; no push. Report to
  `scratchpad/build-ptm-track-d-report.md` (commits, files, exact test counts,
  deviations, incomplete).
