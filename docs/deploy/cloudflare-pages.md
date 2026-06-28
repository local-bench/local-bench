# Deploy: local-bench.ai on Cloudflare Pages

Updated 2026-06-28. This runbook is for the online launch with Pages Functions, D1, R2, and Queues.

## Architecture

- Cloudflare Pages hosts the static Next.js export and the `web/functions` API routes.
- D1 database `localbench_prod` stores suite/submission/job/decision metadata.
- R2 bucket `localbench-submissions` stores uploaded `.lbsub.zip` bundles.
- R2 bucket `localbench-public-artifacts` is reserved for generated public artifacts.
- Queue `localbench-verification` receives upload-complete jobs for the maintainer verifier loop.
- The public leaderboard remains generated from committed JSON. Accepted submissions do not publish automatically.

## Private GitHub Deploy Repo

Use a fresh private repo under `Papa-midnight-dev`, recommended name `local-bench-site`.

Cloudflare Pages settings:

- Project name: `local-bench`
- Production branch: `main`
- Root directory: `web`
- Build command: `npm ci && npm run build`
- Build output directory: `out`
- Functions directory: `functions`

Cloudflare supports private GitHub repos for Pages Git integration. Keep the deployment repo private unless public identity exposure is acceptable.

## Cloudflare Resources

Run from the repo root after authenticating Wrangler:

```powershell
cd web
npx wrangler d1 create localbench_prod
npx wrangler d1 migrations apply localbench_prod --remote
npx wrangler r2 bucket create localbench-submissions
npx wrangler r2 bucket create localbench-public-artifacts
npx wrangler queues create localbench-verification
```

Copy the D1 `database_id` into `web/wrangler.jsonc`.

Set Pages environment variables and secrets:

```powershell
npx wrangler pages secret put ADMIN_API_SECRET --project-name local-bench
npx wrangler pages secret put R2_ACCESS_KEY_ID --project-name local-bench
npx wrangler pages secret put R2_SECRET_ACCESS_KEY --project-name local-bench
npx wrangler pages secret put R2_ACCOUNT_ID --project-name local-bench
npx wrangler pages secret put R2_BUCKET_NAME --project-name local-bench
npx wrangler pages secret put LOCALBENCH_PUBLIC_BASE_URL --project-name local-bench
```

Use `https://local-bench.ai` for `LOCALBENCH_PUBLIC_BASE_URL` and `localbench-submissions` for `R2_BUCKET_NAME`.

## What Needs Manual Account Access

Michael must do the credentialed/account steps:

- Create or confirm the private GitHub repo.
- Connect the repo in Cloudflare Pages.
- Create R2 API credentials with least privilege for `localbench-submissions`.
- Set Pages secrets.
- Attach `local-bench.ai` and optionally `www.local-bench.ai` as custom domains.

Computer-use automation may help with non-sensitive clicks when available, but auth, 2FA, token creation, and final resource confirmation should remain human-confirmed.

## Local Preflight

Before pushing a deploy commit:

```powershell
.\scripts\deploy-site.ps1
```

The script now performs local preflight only: install, tests, typecheck, and static build. Git integration performs the actual Cloudflare deploy after the private repo is pushed.

## Online Submission Smoke

After the Pages deployment is live:

```powershell
curl https://local-bench.ai/api/health
localbench fetch-suite --source-url https://local-bench.ai/api/suites/core-text-v1/manifest --accept-suite-terms
localbench submit keygen --out localbench-ed25519.pem
localbench submit ticket --site https://local-bench.ai --signing-key localbench-ed25519.pem --out ticket.json
```

Then run a small fixture, pack it with `--ticket`, upload it, and poll status. A valid upload should appear in D1 as `uploaded`; the maintainer verifier should move it to `needs_review`.

## Maintainer Verification

Run from a trusted maintainer machine:

```powershell
$env:LOCALBENCH_ADMIN_SECRET = "<same value as ADMIN_API_SECRET>"
localbench submit admin-verify `
  --site https://local-bench.ai `
  --suite-dir <cached-suite-dir> `
  --work-dir runs\submission-verification
```

This downloads pending uploaded bundles through admin-only signed URLs, runs the existing deterministic offline verifier, writes local verification artifacts, and marks each submission `needs_review` or `rejected`.

Publishing is still manual:

1. Review the local verifier artifact.
2. Accept or reject through the admin decision endpoint.
3. Regenerate board data from accepted submissions.
4. Push the private deploy repo so Pages publishes the updated static board.

## Verification Checklist

- `https://local-bench.ai/` renders.
- `https://local-bench.ai/api/health` returns `{"status":"ok"}`.
- `https://local-bench.ai/api/suites/core-text-v1/manifest` returns hash-pinned suite files.
- CLI `fetch-suite --source-url` verifies the downloaded suite hash.
- A test `.lbsub.zip` uploads directly to R2 and D1 shows `uploaded`.
- `submit admin-verify` moves the test submission to `needs_review`.
- Public leaderboard does not change until board data is regenerated and redeployed.

## Rollback

Cloudflare Pages keeps deployment history. Use Pages → `local-bench` → Deployments → select previous deployment → Rollback.

## Anonymity Caveat

A private GitHub repo hides source and commit history from the public, but Cloudflare and GitHub still know the owning account. If public pseudonymity matters, use a clean pseudonymous GitHub org/repo before connecting Pages.
