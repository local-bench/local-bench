# Deploy: local-bench.ai on Cloudflare Pages

Updated 2026-06-28. This runbook is for the online launch with Pages Functions, D1, R2, and Queues.

Current live endpoint facts are intentionally not duplicated here. Use `docs/deploy/live-state.md` as the canonical live-state source, and refresh observations with `scripts/launch-smoke.ps1`.

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

Private-mode variables are separate from the online submission secrets:

- `LOCALBENCH_SITE_PRIVATE`: set to `1`, `true`, `yes`, or `on` to close the public site.
- `LOCALBENCH_PRIVATE_BYPASS_TOKEN`: owner bypass token used by the middleware.

Cloudflare Pages scopes variables per environment. Set both private-mode variables in Production and Preview, or disable preview/branch builds. A Preview deployment without `LOCALBENCH_SITE_PRIVATE` can serve publicly even when Production is private.

The online submission/admin secrets (`ADMIN_API_SECRET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`) are intentionally unset while the submission pipeline is incomplete. Do not set them as part of private-mode launch prep.

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

## Launch Smoke

Run the private-mode smoke from the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch-smoke.ps1 -ExpectedMode Private
```

The default `-ExpectedMode` is `Private`. In private mode, unauthenticated apex, Pages host, suite manifest, and root-page checks must return the private signature: HTTP 503 plus `cache-control:no-store` plus `x-robots-tag:noindex`. HTTP 200 is a release-blocking leak, not a warning.

Optional owner-bypass smoke reads the token at runtime and redacts it from output:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch-smoke.ps1 `
  -ExpectedMode Private `
  -BypassTokenPath C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt
```

Use `-WriteState` to write `docs/deploy/live-state.generated.json` after a credentialed smoke. Use `-RequireCloudflareAuth` when deployment enumeration must be present instead of warning if Wrangler is unavailable or unauthenticated.

## Online Submission Smoke (blocked by missing secrets)

This section is future-use while `ADMIN_API_SECRET`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` are unset. Until those secrets exist, ticket/upload/admin checks are WARN-only in `scripts/launch-smoke.ps1`; they are not site-health failures.

Prototype private mode may block public smoke checks. If `LOCALBENCH_SITE_PRIVATE=1`, pass the owner bypass token from `C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt` with `x-localbench-bypass`, or open `/?lb_bypass=<token>` once in a browser to set the private cookie.

Prototype private mode may block public smoke checks. If `LOCALBENCH_SITE_PRIVATE=1`, pass the owner bypass token from `C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt` with `x-localbench-bypass`, or open `/?lb_bypass=<token>` once in a browser to set the private cookie.

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

Use this checklist only for an intentional public-mode launch. For current private-mode expectations, use `docs/deploy/live-state.md` and `scripts/launch-smoke.ps1 -ExpectedMode Private`.

- `https://local-bench.ai/` renders.
- `https://local-bench.ai/api/health` returns `{"status":"ok"}`.
- `https://local-bench.ai/api/suites/core-text-v1/manifest` returns hash-pinned suite files.
- CLI `fetch-suite --source-url` verifies the downloaded suite hash.
- A test `.lbsub.zip` uploads directly to R2 and D1 shows `uploaded`.
- `submit admin-verify` moves the test submission to `needs_review`.
- Public leaderboard does not change until board data is regenerated and redeployed.

## Prototype Private Mode

The Pages middleware can keep the prototype inaccessible to the public while preserving the deployment, D1, R2, Queues, and owner/API smoke access.

Production private-mode secrets:

```powershell
cd C:\Users\Michael\local-bench\web
"1" | npx wrangler pages secret put LOCALBENCH_SITE_PRIVATE --project-name local-bench
Get-Content C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt -Raw | npx wrangler pages secret put LOCALBENCH_PRIVATE_BYPASS_TOKEN --project-name local-bench
```

Repeat the same private-mode configuration for the Preview environment through the Cloudflare dashboard, or with the equivalent Wrangler environment selector supported by the installed Wrangler version. If Preview cannot be hardened, disable preview/branch builds before exposing deployment URLs outside the owner workflow.

Owner smoke:

```powershell
$token = Get-Content C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt -Raw
curl.exe -H "x-localbench-bypass: $token" https://local-bench.ai/api/health
```

Public rollback:

```powershell
cd C:\Users\Michael\local-bench\web
"0" | npx wrangler pages secret put LOCALBENCH_SITE_PRIVATE --project-name local-bench
git commit --allow-empty -m "chore(deploy): refresh private mode"
git push deploy HEAD:main
```

After enabling private mode or rolling back to public mode, run `scripts/launch-smoke.ps1` with the matching `-ExpectedMode`. Do not use `-ExpectedMode Auto` as a release gate; it is diagnostic only and mixed public/private endpoint results are failures.

## Deployment Retention and Leak Guidance

Cloudflare Pages deployment aliases remain routable after newer deployments ship. Any deployment built before the private-mode middleware can serve a full public site if retained. Delete pre-gate deployments, and re-run the smoke after every deploy, rollback, or environment-variable change.

Credentialed cleanup example:

```powershell
cd C:\Users\Michael\local-bench\web
npx wrangler pages deployment delete --project-name local-bench <deployment-id> --force
```

The launch smoke enumerates Pages deployments when Wrangler is available and also checks known aliases. Any deployment alias that returns unauthenticated HTTP 200 fails the gate.

## Rollback

Cloudflare Pages keeps deployment history. Use Pages → `local-bench` → Deployments → select previous deployment → Rollback.

## Anonymity Caveat

A private GitHub repo hides source and commit history from the public, but Cloudflare and GitHub still know the owning account. If public pseudonymity matters, use a clean pseudonymous GitHub org/repo before connecting Pages.
