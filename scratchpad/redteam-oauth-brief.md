# Verification brief: GitHub OAuth account-binding slice (branch ptm/track-d)

You are an independent security reviewer verifying the OAuth/attribution changes in
THIS worktree (diff = 9d21688..HEAD, commits c8a151e/80b8d47/043a762). Read the code;
cite file:line evidence for every finding. Do not trust the build report.

Files of interest: web/functions/_lib/github-oauth-*.ts, the four routes under
web/functions/api/auth/github/, migration web/migrations/0015_accounts.sql, and the
attribution plumbing in submission-ticket-api.ts / community-live-board.ts /
submission-lifecycle-api.ts. Tests under web/tests/github-oauth-*.

## Invariants to verify (the workorder's security contract)

1. GitHub access tokens: used only for the immediate /user fetch, NEVER persisted
   (D1, R2, logs, error messages, responses). Prove it — trace every place the token
   value flows.
2. Raw GitHub device_code never leaves the server: external surface sees only the
   opaque handle; handle is single-use (atomic claim — verify the claim is actually
   race-safe in D1 semantics), TTL-bounded, unguessable (entropy source?).
3. Key binding requires a valid Ed25519 PoP over
   `localbench.account_bind.v1\n{github_user_id}\n{timestamp}` with 10-min freshness,
   verified against the SUBMITTED public key: can a poll request bind someone ELSE's
   key (PoP replay, key substitution, signature-over-different-uid)? Can an attacker
   bind their key to a victim's GitHub account or vice versa?
4. Web callback: state parameter single-use + verified; open-redirect impossible;
   response is inert HTML (no reflected input, no script injection via login/name
   fields); no cookies/sessions set.
5. Feature flag: with GITHUB_OAUTH_ENABLED unset, every new endpoint is inert (503,
   no D1 writes, no GitHub calls); flag off does not degrade any existing endpoint.
6. Attribution: github_login stamped on submissions only from a bound key (no
   spoofing via request fields); live-board/lifecycle payloads bound + sanitized
   (login format bounded — GitHub logins are [A-Za-z0-9-]{1,39} — enforced?); legacy
   rows (null) render safely.
7. Migration 0015: additive only; the migration-absent fallback cannot be used to
   bypass attribution or crash handlers; no FK cascade that could delete submissions.
8. Rate limits on all three flows effective per the workorder (10/60/30 per IP/hr).
9. Anything else that would embarrass us: SSRF via GitHub URLs (are hosts
   hardcoded?), timing oracles on handle lookup, account takeover on github_user_id
   reuse after revocation, log leakage of secrets.

## Deliverable

Verdict first: GO / GO-WITH-CHANGES / NO-GO for deploying this slice feature-flagged
OFF, and separately for eventually flipping the flag ON. Then numbered findings,
most severe first, each: CONFIRMED (file:line) or PLAUSIBLE, concrete attack
scenario, minimal fix. End with the single most important change.
