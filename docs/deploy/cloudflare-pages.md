# Deploy: local-bench.ai on Cloudflare Pages (v1, read-only board)

**Goal:** publish the static leaderboard at `https://local-bench.ai` with HTTPS.
**What ships:** a fully static site. `web/next.config.mjs` has `output: "export"`,
so `npm run build` emits `web/out/` (117 prerendered pages + the committed
`public/data/*.json`). No server, no Workers, no R2/D1 for v1 — Pages alone is enough.

> v2 (community submissions per `docs/foundations/submission-verification-design.md`)
> adds Workers + R2 + D1 later. This runbook is v1 only.

---

## Decision: Wrangler direct-upload (not Git integration)

The repo has **no git remote** and the standing rule is "commits stay local, never
pushed." So we build locally and upload the static output directly with Wrangler.
No GitHub, no Cloudflare repo access, no CI.

| | **Path A — Direct upload (chosen)** | Path B — Git integration (future) |
|---|---|---|
| Push repo to GitHub? | No | Yes (required) |
| Auto-deploy on push | No (run a script) | Yes |
| PR preview URLs | No | Yes |
| Build runs where | This machine | Cloudflare's build container |
| Fits "commits stay local" | Yes | No |

Path B is the better long-term setup (previews, provenance). Switch when/if the
repo goes to GitHub — the build command (`cd web && npm run build`, output `web/out`)
and the committed `public/data` make it a clean swap. Cloudflare's builder needs
**no Python**: the data JSON is pre-generated and committed, so CF only runs
`next build`.

---

## One-time setup — **MICHAEL'S HANDS** (≈5 min, browser + one CLI auth)

These touch account credentials, so do them yourself; don't hand them to an agent.

1. **Account ID** — Cloudflare dashboard → any domain's Overview → right sidebar
   "Account ID". Copy it.
2. **API token** — dashboard → My Profile → **API Tokens** → Create Token →
   template **"Edit Cloudflare Pages"** → scope to your account → Continue → Create.
   Copy the token (shown once).
   - Scoped to Pages only — safe to use in the deploy script. Revocable anytime.
3. **Make the two values available to the shell that runs the deploy** (current
   PowerShell session — not committed anywhere):
   ```powershell
   $env:CLOUDFLARE_ACCOUNT_ID = "<account id>"
   $env:CLOUDFLARE_API_TOKEN  = "<token>"
   ```
   (Alternative to the token: `npx wrangler login` — OAuth browser flow. Token is
   better here because the deploy script is non-interactive.)

After the **first** deploy creates the project, one more browser step for the domain:

4. **Custom domain** — dashboard → **Workers & Pages** → `local-bench` project →
   **Custom domains** → "Set up a custom domain" → enter `local-bench.ai`
   (optionally also `www.local-bench.ai`). Because the zone is already on Cloudflare
   Registrar, it auto-creates the DNS record and provisions the HTTPS cert (live in
   a few minutes). Apex works via Cloudflare's automatic CNAME flattening — nothing
   to configure manually.

That's the entire hands-on list: **Account ID, API token, custom-domain click.**

---

## Repeatable deploy — **SCRIPTABLE** (`scripts/deploy-site.ps1`)

With the two env vars set, every deploy is one command from the repo root:

```powershell
.\scripts\deploy-site.ps1
```

The script gates on quality before publishing, then uploads:

1. `npm ci` in `web/` (clean, lockfile-exact install)
2. `npm run test` (vitest) — abort on failure
3. `npx tsc --noEmit` — abort on failure
4. `npm run build` → `web/out/`
5. `npx wrangler pages deploy out --project-name=local-bench --branch=main`

First run also creates the project if missing (`wrangler pages project create`).
The build deploys the **committed** `web/public/data` — it does **not** regenerate
data (that needs the run JSONs + the pinned Py314 venv, which aren't a deploy
concern). Regenerate separately with `web/build_data.py` and commit before deploying
when the numbers change.

---

## Codex computer-use? — not worth it

The handoff floated handing the browser-driven Cloudflare setup to a Codex
computer-use session. Recommendation: **don't.** The hands-on steps are ~5 minutes,
one-time, and credential-sensitive (an API token + account navigation, likely behind
2FA). A browser agent there adds account-security risk for almost no time saved. The
*repeatable* part — the actual deploy — is pure CLI with zero browser, already
scripted. Give the agent nothing it can't do safely; the click-path above is faster
and safer by hand.

---

## Verify after go-live

- `https://local-bench.ai/` → graph + summary board renders.
- `https://local-bench.ai/leaderboard/` → full board, "Full bench time" column,
  no "Core Text" anywhere.
- `https://local-bench.ai/methodology/` → states Knowledge (MMLU-Pro) + Instruction
  (IFBench) feed the Index.
- HTTPS padlock valid; HTTP redirects to HTTPS (Pages default).

## Rollback

Cloudflare Pages keeps every deployment. Dashboard → project → Deployments →
pick a previous one → "Rollback to this deployment". Instant, no rebuild.

## Anonymity (pre-launch gate #20)

Verified 2026-06-23 — the published artifact carries no operator identity:
- **No public repo.** Deploy is Wrangler **direct upload** of `web/out/`, not a connected git
  repo, so commit history / author metadata is never published.
- **Site + `<meta>` clean.** No name, email, or personal account anywhere in the built site
  (`web/out/`), page copy, or metadata. `app/layout.tsx` sets only a generic title +
  description; there are no `author` / `og:` / `twitter:` tags, so nothing to leak.
- **Deploy script clean.** `scripts/deploy-site.ps1` holds no PII; credentials come from the
  `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` env vars, never hardcoded.
- **Re-check before each deploy** if site copy changed:
  `grep -riE "michael|russell|clarity|outlook" web/out/` must return nothing.

## Publish gate G0 (must hold before first go-live)

- [x] No answer-only gemma in headline rank (gemma rows are score-less shells)
- [x] Candidate axes (Math/Coding-exec/Agentic) out of the composite, no fabricated
      numbers (synthesized-axes fix + n=0 "— not measured" guards)
- [x] Site + methodology tell one story; "Intelligence Index" naming applied
- [ ] Michael provides Account ID + API token, runs `deploy-site.ps1`, attaches domain
