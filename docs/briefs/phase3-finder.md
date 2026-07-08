<task>
Build the Phase-3 "Rig-Match Finder" HOME hero for local-bench's web app, plus the clearly-labelled
synthetic DEMO dataset it needs to render. Work ONLY on git branch `site-overhaul` (already checked
out). This is the visible centrepiece of the finder-first redesign. You implement; Claude reviews.
</task>

<context>
Read FIRST, in this order:
- docs/foundations/website-design-v2.md  — the APPROVED design. Build to its "Home — Rig-Match Finder"
  section (selectors -> ranked "what fits" list; anchors = ceiling; scatter kept prominent; bounty board)
  and its resolved forks + data caveat.
- docs/foundations/site-audit.md — component/file map.
- Existing web code you will extend/reuse: web/app/page.tsx, web/components/home-leaderboard.tsx,
  web/components/model-scatter.tsx, web/lib/schemas.ts, web/lib/axis-config.ts, web/lib/data.ts,
  web/lib/format.ts, web/build_data.py, web/data_sources.json, web/tailwind.config.ts.

The site is already axis-agnostic (web/lib/axis-config.ts is the single source of truth). Current REAL
data = 4 API anchors (lane api-uncapped) + 1 local Qwen3.5-9B (lane answer-only). API anchors have NO
local VRAM footprint — they are a CEILING reference only, never ranked. We have almost no real LOCAL
quant-ladder data, so the finder needs synthetic DEMO data to be visible. Real data arrives later.
</context>

<deliverables>
1. DEMO dataset — synthetic, plausible, and GLARINGLY labelled:
   - ~5 local models, each across a quant ladder (FP16, Q8_0, Q5_K_M, Q4_K_M, Q3_K_M):
     Qwen3-32B, Llama-3.3-70B, Gemma-3-27B, Mistral-Small-24B, Phi-4-14B.
   - Plausible numbers (you choose exact values; keep them internally consistent):
       * vram_footprint_gb grows with params and bits (e.g. a 32B: FP16~64, Q8~34, Q5_K_M~23,
         Q4_K_M~19, Q3_K_M~15; a 70B is roughly 2x; a 14B roughly half).
       * a composite-style quality score on the SAME 0-100 scale as the anchors (anchors sit ~91-94),
         with locals lower (e.g. a 32B FP16 ~72-76) and DEGRADING monotonically as the quant drops
         (Q3 a few points below FP16); attach small plausible CIs.
       * tok/s RISES as the quant drops.
       * lane = answer-only; set quant_label; mark each demo run with a new OPTIONAL `demo: true` field.
   - Add the `demo` flag to the schema (optional, defaults false) and thread it through
     data_sources.json -> build_data.py -> public/data. KEEP the 4 real anchors and the real Qwen 9B
     EXACTLY as they are — do not alter any real run's numbers.
   - Make the synthetic data UNMISTAKABLE: `demo:true` in the data, a per-row "DEMO" badge, AND a
     site-wide banner: "Preview uses synthetic demo data — not real measurements (Track 2 will replace it)."
2. Home Rig-Match Finder (new web/components/rig-match-finder.tsx, wired into web/app/page.tsx):
   - Controls: VRAM tier selector [8/12/16/24/32/48 GB] (default 24), quant selector [Any + the ladder],
     lane toggle.
   - Output: a ranked list of LOCAL model x quant combos that FIT the selected VRAM, ranked by a
     conservative score (lower CI bound). Each row: model, quant, quality +/- CI, frontier-gap shown as
     "X% of top anchor", vram_footprint_gb, tok/s, and a verdict chip
     (best-under-budget / statistical tie / needs-replication / not-enough-data).
   - Anchors appear as a CEILING reference (a labelled strip/line: "frontier ceiling: GPT-5.5 92 ·
     Opus 92 · Gemini 94"), NEVER as ranked rows.
   - Cold-start grace: if a selection yields few/zero rows, show a coverage message + a "submit your run"
     CTA, plus a small BOUNTY block ("most-wanted runs -> copy CLI command").
   - Keep the EXISTING quality-vs-VRAM scatter PROMINENT immediately BELOW the finder (Michael wants it
     kept and visible, not hidden in a tab). Reuse components/model-scatter.tsx (generalise if needed).
3. Keep the existing leaderboard table reachable (move it below the finder + scatter, or behind a
   "full leaderboard" disclosure) — do NOT delete it.
</deliverables>

<constraints>
- Branch `site-overhaul` ONLY. NEVER commit to main.
- Do NOT change the CLI / scoring core or any REAL run's data. Demo data is purely ADDITIVE.
- Reuse existing tailwind tokens, next/font fonts, axis-config, badges, and the scatter component;
  match the dark design system. Keep it accessible and reasonably responsive.
- API keys / secrets: never read, echo, or commit them.
</constraints>

<verification_loop>
- `npm run typecheck` clean; `npm test` green (ADD tests for: the fit/rank logic, the frontier-gap
  computation, and the demo-flag plumbing); `npm run build` green.
- Verify the dev render: home leads with the finder; 24 GB shows demo rows ranked sensibly; the scatter
  renders below; the DEMO banner is visible; anchors show only as the ceiling.
- Commit per coherent step on site-overhaul with clear messages. Do not leave the tree broken.
</verification_loop>

<output_contract>
Return: files changed; the demo dataset summary (models x quants, sample VRAM/quality/tok-s); how the
finder computes fit + rank + frontier-gap; test results (typecheck/test/build); and any assumptions or
decisions. Note what remains for the follow-up tasks (quant-decision matrix on the model page; /compare).
</output_contract>
