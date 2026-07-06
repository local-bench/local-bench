# Live deployment state

Generated: 2026-07-04
Expected mode: Private
Expires for decision-making: 24h
Source: scripts/launch-smoke.ps1 -ExpectedMode Private -WriteState (plus authenticated wrangler deployment/D1 sweep after the contract-v2 deploy, 2026-07-04)

This file is the canonical live-facts document for launch-prep decisions. Handoffs and runbooks should link here instead of duplicating endpoint expectations.

## Expected public behavior

Unauthenticated production traffic is expected to be closed by private mode:

- `https://local-bench.ai/api/health`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.pages.dev/api/health`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.ai/api/suites/core-text-v1/manifest`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.
- `https://local-bench.ai/`: HTTP 503 with `cache-control: no-store` and `x-robots-tag: noindex`.

HTTP 200 from any unauthenticated production host or deployment alias is a release-blocking public leak.

All four private signatures plus both alias-domain checks PASSED on 2026-07-03 after the redeploy.

## Hosts and suite

- Apex host: `local-bench.ai`
- WWW host: `www.local-bench.ai`
- Pages host: `local-bench.pages.dev`
- Suite id (manifest smoke): `core-text-v1`
- Suite hash: `6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179`
- Expected suite file count: `15` (contract v2 added the 4 LICENSES entries that were missing from the catalog file list; suite dir hash unchanged — this was the `fetch-suite --site` fix)
- Site-released submission suites (contract v2): registered pairs `suite-v1-text-code-agentic-5axis-v1` (manifest sha `5a47282a...`, the ticket default) and `suite-v1-partial-text-code-4axis-v1` (manifest sha `b3fc4019...`). Community tickets must name a registered pair explicitly.

## Deployment facts

- Commit: `8742223` (Wave 5 board + provenance rendering, consistency fix, freeze re-pin eabdb69d…; branch `main` on the deploy remote, pushed 2026-07-05 early). Current production deployment id `992deab1-a6a0-43a5-b8d1-873267a77529` (source `8742223`). Smoke after this deploy: 24 PASS / 0 FAIL (private mode). Prior pin: `f0d7b5a2` (source `a0e4d20`).
- Pending rows added by live QA 2026-07-05: `ticket_2d2f80a8640d4dc48fb8052744ec1ea2` (community, display name "QA Fixture", hidden, pending) — content-equivalent to the ranked run; recommend REJECT after owner eyeball (its purpose, proving the live community leg, is served).
- Deployment id: VERIFIED 2026-07-04 via authenticated wrangler (account `michael.russell@clarityconsultive.com`, id `4af6606afb8636c5243c521f9bb26c70`). All enumerated production Pages deployment aliases return HTTP 503 or 404 — no leak on any live deployment.
- Health payload now reports `storage.queue: false` BY DESIGN: the dead `VERIFICATION_QUEUE` producer binding was removed (Pages cannot consume queues). d1 and r2 must be `true`.

## Leak-closure note

Two pre-gate production deployments, `494f03cd` and `ccedf382`, previously served unauthenticated HTTP 200 and were deleted on 2026-06-29. Deployment aliases remain part of the smoke gate because any deployment built before private-mode middleware, or any new deployment missing preview/production private vars, can re-open the leak. Full-fleet alias sweep 2026-07-03 (all 8 live deployments) returned 503 across the board.

## Secrets and submission pipeline state (verified 2026-07-03)

`ADMIN_API_SECRET`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` are SET and proven working: admin-gated ticket issuance (401 without the admin secret, 201 with), R2 presigned PUT of an 18.6MB bundle, and owner-bypass health/manifest all succeeded out-of-band. The smoke script does not probe these paths (state-mutating) and emits one informational WARN instead.

Both prior blockers are CLEARED as of 2026-07-03:

1. RESOLVED — `POST /api/submissions/{ticket}/complete`: the CLI writer-compliance fix landed on `main` (commit `e1876eb`) and was proven end-to-end. A full orchestrated submission (canary bundle sha `e8b34c05`) went ticket → R2 PUT → `/complete` → admin-verify → admin-decision `hidden`, all accepted; the 400 no longer reproduces. The banned `result_bundle_v1` top-level fields are stripped, and the embedded `manifest.integrity.publishable` now matches the validator (the W3 normalize-after-apply ordering fix). The site contract was correct and unchanged throughout.
2. RESOLVED — `npx wrangler login` completed; deployment enumeration and remote D1 `0003` apply are done (see below). Log tailing (`wrangler tail`) is now available.

Remote D1 state (2026-07-04): migration `0004_submission_contract_v2.sql` applied to `localbench_prod` (data-preserving submissions rebuild: server-derived `origin` column with CHECK, `expires_at`, `run_payload_sha256`, `duplicate_of`, unique indexes, `rate_counters` table). Pre-migration backup taken to `C:\Users\Michael\.localbench\backups\d1-localbench_prod-2026-07-04-pre0004.sql` and verified to contain both accepted rows. Post-migration query confirmed all 5 rows intact with `origin=project_anchor`; both accepted submissions (`ticket_790a73b6…` ranked row, `ticket_4cfd0aa2…` canary) remain `accepted` + publish `hidden`. Earlier state (2026-07-03): migration `0003_submission_reconcile.sql` applied.

The legacy finalize Bug 2 (opaque 500) is retired: the deployed structured error handling returns precise coded errors.

## Private bypass

Owner bypass token path:

```text
C:\Users\Michael\.localbench\local-bench-private-bypass-token.txt
```

The token must not be committed, echoed, logged, or included in command transcripts. `scripts/launch-smoke.ps1 -BypassTokenPath <path>` reads it at runtime and redacts it from output.

## Refresh command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch-smoke.ps1 -ExpectedMode Private -WriteState
```

That command writes `docs/deploy/live-state.generated.json` for machine-readable observations. This markdown file remains the human canonical live-facts document.

## 2026-07-05 — PUBLIC LAUNCH
- `LOCALBENCH_SITE_PRIVATE=0` set 2026-07-05; deployment `c0dcac37` (source `47aa5e0`) is PUBLIC. Smoke: 27 PASS / 0 FAIL, mode=Public (alias-leak check is now Private-mode-only by design).
- Ranked row `ticket_790a73b6e5b94f9ab26845da82d10dd1` publish_state=published.
- Public repo: https://github.com/local-bench/local-bench (anonymous author; initial snapshot + dist-rename commit; independent clone re-scrub PASS).
- PyPI: `local-bench-ai` 0.1.0 live (`local-bench` blocked by PyPI similarity to Menlo AI's `localbench`; owner chose local-bench-ai). Fresh-venv install + public fetch-suite verified end-to-end without any token.

## 2026-07-05 — POST-LAUNCH POLISH (QA sweep + owner review + identity re-anchor)
- Source commits `fdad3dd` (wave 1: onramp live-loop recipe, popular-band + HF links, efficiency-frontier chip, gate relabel, eligibility note, submit auto-resolve → 0.1.1) → `6f02eea` (wave 2: model-page trust labels, compare Q4_K_XL fix + coverage chips, measured-diagnostics section, sitemap/robots/canonical/OG, _redirects/_headers, conformance_status leak) → `bfa1e43` (wave 3: model→variant identity — ranked row re-anchored to `gemma-4-12b-it` label "Gemma 4 12B IT" variant "QAT Q4_K_XL", merged with the 7-quant ladder; run_path repo-root fallback; inline tc_json gate → MARGINAL 74.2%/0% on the ranked row; board_v2 sha `c199e25c…`, LAUNCH_FREEZE re-pinned, board_v1 untouched `3d058e60…`) → `15ee513` (model-page provenance prefers ranked run) → `d9445b9` (301s for the moved model/run URLs).
- PyPI: `local-bench-ai` **0.1.1** published + fresh-venv verified (`submit run` auto-resolves the fetched suite from cache; explicit `--suite-dir` wins).
- Smoke after wave-3 deploy: **29 PASS / 1 WARN / 0 FAIL, mode=Public**. Per-fix live battery: 26 PASS.
- Public repo synced: anonymous commit `00ddce6` (46 files), scrub 0 blocking / 8 known-benign advisories.
- KNOWN RESIDUALS: (a) `www.local-bench.ai` and `local-bench.pages.dev` still serve 200 duplicates — the `_redirects` host rules did not take effect on this stack; self-referencing canonicals are live on every page so indexing is protected; durable fix = zone-level Bulk Redirect (owner dashboard action, optional). (b) Apex briefly served a stale cached copy of the deleted old-slug model page; `d9445b9` turned those URLs into proper 301s.
- QA sweep evidence (route inventory all-200, zero leftover noindex, TTFB ~75–80 ms BNE, homepage ~214 KB, burst 150/150 OK, suite-hash provenance verified end-to-end) archived in the session scratchpad `qa-sweep/`.

## 2026-07-05 — LEADERBOARD LEGIBILITY (owner review round 2)
- Source commit `c62eb9b`: (a) leaderboard drops the **Kind** column ("Anchor"/"Community-reported" jargon — the "anchor" wording conflated the cloud-API reference-row concept with `origin: project_anchor`) and the **Tool-call format** gate column (gate still shown on model + run pages); (b) the **User** column becomes **Run by** — project-run rows are credited `local-bench`, community submissions show the submitter's credit line, unmeasured catalog shells show a placeholder; (c) model-page header badge is now "run by local-bench" / "submitted by <name>"; (d) origin trust chip (project anchor/community) removed — agentic `attested`/`self-reported` chips remain; (e) methodology taxonomy reworded to "Run by: local-bench vs community" (trust semantics unchanged); (f) landing-page section headers standardized to kicker + `text-2xl` h2 (were `text-lg` / missing / `text-3xl`).
- Display-layer only: board_v2/LAUNCH_FREEZE untouched (board sha `c199e25c…`), board_v1 pin verified `3d058e60…`. Web tests 134/134; static-export greps confirmed all six surfaces before deploy.
- Public repo synced: anonymous commit `cb059cb`, scrub 0 blocking / 8 known-benign advisories.

## 2026-07-05 — BOUNDED-FINAL-V1 BUILD, waves 0-1 + bench-time chip
- Design spec of record committed: `docs/design/bounded-final-v1.md` (`5ba0348`) — all-families ranked lane (index-v3.0), approved by owner, oracle-reviewed (GPT-5.5 Pro).
- Wave 1 `a86ea74`: scorecard v3 identity — per-profile digests + lane_spec digest; whole-catalog digest demoted to informational; submission validation now checks the selected profile against the server allowlist (adding families no longer invalidates in-flight bundles). Suite SCORECARD/SHA256SUMS/release manifests regenerated; frozen item sets + itemsets.lock UNTOUCHED (verified); board_v1 pin intact. Verified: pytest 1123/17skip/1xfail, vitest 134, build green.
- CUTOVER NOTE: pre-v3 CLI bundles now reject with an upgrade message (accepted; zero live community submitters). PyPI 0.2.0 to ship with wave 2a to close the window.
- Bench-time chip `a0a1ba2` (merge `7630080`): "Estimated benchmark time" panel top-right of the homepage onramp; decode-physics estimate calibrated against measured runs (utilization 0.5 reproduces both dense runs ±27%; suite constant 6.1M tokens matches the five-axis run within 1%); live-verified (4 checks; served SCORECARD.json confirms v3 shape). 150 web tests.

## 2026-07-06 — FRESH BOUNDED-FINAL-V2 BOARD LIVE
- Source commits `0e49e2b` (two v3 ranked-gate fixes: agentic budget-audit exclusion + deterministic-fail coding gate, with realistic-shape regression tests) → `8bd1e81` (fresh board: Gemma 4 12B IT QAT bounded-final-v2 row added re-scored under scorecard v3, best_system ranked-first fix, HEADLINE_LANE web flip, index-v3.0, LAUNCH_FREEZE re-pin) → `f49718b` (public-scrub hygiene). Pushed to deploy `main`; new board detected live at 19:53 AEST.
- Board: sha `a1115302f2139b0a6ea51a3ad39bdd86451207e25f7f84f9162b24ba176f7c61`, frozen `2026-07-06T00:00:00Z`, parity ok. ONE ranked row: `gemma-4-12b-it` Index 35.20 [32.81, 37.90] on bounded-final-v2 (agentic 4.2/100 — v2 funnel protocol is far harder than v1's ~32; attested, not harness-dominated). Six v1 capped-thinking measured rows now render in the measured-diagnostics section; static-composite section is empty by design until v2 static rows exist.
- Gemma was RE-SCORED, not re-run: generations hash-pinned unchanged, coding re-executed by the sandbox verifier under the final scorer, identity + budget audit re-derived (`rescore_provenance` in the run file). Run lives at `runs/bench/ranked-6axis-bounded-final-2026-07-06/` (untracked; board_v2 is the committed artifact).
- Tests at ship: cli 1244 passed / web 202 passed / tsc / static build. Smoke after deploy: **36 PASS / 1 WARN (known informational) / 0 FAIL, mode=Public**.
- Public repo synced: anonymous commit `4a980d0`; scrub 0 blocking / 8 known-benign advisories (two NEW blocking findings — absolute paths in the catalog report + swept-in catalog-refresh-out/ — were fixed at source in `f49718b` first).
- Qwopus3.6-27B-v2-MTP + base Qwen3.6-27B requeue is running (runner-v2-requeue.ps1, ~34h from 16:35 06-07); those land as ranked rows 2-3 under the same identity (scorecard_id verified unmoved by the gate fixes).

## 2026-07-05 — BOUNDED-FINAL-V1 waves 2a+2b COMPLETE; PyPI 0.2.0
- Wave 2a `88832be`: bounded-final-v1 lane + answer_only_v1 (model_match "*") + budget audits + conformance splits + index-v3.0 ranked predicate (audits + allowlisted profile digest; missing items score 0). Any model id can produce a publishable rankable run — family gate removed.
- Wave 2b `e3d59f5`: generic_think_tags_8192_v1 (two-pass forcing, canonical-template rendering, tokenizer-derived stops, usage-metered budgets) + gemma4_channel_8192_v1 override; --profile auto template introspection; legacy v1 profile digests pinned as hardcoded constants (review addition); suite scorecard_id asserted UNCHANGED across profile additions. pytest 1169 / vitest 150.
- Leaderboard visual waves (same day): shared axis palette + header dots (`808c8d8`), index contribution rail on /leaderboard + agentic funnel-join fallback to the ranked run's own axis + coding→magenta + tool-gate pill relocated into Variant profiles (`1ed446b`). All live-verified.
- **PyPI `local-bench-ai` 0.2.0 published + fresh-venv verified** (5 ranked profiles, 2 lanes) — closes the scorecard-v3 cutover window opened by wave 1.
- NEXT: wave 3 GPU batch (Gemma v3 re-run + Qwopus five-axis) pending owner go-ahead; wave 4 site flip after the board reseeds.
