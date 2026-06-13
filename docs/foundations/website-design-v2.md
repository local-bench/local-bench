# local-bench — Website Design Spec v2 (finder-first) — CANONICAL

*Approved direction: Michael, 2026-06-13, after a 4-model design red-team (GPT-5.5 xhigh, Gemini 3.1
Pro, Qwen 3.7 Max, independent Opus — ALL returned REVISE; critiques in `docs/foundations/redteam/`).
Supersedes `website-design.md` on IA + hero choices. The scoring stack + trust model there still hold.*

## The decision
**Finder-first, built hybrid.** Lead with a hardware-first *"what can I run on my GPU?"* finder; keep a
**prominent, polished quality-vs-VRAM scatter** on the page (Michael's call — not demoted to a tab). The
model page leads with a *"which quant should I run?"* decision matrix. Build the foundation + shell now;
the data-dependent hero numbers populate when **Track 2** delivers a discriminating suite + seeded
quant-ladder data.

## Why (red-team consensus, all four independently)
- A quality-vs-VRAM **scatter as the hero dies at cold-start** (4 anchors + a handful of local runs reads
  as an "empty ghost town"; CIs on a scatter become "illegible spaghetti" — anti-credible).
- **Lead with the decision, not the leaderboard:** the user's real question is *"I have 24 GB — what's the
  smartest thing I can run, at Q4?"* A short curated list reads as a *lab report*; a sparse scatter reads dead.
- **Anchors = a reference ceiling** ("82% of GPT-5.5"), never competitors to chase.
- **Aggregate by `[model + quant]`;** runtime/hardware are *provenance*, not separate rows ("sparse-matrix-of-death").
- **Biggest risk:** launching on sparse / non-discriminating data → dismissed as "AA clone with fewer rows."
  Mitigation: finder-first survives sparse data; gate the real launch on Track 2 (probe + seeded ladders).

## Information architecture
- **`/` Home — Rig-Match Finder** (VRAM + quant + lane selectors → ranked "what fits" list) → prominent
  scatter below → bounty board (cold-start scaffolding).
- **`/model/[slug]` — "Which quant should I run?" matrix** (FP16→Q3, Pareto sweet-spot) + per-axis profile + community receipts.
- **`/compare` — head-to-head model×quant diff** (the weekly-return hook).
- **`/run/[id]` — evidence receipt** (manifest + provenance hashes).
- **`/methodology` — credibility** (discrimination diagnostics, weights, no-LLM-judge, threat model; Trust folded in).
- **`/submit` — contribution funnel** (one CLI command; what uploads vs stays local).

## Home — Rig-Match Finder (numbers illustrative)
```
 WHAT CAN I RUN?   VRAM [ 24 GB ▾]   Quant [ Q4_K_M ▾]   Lane [ ▾ ]
 Best measured setups that fit 24 GB
  #  Model         Quant    Quality   vs GPT-5.5   VRAM   tok/s
  1  Qwen3 32B     Q4_K_M   71 ±2     78% ██████░  19GB   42
  2  Llama3.3 70B  IQ3_XXS  68 ±3     74% █████░░  22GB   18
     … needs replication    [ submit your 24 GB run ]
  ── ceiling ──  GPT-5.5 92 · Opus 92 · Gemini 94  (reference, not ranked)
 ▸ EXPLORE: quality-vs-VRAM scatter (all runs)  [prominent, expandable]
 ▸ BOUNTY: we need Q6_K for Command-R, FP16 for Gemma3 → [copy CLI]
```
Behaviour: selectors filter to model×quant combos that fit; rank by conservative score lower-bound; show
frontier gap, VRAM, tok/s, replicate count, and a verdict (best-under-budget / tie / needs-replication /
not-enough-data). Empty cells are useful ("no Q5 run yet → submit"), so it never looks broken.

## Model page — "Which quant should I run?" (numbers illustrative)
```
 Qwen3 32B
  Quant     Quality(±CI)   Δ vs FP16     VRAM    Fits   tok/s
  FP16       74 ±2         baseline      64 GB   48GB+   12
  Q8_0       73 ±2         −1.0 ±1.3     34 GB   48GB    20
  Q5_K_M     72 ±2     ★   −1.8 ±1.6     23 GB   24GB    31   ◀ SWEET SPOT
  Q4_K_M     71 ±2         −3.1 ±1.9     19 GB   24GB    42
  Q3_K_M     66 ±3         −7.9 ±2.4     15 GB   16GB    55
  ★ Best tradeoff: Q5_K_M keeps ~97% of FP16 quality at ~⅓ the VRAM
  [ coverage: Q6_K not yet measured ]   ▸ per-axis degradation   ▸ receipts (n)
```
Behaviour: paired quality delta vs FP16 with paired CIs; highlight the Pareto sweet-spot; **coverage card
when a quant/baseline is missing — never a broken/empty hero.**

## Resolved forks
- **Compare page:** build it (strongest weekly-return hook).
- **Charts:** keep the hand-rolled SVG for now (audit rated it well); revisit a library only if interactions demand.
- **Radar charts:** cut at launch (distort CIs; per-axis bars do it better).
- **Aggregation:** board groups by `[model + quant]`; runtime/hardware shown as provenance + flagged if they ever diverge quality.

## Data caveat (the hybrid gate)
The finder + matrix render **placeholder data** until Track 2 delivers (1) a suite that actually
discriminates (the discrimination probe / suite-v1) and (2) **seeded quant-ladder data we run ourselves**
— FP16 baselines + Q8/Q5/Q4/Q3 for a few base models (5090 for what fits; rented cloud for big-model FP16,
since the community can't run FP16). All current v0 data must be labelled "preview / pre-suite-v1."

## Build sequencing (hybrid)
**P1 Foundation** (axis-agnostic refactor + 14 design tokens + web fonts + copy/index_version) →
**P2 Structure** (AppShell/TopNav + breadcrumbs + `/submit` stub) → **[GATE: Michael reviews]** →
**P3 Heroes** (finder + quant matrix + compare) → **P4 Credibility+polish** (DiagnosticsPanel + responsive).
P1–P2 are design-layout-agnostic (safe to build now). Track 2 (probe + seed data) runs in parallel.
