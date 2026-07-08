# Go-public runbook — private-mode exit plan

Written 2026-07-07, when the site was intentionally flipped PRIVATE (Michael's call)
while the board is rebuilt under the bulletproof-then-fill-then-announce posture.
This file is the checklist for coming back out. Companion: `cloudflare-pages.md`
(mechanics), `live-state.md` (canonical live state), `requeue-landing-runbook.md`.

## Current state (2026-07-07)

- `LOCALBENCH_SITE_PRIVATE=1` set on Pages production; deployment `de0046b` serving
  503 + `x-robots-tag: noindex` unauthenticated.
- All pre-flip public-era deployments DELETED (28 leaking aliases removed across two
  passes; smoke `-ExpectedMode Private` = PASS=29 WARN=1 FAIL=0).
- Owner access: bypass token at `C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt`
  → CLI via `LOCALBENCH_PRIVATE_BYPASS_TOKEN` env var; browser via one-time
  `/?lb_bypass=<token>`.
- PyPI (`local-bench-ai` 0.2.3) and the public GitHub repo stay public by decision —
  visitors from those hit the 503, which is intended pre-announce.

## While private — the work queue (in order)

1. **Family-tree picker** (spec `docs/superpowers/specs/2026-07-07-picker-variant-hierarchy-design.md`):
   review + commit Codex web/catalog halves, run discovery waves across ALL bases,
   curate, deploy behind the gate.
2. **index.json structural fix** — legacy composites out of the standard field.
3. **Worker-marshalling plan** for coding-exec forgery vectors (plan to Michael first).
4. **Requeue landing** (~2026-07-08): follow `requeue-landing-runbook.md`
   (verifier → rescore → board → deploy). Works fine behind the gate.
5. **Michael fills the board** per the priority roster (Qwen ladder first). CLI runs
   need `LOCALBENCH_PRIVATE_BYPASS_TOKEN` set for fetch-suite/submit against the site.
6. Michael: reject the 3 stale QA tickets; display-name charset decision.

## Re-flip to public (when Michael says the board has enough data)

Every deploy while private re-checks the smoke (`-ExpectedMode Private`). Then:

1. From `web/`: `"0" | npx wrangler pages secret put LOCALBENCH_SITE_PRIVATE --project-name local-bench`
2. Cut a deployment: empty commit → `git push deploy HEAD:main` (env changes only
   apply to NEW deployments).
3. `scripts\launch-smoke.ps1 -ExpectedMode Public` must be fully green.
4. Delete any remaining PRIVATE-era deployment aliases if the smoke flags mixed
   modes (same procedure as the flip-in: `wrangler pages deployment delete`).
5. **Final ungated clean-room rehearsal (MANDATORY, not skippable):** fresh venv,
   follow the live homepage recipe end-to-end exactly as a stranger would — install
   from PyPI, fetch-suite, cache-tokenizer, preflight against a 32k/parallel-1
   server, and a /submit walk. The gated rehearsals do not count for this; bypass
   headers/cookies make the traffic path non-identical.
6. Sanity-check Google: site should re-index naturally (503 was served with
   noindex + no-store; no stale public cache to purge).
7. **Flip the watcher**: in the LocalBench-Watch script
   (`Projects\local-bench\monitor\lb-watch.ps1` in the OneDrive ClaudeCode dir) set
   `$ExpectedMode = "public"`, then run one manual tick and confirm the log line says
   `site: 200 (public, ok)`. Skipping this pages Michael with a false
   "SITE IS PUBLIC (expected private)" urgent alert on the next 15-min tick.
8. Browser-level family-tree picker walk (part of the mandatory rehearsal above —
   the picker shipped entirely behind the private gate and has never been exercised
   ungated).
9. Only then: Michael announces (announcement guidance in the launch-authorization
   memory; go-public call is Michael's alone).

## Gotchas learned at flip time (2026-07-07)

- `wrangler pages deployment list` paginates (~25 rows): after deleting leaking
  deployments, RE-RUN the smoke — it probes known aliases beyond the list page and
  found 4 more leaks on the second pass.
- Old deployments bake their build-time env: any deployment created while the site
  was public serves a full public site on its `<id>.local-bench.pages.dev` alias
  forever until deleted. After ANY env flip, enumerate + delete + re-smoke.
- The smoke's WARN about submission/admin legs is informational (state-mutating
  probes are intentionally skipped; verified out-of-band 2026-07-03).
