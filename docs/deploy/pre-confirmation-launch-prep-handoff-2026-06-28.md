> **SUPERSEDED 2026-06-29** by `docs/deploy/launch-prep-handoff-2026-06-29.md` (and
> `docs/deploy/live-state.md` once created). The "Current production facts" / "Observed live
> checks" / "Expected health payload" below are **STALE** — they describe the pre-private-mode
> public deployment and expect HTTP 200. The site is now **PRIVATE**: public endpoints return
> **503** (`no-store` + `noindex`). Do not write smoke checks against the 200 expectation here.

# Pre-confirmation launch prep handoff - 2026-06-28

## Purpose

This handoff is for a separate Codex chat to do low-regret launch prep while the first real benchmark result is pending.

Do not build or revise the full submission architecture yet. The first benchmark result may change what the system needs to store, validate, hash, display, or reject.

## Repo state

- Repo: `C:\Users\Michael\local-bench`
- Branch: `codex/local-bench-online-backend`
- Current deploy state: `docs/deploy/cloudflare-launch-state-2026-06-28.md`
- Cloudflare runbook: `docs/deploy/cloudflare-pages.md`
- Submission trust design, for later reference only: `docs/foundations/submission-verification-design.md`
- v1 launch scope guard: `docs/foundations/v1-launch-checklist.md`

Existing dirty worktree entries observed before this handoff:

```text
 M cli/pyproject.toml
 M docs/REPRODUCE.md
?? cli/src/localbench/monitor_cli.py
?? cli/src/localbench/monitor_records.py
?? cli/src/localbench/monitoring.py
?? cli/tests/test_monitoring.py
?? docs/deploy/cloudflare-launch-state-2026-06-28.md
?? docs/foundations/model-benchmark-roster-2026-06-28.md
```

Do not revert or clean these unless Michael explicitly asks.

## Current production facts

- Cloudflare Pages project `local-bench` exists and is Git-backed from private repo `Papa-midnight-dev/local-bench-site`.
- Production deployment succeeded from commit `423b99c9d293a57a722b49757425378967e4cc06`.
- Canonical Pages URL: `https://local-bench.pages.dev`
- Apex domain: `https://local-bench.ai`
- Production deployment URL: `https://494f03cd.local-bench.pages.dev`
- D1 binding `DB` points to `localbench_prod` (`31023810-a7f8-49d4-825e-01e976bd0e1d`).
- R2 bindings:
  - `SUBMISSIONS` -> `localbench-submissions`
  - `PUBLIC_ARTIFACTS` -> `localbench-public-artifacts`
- Queue producer binding `VERIFICATION_QUEUE` -> `localbench-verification`.
- Set production variables:
  - `LOCALBENCH_PUBLIC_BASE_URL=https://local-bench.ai`
  - `R2_ACCOUNT_ID=4af6606afb8636c5243c521f9bb26c70`
  - `R2_BUCKET_NAME=localbench-submissions`
- Still missing sensitive production secrets:
  - `ADMIN_API_SECRET`
  - `R2_ACCESS_KEY_ID`
  - `R2_SECRET_ACCESS_KEY`

Observed live checks:

```powershell
curl.exe -sS https://local-bench.ai/api/health
curl.exe -sS https://local-bench.pages.dev/api/health
curl.exe -sS https://local-bench.ai/api/suites/core-text-v1/manifest
```

Expected health payload:

```json
{"service":"localbench","status":"ok","storage":{"d1":true,"queue":true,"r2":true}}
```

Expected suite manifest facts:

- `suite_id`: `core-text-v1`
- `files`: `11`
- `suite_hash`: `6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179`

DNS caveat: `www.local-bench.ai` is configured and Cloudflare marks it active. Public resolver `1.1.1.1` resolves it, and forced-resolution to Cloudflare edge returned HTTP 200, but this machine's default resolver had not picked it up during the launch session.

## Allowed work now

Keep this prep narrow and reversible.

1. Add or update a non-secret launch smoke script.
   - Suggested path: `scripts/launch-smoke.ps1`
   - It should check:
     - `https://local-bench.ai/api/health`
     - `https://local-bench.pages.dev/api/health`
     - `https://local-bench.ai/api/suites/core-text-v1/manifest`
     - `www.local-bench.ai` DNS via the default resolver and `1.1.1.1`
     - optional Cloudflare Pages deployment status if Wrangler auth is already available
   - It should emit `PASS`, `WARN`, or `FAIL`, with no secrets.

2. Add a first-benchmark acceptance checklist.
   - Suggested path: `docs/deploy/first-benchmark-acceptance-checklist-2026-06-28.md`
   - It should define what "benchmark came back OK" means before submission architecture work resumes.
   - Include at least:
     - run completed without harness crash
     - suite hash matches `core-text-v1`
     - emitted bundle/result schema validates
     - lane metadata matches the launch lane
     - no leaked reasoning, truncation, or missing-final-answer pattern
     - scoring output is reproducible from artifacts
     - no one-off fix was applied outside the recorded runner/scorer path

3. Update `docs/deploy/cloudflare-pages.md` only if needed.
   - Clarify the live production resource names.
   - Clarify that the ticket/upload/admin smoke is blocked until the three missing secrets are set.
   - Do not remove the existing online submission smoke section; annotate it.

4. Prepare the secret-setting checklist, without generating or printing secrets in logs.
   - R2 S3 credentials must be created in Cloudflare dashboard with least privilege for `localbench-submissions`.
   - Set secrets with:

```powershell
cd C:\Users\Michael\local-bench\web
npx wrangler pages secret put ADMIN_API_SECRET --project-name local-bench
npx wrangler pages secret put R2_ACCESS_KEY_ID --project-name local-bench
npx wrangler pages secret put R2_SECRET_ACCESS_KEY --project-name local-bench
```

5. Optionally sketch submission boundaries in docs only.
   - Allowed: a short note naming ticket lifecycle, upload completion, verifier queue, admin decision, and publish gate.
   - Not allowed yet: D1 migration changes, API schema changes, queue behavior changes, automatic publishing, trust-label UI changes.

## Work to defer until the benchmark is OK

- Do not modify submission API behavior.
- Do not modify D1 migrations or stored submission schema.
- Do not modify verification queue semantics.
- Do not build admin approval UI.
- Do not regenerate or publish leaderboard data from submitted artifacts.
- Do not add private sentinel mechanics yet.
- Do not claim the online submission flow is launched until ticket issuance, R2 upload, D1 status transition, maintainer verification, and manual accept/reject have all been observed end to end.

## Suggested verification for the next chat

Run these after any handoff-prep edits:

```powershell
git status --short
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch-smoke.ps1
```

If a script is added under `scripts/`, prefer a dry-run/no-auth mode by default and make Cloudflare-auth checks optional.

For docs-only edits, no build is required unless the Next.js docs route consumes those files.

## Suggested prompt for the next chat

```text
Continue local-bench pre-confirmation launch prep from:
C:\Users\Michael\local-bench\docs\deploy\pre-confirmation-launch-prep-handoff-2026-06-28.md

Implement only low-regret prep while the first benchmark result is pending:
1. Add a non-secret launch smoke script.
2. Add the first-benchmark acceptance checklist.
3. Update the Cloudflare runbook only to reflect current live state and missing-secret blockers.

Do not modify submission API behavior, D1 migrations, queue semantics, admin UI, or leaderboard publishing yet. Preserve unrelated dirty worktree changes.
```
