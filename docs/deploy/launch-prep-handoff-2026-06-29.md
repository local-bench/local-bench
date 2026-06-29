# Launch-prep build spec / handoff — 2026-06-29

> **SUPERSEDES** `docs/deploy/pre-confirmation-launch-prep-handoff-2026-06-28.md`.
> That handoff's "Current production facts" are STALE (they describe the pre-private-mode
> public deployment). Do not trust its endpoint expectations. This document is the source of truth.

## Roles
- **Orchestrator (Claude):** owns this spec, reviews diffs, and QAs by live-testing against
  the production site. Will not accept the build until the success criteria below pass.
- **Implementer (Codex / GPT-5.5):** builds the P0 deliverables exactly as specified. Stay
  inside the allowed scope. Do not touch deferred surfaces. Do not claim done until the
  end-of-session verification passes.

## Corrected production facts (verified live 2026-06-29)
- The site is in **PRIVATE MODE**. Gate = `web/functions/_middleware.ts` (root Pages Functions
  middleware, no `_routes.json`, covers all paths, fails **closed**). Keyed on env
  `LOCALBENCH_SITE_PRIVATE ∈ {1,true,yes,on}`; bypass via header `x-localbench-bypass`,
  cookie `lb_private_bypass`, or query `?lb_bypass=<token>` matching `LOCALBENCH_PRIVATE_BYPASS_TOKEN`.
- Public requests return **HTTP 503** with `cache-control: no-store` and `x-robots-tag: noindex`.
  Confirmed live on `https://local-bench.ai/api/health`, `/api/suites/core-text-v1/manifest`,
  and `https://local-bench.pages.dev/api/health`.
- **Live production deployment:** `049f238e` (commit `05263f1`, branch `main`) — gated (503). The
  prior `5a325e77` (commit `d58e3db`, "gate prototype behind private mode") is also gated (503).
- **Leak closed today:** two PRE-gate production deployments were serving the full site publicly
  at HTTP 200 (`494f03cd` / commit `423b99c`, and `ccedf382` / commit `6703b41`). Both were
  `wrangler pages deployment delete --force`d on 2026-06-29 and now return 404. The gate landed in
  `d58e3db`; any deployment built before that has no middleware and leaks if left alive.
- **Still-missing production secrets** (submission/admin surfaces genuinely blocked — leave unset):
  `ADMIN_API_SECRET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
- Bypass token stored locally at `C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt`
  (outside git; never echo it).

## Known lane-spec defect (decision pending — do NOT silently publish around it)
`docs/foundations/submission-verification-design.md` already records: the suite ships
`decoding: {temperature: 0}` only (no `top_k`), and **"Do NOT define the lane as temperature=0 in
llama.cpp … Pin canonical greedy as `top_k=1` / single sampler"** (build-order item #1). Implication:
the first **publishable** benchmark must run under the final `top_k=1` lane, OR the pending pilot is
labelled calibration-only. The acceptance checklist below puts lane/sampler freeze at the top.
(Decision owner: Michael. Codex: do not change `suite/v1/suite.json` decoding as part of this prep.)

---

## ALLOWED WORK (P0 — this session only)

### 1. Canonical live-state doc + kill doc-drift
- Create `docs/deploy/live-state.md` as the **single source of truth** for current live facts
  (expected mode = Private, hosts, suite_id `core-text-v1`, suite_hash
  `6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179`, live deployment id,
  missing-secret blockers, leak-closure note, bypass-token path).
- Add a header block: `Generated:`, `Expected mode: Private`, `Expires for decision-making: 24h`,
  `Source: scripts/launch-smoke.ps1 -ExpectedMode Private -WriteState`.
- Handoffs/runbooks must **link** to this file, never duplicate live endpoint facts. Add a one-line
  pointer at the top of `pre-confirmation-launch-prep-handoff-2026-06-28.md` marking it superseded.

### 2. `scripts/launch-smoke.ps1` — private-mode-aware smoke (no secrets in source/output)
Signature: `-ExpectedMode Private|Public|Auto` (**default Private**), `-BypassTokenPath <path>`
(optional), `-RequireCloudflareAuth` (optional), `-WriteState` (optional → emit
`docs/deploy/live-state.generated.json`).

- **ExpectedMode=Private** — public unauthenticated checks must assert the PRIVATE SIGNATURE
  (`503` **and** `cache-control: no-store` **and** `x-robots-tag: noindex`) on: apex
  `local-bench.ai`, `local-bench.pages.dev`, suite manifest, root page. A `200` (public leak),
  wrong status, or missing privacy header = **FAIL** (do not WARN). Do **not** treat
  "public-200-OR-private-503" as PASS — that masks accidental exposure.
- **Deployment-alias leak check (REQUIRED):** enumerate Pages deployments
  (`wrangler pages deployment list --project-name local-bench` if auth present) and assert no
  deployment subdomain serves `200` to an unauthenticated request. Any public `200` = **FAIL**.
  If wrangler auth absent → WARN (cannot enumerate), still check known aliases passed in.
- **Authenticated bypass check (optional, secret-safe):** only if `-BypassTokenPath` present and
  the file exists — read token at runtime, trim CRLF, send via header, PASS only if `200` + exact
  expected payload/hash. Token missing → WARN ("owner bypass not tested"). Bypass returns 503/wrong
  payload → FAIL. Token must NEVER appear in stdout, logs, or exception text (redact). Never run
  `curl -v` with the bypass header.
- **ExpectedMode=Public** — assert `200` + expected JSON (`service=localbench`, `status=ok`, storage
  booleans) on health; `200` + `suite_id=core-text-v1` + file count + exact suite hash on manifest.
- **ExpectedMode=Auto** — diagnostic only (print detected mode); MIXED public/private results = FAIL,
  not WARN. Not a release gate.
- **DNS:** `local-bench.ai` and `www`: default-resolver+`1.1.1.1` both resolve → PASS;
  default fails but `1.1.1.1` resolves → WARN (cache lag); `1.1.1.1` fails → FAIL.
- **Submission/admin:** ticket/upload/admin are **WARN** ("blocked by missing secrets
  ADMIN_API_SECRET/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY"), never FAIL — not a site-health issue.
- **Implementation requirements:** `Invoke-WebRequest`/`curl.exe` with explicit timeout;
  case-insensitive header checks; cap response-body excerpts; redact token from any output; exit
  nonzero only if ≥1 FAIL; final summary line: PASS/WARN/FAIL counts + detected mode.

### 3. `docs/deploy/first-benchmark-acceptance-checklist-2026-06-29.md` — two gates
**Gate A — Publish gate** (result trustworthy enough to show). P0 items, lane/sampler freeze FIRST:
1. **Lane/sampler frozen** — record lane name + all lane-defining params (hardware class, runtime,
   context length, capping policy, sampler sequence, `top_k`, `temperature`, seed, batch size,
   prompt-cache, slot count, flash-attn, KV precision, RoPE, stop tokens, max tokens, timeout).
   Do not publish a first result under ambiguous `temperature=0`-only unless clearly labelled
   non-final (see lane-spec defect above).
2. **Model-system identity complete** — model name + source + **model-file SHA256** + GGUF/quant
   metadata + quantization type + tokenizer hash + chat-template hash + runtime engine/version/commit
   + build flags + GPU/VRAM + driver + CUDA/runtime versions + OS.
3. **Runner+scorer provenance pinned** — repo commit, dirty-tree status (block publish if dirty, or
   attach a patch hash that reconstructs the run), CLI/pkg versions, lockfile hash, runner/scorer
   config hashes, extractor version, suite manifest hash, scorecard id.
4. **Complete artifact bundle exists before scoring** — rendered prompts, raw outputs, extracted
   answers, per-item metadata, token counts, stop reasons, log excerpts, run manifest, scorer output,
   validation report, top-level manifest hashing every file. Scoring reproducible from the bundle
   offline (no site/D1 contact).
5. **Prompt-template fidelity** — hash template + fully-rendered prompts; confirm no per-item edits,
   no ground-truth leakage, correct chat template/system prompt, no pre-model truncation.
6. **Invalid/refusal/truncation accounting explicit** — define how refusal / format-failure /
   missing-final-answer / leaked-reasoning / truncation / timeout / OOM / empty / duplicate count in
   the denominator. Do not silently drop failed items; show invalid/format/truncation rates next to scores.
7. **Scorer determinism proven** — run scorer twice from the same bundle → byte-identical score JSON
   (or document timestamp-only diffs). Tie-breaking, rounding, weighting, normalization deterministic.
8. **Reproducibility demonstrated** — a clean checkout reproduces the published score + row hashes
   from artifacts.
9. **Statistical sufficiency visible** — exact expected/attempted/valid/invalid item counts per
   axis + CIs (do NOT use "files=11" as the denominator). Show per-axis scores + uncertainty so rank
   diffs aren't overclaimed.
10. **Tamper-evidence** — top-level release manifest hashing suite manifest, runner config, model
    file, prompt template, rendered prompts, raw transcripts, extracted answers, score output,
    board row, public bundle. Public board row should carry bundle + scorecard hash.
11. **No unrecorded manual path** — extend "no one-off fix outside runner/scorer": no manual
    transcript edits, no hand-corrected answers, no post-hoc item exclusion, no rerun-because-
    underperformed, no prompt tweak after seeing failures.
12. **Redaction + license pass** — no local usernames / Windows paths / hostnames / secrets /
    private-repo URLs / identity-bearing logs in public artifacts; confirm dataset/model license
    permits the exact public release.

**Gate B — Pipeline-unblock gate** (may resume submission work only when Gate A passes AND):
- first bundle validates under the future submission-bundle validator;
- validator emits a deterministic accepted-result projection containing every public-board field;
- D1 can be designed as index rows pointing to immutable bundle hashes (D1 ≠ scoring truth);
- trust labels frozen as conservative ("community re-scored" / "spot-reproduced", not "verified");
- format represents both `origin: project_anchor` and `origin: community_submission`;
- same scorer path for project + community artifacts.
- Bridge test (no D1): `validate-submission-bundle` + `rescore-bundle` on the first anchor bundle →
  `accepted_result_projection.json` that exactly matches the public board row.

### 4. Update `docs/deploy/cloudflare-pages.md` (timeless runbook only)
Add: private-mode enable/rollback, how to run the smoke, **deployment-retention/leak guidance**
(delete pre-gate deployments; new public deployments can re-open the leak), and Preview-env
hardening. Do NOT hard-code "today returns 503/200" except as labelled examples. Annotate (don't
remove) the existing online-submission smoke section as blocked-by-missing-secrets.

### 5. Harden Preview environment (config note + action if you have dashboard/wrangler access)
Private mode keys on `LOCALBENCH_SITE_PRIVATE`. Cloudflare Pages scopes vars per-environment, so a
Preview deployment without it serves publicly. Ensure `LOCALBENCH_SITE_PRIVATE` +
`LOCALBENCH_PRIVATE_BYPASS_TOKEN` are set on **Preview** too, or disable preview/branch builds.
Document this in the runbook regardless.

---

## DEFERRED — do NOT touch until the first benchmark validates
- No D1 migrations or stored submission schema changes.
- No submission API behavior changes; no queue producer/consumer semantics changes.
- No admin approval UI; no automatic publish; no leaderboard regeneration from submitted artifacts.
- **Do NOT set** `ADMIN_API_SECRET` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` — they are a
  current safety rail; setting them turns half-built endpoints into live mutation paths.
- No trust-label UI changes; no private sentinel mechanics.
- Do not change `suite/v1/suite.json` decoding (lane re-pin is Michael's call, separate change).
- Do not claim the online submission flow is launched until ticket → R2 upload → D1 transition →
  verify → manual accept/reject → publish are all observed end to end.

## SUCCESS CRITERIA (launch-prep contract — session is done only if ALL true)
1. `scripts/launch-smoke.ps1` exists and supports `-ExpectedMode Private` (default).
2. Running it with `-ExpectedMode Private` PASSES against the live site (apex/pages/manifest all
   503+privacy-headers; no deployment alias serves 200; submission = WARN).
3. `docs/deploy/live-state.md` exists; the 06-28 handoff is marked superseded; no handoff duplicates
   live endpoint facts.
4. `docs/deploy/first-benchmark-acceptance-checklist-2026-06-29.md` exists with both gates and
   lane/sampler freeze at the top.
5. `docs/deploy/cloudflare-pages.md` updated with private-mode + leak/retention + Preview hardening.
6. **No** D1 migration / submission API / queue / admin UI / publish / secret-setting / suite.json
   changes in the diff.

## END-OF-SESSION VERIFICATION (run before claiming done)
```powershell
git -C C:\Users\Michael\local-bench status --short
git -C C:\Users\Michael\local-bench diff --name-only
Set-Location C:\Users\Michael\local-bench
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch-smoke.ps1 -ExpectedMode Private
```
Orchestrator (Claude) will independently re-run the smoke against the live site and review the diff
before accepting. Engine-track work (checkpointing/monitoring) does NOT count as launch prep — keep
it out of this diff.
