# Cloudflare launch state - 2026-06-28

## Completed

- Prototype private mode enabled through Cloudflare Pages middleware and production secrets:
  - `LOCALBENCH_SITE_PRIVATE=1`
  - `LOCALBENCH_PRIVATE_BYPASS_TOKEN` stored in Pages secrets
- Owner bypass token is stored locally at `C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt`.
- Cloudflare Pages project `local-bench` created in account `4af6606afb8636c5243c521f9bb26c70`.
- Git provider connected to private GitHub repo `Papa-midnight-dev/local-bench-site`.
- Production branch: `main`.
- Build settings:
  - Root directory: `web`
  - Build command: `npm ci && npm run build`
  - Output directory: `out`
- Production deployment succeeded from commit `423b99c9d293a57a722b49757425378967e4cc06`.
- Pages deployment URL: `https://494f03cd.local-bench.pages.dev`.
- Canonical Pages URL: `https://local-bench.pages.dev`.
- D1 binding `DB` points to `localbench_prod` (`31023810-a7f8-49d4-825e-01e976bd0e1d`).
- R2 bindings:
  - `SUBMISSIONS` -> `localbench-submissions`
  - `PUBLIC_ARTIFACTS` -> `localbench-public-artifacts`
- Queue producer binding `VERIFICATION_QUEUE` -> `localbench-verification`.
- Production runtime variables currently set through Pages secrets:
  - `LOCALBENCH_PUBLIC_BASE_URL=https://local-bench.ai`
  - `R2_ACCOUNT_ID=4af6606afb8636c5243c521f9bb26c70`
  - `R2_BUCKET_NAME=localbench-submissions`
- Custom domains attached and active:
  - `local-bench.ai`
  - `www.local-bench.ai`
- DNS records added in Cloudflare dashboard:
  - `local-bench.ai CNAME local-bench.pages.dev`, proxied
  - `www.local-bench.ai CNAME local-bench.pages.dev`, proxied

## Verification

- `https://local-bench.pages.dev/api/health` returned `{"service":"localbench","status":"ok","storage":{"d1":true,"queue":true,"r2":true}}`.
- `https://494f03cd.local-bench.pages.dev/api/health` returned the same health payload.
- `https://local-bench.ai/api/health` returned the same health payload over normal DNS on this machine.
- `https://local-bench.ai/api/suites/core-text-v1/manifest` returned `suite_id=core-text-v1`, `files=11`, suite hash `6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179`.
- Public/authoritative DNS resolvers (`1.1.1.1`, `8.8.8.8`, `ganz.ns.cloudflare.com`, `hattie.ns.cloudflare.com`) resolve both `local-bench.ai` and `www.local-bench.ai` to proxied Cloudflare A/AAAA records.
- Pages custom-domain status is active for both `local-bench.ai` and `www.local-bench.ai`.
- Forced-resolution checks against Cloudflare edge returned 200 for:
  - `https://local-bench.ai/api/health`
  - `https://www.local-bench.ai/api/health`
- Forced-resolution manifest smoke returned `suite_id=core-text-v1`, `files=11`, suite hash `6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179`.

## Still pending

- Local Windows/default resolver has picked up `local-bench.ai`, but not `www.local-bench.ai` yet. Public resolver `1.1.1.1` returns proxied A/AAAA records for `www`, and forced-resolution to Cloudflare edge returns HTTP 200, so this appears to be upstream/local DNS cache propagation rather than a Cloudflare Pages configuration failure.
- Submission ticket/admin surfaces still need sensitive production secrets:
  - `ADMIN_API_SECRET`
  - `R2_ACCESS_KEY_ID`
  - `R2_SECRET_ACCESS_KEY`
- R2 S3 API credentials were not present in the local API-key file search and the Wrangler OAuth token cannot create/list DNS records via API. Create least-privilege R2 credentials in the Cloudflare dashboard, then set the missing Pages secrets with `wrangler pages secret put --project-name local-bench`.

## Private-mode rollback

To make the site public again without removing middleware, set the production secret `LOCALBENCH_SITE_PRIVATE` to `0` and redeploy:

```powershell
cd C:\Users\Michael\local-bench\web
"0" | npx wrangler pages secret put LOCALBENCH_SITE_PRIVATE --project-name local-bench
git commit --allow-empty -m "chore(deploy): refresh private mode"
git push deploy HEAD:main
```
