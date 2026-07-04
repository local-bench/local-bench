# Holistic approach review (oracle, 2026-06-23)

GPT-5.5 Pro consult `localbench-holistic-approach-review`, given all four binding plans + a
"hunt for what we missed before a 1-2 month build" brief. Captured verbatim-in-summary; full
text in the run output. This is a DECISION INPUT, not yet adopted — the combined-launch call is
Michael's.

## Headline verdict: the benchmark spine is good; the COMBINED-LAUNCH scope is too risky
Oracle would NOT do the single combined public launch as scoped. **Single biggest risk = SCOPE
COUPLING:** the first public release is made to depend on ALL the hardest-to-prove pieces working
at once — AppWorld feasibility, full 96-task agentic coverage across every system, signed
submission intake, server-side verify, board merge, spot reproduction, sentinel policy,
Cloudflare-only anon ops, one serial GPU. If any one is hard (AppWorld feasibility + v2
anti-gaming genuinely are), the WHOLE launch stalls 1-2 months with no public presence/feedback.

**Killer point against combining:** the main rationale for combining (avoid a v1->v2 schema
migration) is ALREADY SOLVED by the distribution plan making my-run.json + the artifacts v2-ready.
So combining buys little and couples a lot.

## Oracle's recommended sequencing (a SPLIT, not a weak teaser)
- **Public v1:** project-anchor board + FUNCTIONAL local self-run (install wheel, fetch frozen
  MMLU-Pro 400 + IFBench 294, run, my-run.json) + immutable artifacts + "no public submissions
  yet" copy. This is a real, differentiated, reproducible product — gets external de-risking
  (installer, suite fetch, docs, artifacts) without pretending submissions exist.
- **Private/shadow v2 pilot:** collect a few outside bundles manually, run offline
  `localbench verify`, test schema + support burden.
- **Public v2:** `localbench submit`, Cloudflare upload, server/maintainer-side authoritative
  re-score, tiered display.
- **Agentic:** CANDIDATE only after the real CPU feasibility proof + smoke pass; do NOT let it
  block Core Text v1. (Downgrade from "launch gate" to "candidate-after-proof".)

## Missed / underweighted (scope-INDEPENDENT — fix regardless of launch shape)
1. **Anonymous-wheel TRUST problem.** Asking users to run code from an anon domain with no
   PyPI/repo needs a supply-chain story: publish a pseudonymous signed release bundle (wheel +
   SHA256SUMS + dep lock + SBOM + sanitized source zip + Ed25519 sig) + a "how to inspect what
   you install" page. No GitHub/PyPI needed.
2. **"Server-side re-score" compute placement is undecided.** Cloudflare Workers Python has CPU
   limits; a ~694-item re-score may need a maintainer-run/containerized verifier, not a Worker.
   Do NOT ship "server-side authoritative" copy until the path is tested end-to-end.
3. **Post-hoc signing != live run.** Reserve schema fields NOW: `submission_ticket_id`,
   `server_nonce`, `issued_at`, `run_started_at`, `run_finished_at` (v1 leaves null); v2 requires
   a pre-run ticket for anything above "community re-scored".
4. **Contamination/trust policy unfinished.** Decide BEFORE launch: sentinel-warn/fail rows
   excluded from default ranked view or heavily marked; how to label benchmark-trained models.
5. **Upload-bundle security missing.** Hard limits before any submit path: max bundle size /
   string length / item count, strict JSON schema, no zip traversal, no decompression bombs, no
   raw transcript rendering, HTML-escape model names, quarantine-before-verify.
6. **Strict determinism may not be real.** Run a repeatability slice NOW (2-3 models, same
   prompts/quant/runtime/one-slot, cache off): measure token / extracted-answer / score identity.
   Tier language ("spot-reproduced" = strict replay vs adjudicated score agreement) depends on it.

## Board / scoring traps to fix before launch
- **Model row semantics:** the board collapses the Qwen ladder to its best run while claiming
  rows are "systems". FIX: rank SYSTEMS (each quant its own row) OR family-summary + system-detail
  rows. Decide headline best-quant (Q6_K 75.25) vs recommended/plateau-quant (Q4_K_M 74.9).
- **Move ALL board math into the artifact generator** — no score math in web/; include
  per-run/per-quant detail in board_v1.json or a companion immutable artifact.
- Keep the scope-banner + judge-free-!=-complete honesty copy FRONT-PAGE prominent.
- **Model drift is real:** freeze model artifact URLs + SHA256s + llama.cpp commit + CUDA/runtime
  + templates + scorecard; treat v1 as an "as-of DATE" board; don't chase new models mid-build.

## Distribution / AppWorld confirmations
- Distribution plan "mostly right"; must-not-cut = resolver replacement, empty-machine test,
  top_k=1, narrow "board-comparable", CLI support tools. Finish NOTICE/ATTRIBUTION (IFBench
  ODC-BY-1.0 confirmed; MMLU-Pro dataset MIT) BEFORE serving the bundle.
- v2 uploads: direct-to-R2 correct; define gzip/JSONL + bundle-size now (Workers body limit
  100MB Free/Pro; R2 multipart for large).
- AppWorld: pin 0.1.3.post1 confirmed; do NOT spend GPU on 96-task until CPU install+verify+
  adapter-map+scripted-feasibility pass. (install+verify already PASS on-box.)

## The 10 cheapest changes now (oracle's list)
1 split the launch · 2 freeze the v2-compatible schema (nullable tickets/nonces/hashes/source/
tier/account/schema_version; preserve reasoning_text+finish_reason) · 3 build `localbench verify`
offline before any Cloudflare ingest · 4 do the AppWorld CPU feasibility proof IMMEDIATELY (de-scope
agentic if it fails) · 5 move all board math into the artifact + resolve quant semantics · 6
pseudonymous signed release manifest · 7 write the contamination/trust policy · 8 harden submission
parsing before upload UX · 9 determinism repeatability slice on the 5090 · 10 private beta with 3
users before any public launch.
