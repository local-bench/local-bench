<task>
Build the local-bench web PROTOTYPE: a Next.js (App Router) + TypeScript + Tailwind site, DARK
MODE BY DEFAULT, that reads the static JSON produced by web/build_data.py (see
docs/briefs/task-11-web-data-pipeline.md and the actual files under web/public/data/). This is a
local prototype — NO Supabase, NO auth, NO database. It runs with `npm run dev` and must pass
`npm run build` (static export friendly).

The product is a community quality-benchmark leaderboard for LOCAL AI setups, anchored against
frontier models run through the identical frozen suite (suite-v0). Three axes: MMLU-Pro (knowledge/
reasoning, 10% chance baseline), IFEval (instruction following), genmath (generated math). Composite
= equal-weighted mean of chance-corrected per-axis scores, shown 0..100 with a 95% bootstrap CI.

INFORMATION ARCHITECTURE — three zoom levels (this is the spine, build exactly this):
1. HOME `/` — every model ranked against each other, ONE representative (best) run each. Read
   web/public/data/index.json. A sortable leaderboard table: rank, model (links to model page),
   kind badge (Anchor / Community — do NOT show a "Replicated" badge: true replication needs >=3
   INDEPENDENT accounts and we have none yet; community models show "Community-reported" + run count
   N. "Replicated" is described on /trust as a future signal only), composite as "NN.N" with a "±X.X" CI and a small
   horizontal score bar, the three axis values (compact, each with its own faint bar), tier badge,
   lane, tokens-to-answer (median), est. cost. Default sort = composite desc. AA-style density.
   A short header: what the suite is + a link to /methodology. PROMINENT honest note: "Quick tier =
   personal estimate, UNRANKED; Standard tier is the ranked board." Anchors visually distinct.
2. MODEL `/model/[slug]` — one model, ALL its runs/quants on a SCATTER (this is the AA-style
   "where does your setup land" view). Read web/public/data/models/<slug>.json. X-axis =
   vram_footprint_gb (model memory footprint), Y-axis = composite (0..100). Community runs =
   points WITH vertical 95% CI error bars; runs with null vram_footprint_gb are listed in the table
   but omitted from the scatter x (note this). Anchors (kind=anchor, null footprint) = horizontal
   dashed REFERENCE LINES across the chart, labeled with the model name — the local-vs-frontier
   comparison. Below the scatter, a runs table (quant, footprint, composite±CI, axes, lane,
   tokens-to-answer, tok/s, cost, hardware) with each run linking to its run-detail page. Framing:
   "where your run lands vs other quants and the frontier anchors".
3. RUN DETAIL `/run/[runId]` — per-axis breakdown. Read web/public/data/runs/<runId>.json. Top:
   composite NN.N ±CI big. Then the THREE axes as horizontal bars with point + CI whiskers, the
   WORST axis highlighted (worst_axis field). A manifest card: model, quant, runtime (name/version/
   kv-cache/ctx), hardware (gpu+vram, os), lane, thinking_mode, caps, sampling, tokens (prompt/
   completion/total + tokens-to-answer median/p95), tok/s, wall-time, est cost, n_items, n_errors,
   n_no_answer. Footer: suite_version + item_set_hashes (provenance). Honest data-quality note if
   n_errors or n_no_answer > 0.

ALSO:
- `/methodology` — render a concise methodology page from the substance of docs/scoring-methodology.md:
  the three estimands (repeatability vs paired quant-delta vs generalization), chance-corrected
  absolute normalization, reasoning lanes (native/capped/answer-only), fixed item sets + CIs,
  Quick(unranked)/Standard(ranked) tiers, weights are editorial/versioned. Keep it readable, not a
  raw dump. Link back home.
- `/trust` — trust/threat model from docs/threat-model.md substance: trust unit = REPLICATION (never
  "verified"); a proxy can fake any transcript (cheat-proxy proven), so labels are community-reported
  / Replicated (>=3 independent) / Anchor; server-side scoring + plausibility filters are signal not
  proof; generated-math private sentinel as contamination canary. Honesty as credibility.

DESIGN: dark-first palette that screenshots well (deep neutral background ~#0b0e14, card ~#11161f,
text high-contrast, ONE accent for bars/Pareto/links e.g. a cyan/emerald, muted gridlines, distinct
anchor color for reference lines). Tailwind. Responsive but desktop-first (this is a data site).
Charts: prefer a SMALL dependency-light approach — hand-rolled SVG scatter/bars give full dark
control and screenshot crisply; a tiny lib is acceptable only if it stays light. NO heavy chart
framework. Numbers are the hero: tabular-nums, generous whitespace in tables, clear CI rendering.

DATA ACCESS: read the static JSON via server components (fs read of web/public/data at build/request
time) and use generateStaticParams for /model/[slug] and /run/[runId] from index.json + the models
files. The site must be fully static-build-able.
</task>

<action_safety>
Work ONLY inside web/ (create web/package.json, web/app/**, web/components/**, web/lib/**,
web/tailwind config, web/tsconfig, etc.). Do NOT modify web/build_data.py, web/data_sources.json,
web/public/data/** (consume them read-only), and do NOT touch cli/, suite/, scoring/, docs/. Scaffold
Next NON-INTERACTIVELY (write package.json + config files directly; do not run `create-next-app`
interactively). No git commits.
</action_safety>

<completeness_contract>
Done = `npm install` then `npm run build` BOTH succeed from web/ (SSG build passing proves every
page renders without throwing against the real data files); `npm run dev` serves. All three IA levels
+ /methodology + /trust exist and read the real web/public/data JSON. Home lists every model in
index.json; each model page scatters its runs + draws anchor reference lines; each run page shows the
three axes with CIs + manifest. Dark mode is the default with no flash of light.
</completeness_contract>

<verification_loop>
After building: run `npm run build` and ensure exit 0 with all routes compiled. Start `npm run dev`
on a fixed port and curl `/`, `/methodology`, `/trust`, one `/model/<slug>`, and one `/run/<runId>`
(derive slugs/ids from web/public/data/index.json) — each must return HTTP 200 with expected content
(model label, the word "composite", CI markers). Fix any route that errors or any page that renders
empty before finishing. Report the exact slugs/ids you tested.
</verification_loop>

<missing_context_gating>No questions. If a data field is missing/null, degrade gracefully (show
"—" or "API" / "n/a") and note the choice in a code comment. Pick Next/Tailwind versions that build
cleanly on Node 24.</missing_context_gating>

<compact_output_contract>
Final: (1) files/dirs created (tree depth 2), (2) the `npm run build` result line + the routes
compiled, (3) the curl checks you ran with status codes, (4) <=6 bullets: chart approach chosen,
how anchor reference lines are drawn, dark-mode mechanism, any data field that needed graceful
fallback, and what a reviewer should look at first.
</compact_output_contract>
