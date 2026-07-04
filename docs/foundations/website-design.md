# local-bench — Website Design Specification

**Status:** design spec (not code) · **Target repo:** `<home>\local-bench\web` (Next.js static export, dark-only) · **Suite/index:** `suite-v1 · index-v2` · **Date:** 2026-06-13

---

## 0. Why this redesign exists

The v0 suite fails to discriminate (a 9B lands within ~6 composite points of frontier SOTA; Gemini "beats" Opus by acing saturated easy axes). The benchmark fix is a content rebuild (5-domain difficulty ladders, see the suite spec). **This document is the website fix.** The current site reads like "Artificial Analysis but worse": a composite-led, frontier-flavoured leaderboard. The redesign makes the homepage lead with the one thing AA structurally cannot show — **the measured, confidence-interval-bounded cost of quantization on your own model** — and exposes the credibility moat (every weight, formula, and saturation/discrimination diagnostic) that AA and LLM-Stats keep closed.

We build **on top of the existing prototype**, not from scratch. Already shipped and reused verbatim where noted:
- Dark palette tokens in `tailwind.config.ts` (`bench.bg/panel/line/text/muted/accent/anchor`).
- 3-level IA: `app/page.tsx` (home), `app/model/[slug]/page.tsx`, `app/run/[runId]/page.tsx`, `app/methodology/page.tsx`, `app/trust/page.tsx`.
- Hand-rolled SVG charts (`components/model-scatter.tsx`, `components/run-axis-breakdown.tsx`) and CSS bars (`components/score-bar.tsx`) — **no chart library**; this spec keeps that constraint so it is directly buildable.
- The persistent lane caveat copy (home header), the badges (`components/badges.tsx`), the manifest grid (`components/detail-grid.tsx`).

The single largest schema change: generalize the hard-coded 3 axes (`mmlu_pro`, `ifeval`, `genmath` in `lib/schemas.ts` line 3 and `home-leaderboard.tsx` line 10 `TABLE_AXES`) to the **5 recommended domains**: Knowledge & Reasoning / Math / Instruction-Following / Agentic / Coding.

---

## 1. Information architecture

Three depth levels (kept from the prototype) plus two trust/credibility pages and a contributor funnel:

```
HOME  (/)                       all setups ranked, ONE representative score each
  └─ MODEL  (/model/[slug])      one base model, ALL its quants on quality-vs-VRAM + quant-delta strip
       └─ RUN DETAIL (/run/[id]) one run: per-axis-per-rung, contamination canary, manifest, provenance
METHODOLOGY (/methodology)      every weight + formula + saturation/discrimination diagnostics
TRUST       (/trust)            threat model; replication is the trust unit, not "verified"
SUBMIT      (/submit)           CLI to contribute a run; what uploads; lane/tier rules
```

**Narrative spine:** HOME asks "what fits my GPU and how good is it?"; MODEL answers "what does each quant cost me, paired and CI-bounded?"; RUN DETAIL answers "can I trust and reproduce this one number?"; METHODOLOGY/TRUST answer "why should I believe the suite at all?".

---

## 2. Visual language

### 2.1 Palette (dark-only; hex)

Inherited tokens are marked **(shipped)**; new tokens are semantic state colours for the CI/quant-delta honesty layer.

| Token | Hex | Use |
|---|---|---|
| `bg` **(shipped)** | `#0b0e14` | page background |
| `panel` **(shipped)** | `#11161f` | cards, tables, chart plot fill |
| `panel-2` | `#0e131c` | nested/inset wells (depth without lighter grey) |
| `line` **(shipped)** | `#273244` | borders, gridlines |
| `line-strong` **(shipped)** | `#4a5568` | axis spines |
| `text` **(shipped)** | `#eef4fb` | primary text + numbers |
| `muted` **(shipped)** | `#99a7b8` | labels, secondary |
| `muted-2` | `#6b7a8d` | footnotes, tertiary, `~chance` hatch |
| `accent` **(shipped)** | `#32d2b4` | teal — community/open data, CTAs, focus, primary chart points |
| `accent-dim` | `#1f8a76` | teal hover/pressed |
| `anchor` **(shipped)** | `#f6b24b` | amber — **frontier anchors only** (dashed lines, anchor rows/ticks) |
| `anchor-soft` | `#f6d08d` | amber text on dark |
| `better` | `#46d39a` | quant-delta improves (verdict) |
| `worse` | `#ff6b6b` | quant-delta regresses (verdict) |
| `tied` | `#99a7b8` | within uncertainty (= `muted`) |
| `mixed` | `#c792ea` | mixed verdict (violet) |
| `lane-reasoning-edge` | `#7c83ff` | indigo border-only tint marking native-reasoning lane |
| `warn` **(shipped)** | `#fbbf24` on `rgba(251,191,36,0.08)` | lane caveats, data-quality notes |

**Colour discipline (the rule that makes charts honest):** magnitude is **always** position/length; verdict is **always** hue + shape. Greens/reds appear **only** as quant-delta verdicts, never as raw-magnitude fills. Verdict colours are paired with an icon (▲ better / ▼ worse / = tied / ◬ mixed) so colour is never the sole channel (deuteranopia-safe). Anchor amber is full-strength on lines but ~2.5% on row tints, so anchor rows read as *reference*, not *alert*. Contrast: text 14.8:1, muted 6.9:1, accent 7.1:1 on `bg`.

### 2.2 Typography

Two CSS-var families (already wired in `layout.tsx`): **Inter** (`--font-sans`) for prose/labels/headings; a **tabular-figures mono** (`--font-mono`, JetBrains Mono / `ui-monospace`) for **every number, score, CI, hash, run-id, token count**. Tabular mono is non-negotiable: score columns must align and a CI like `±1.9` must never reflow.

Scale (rem): display 2.5 (home H1) · h1 2.25 (model name) · run-composite headline 3.75 (60px, shipped) · h2 1.5 · h3 1.125 (card titles) · body 1 · small 0.875 (cells/captions) · micro 0.6875 (uppercase eyebrow + badges, tracked +0.04em — the shipped label treatment). Headline metrics: mono + 600. Tabular numbers: mono + 400. Version stamps reuse the shipped `font-mono text-xs uppercase text-bench-accent` motif as `suite-v{n} · index-v{n}` on every page.

### 2.3 What we borrow from AA, and how we differ

**Borrowed (component-level):** 0–100 composite index; the signature quadrant **scatter** as hero; hierarchical category weighting (AA 4×25% → our 5 domains); open-vs-proprietary visual split (→ community-teal vs anchor-amber); sortable per-eval table; per-model + methodology pages; reasoning-effort in the model label; cost-to-run economics; headroom buffering so the frontier doesn't pin the ceiling.

**How we differ (the anti-"AA-but-worse" moves):**
1. **Hero is the local/quant wedge, not a frontier index.** AA's landing default is a ranked frontier table with intelligence-vs-**price** as a variant (verified Jun 2026: "28 of 538 models", "Intelligence vs Cost to Run" quadrant). Ours leads with **intelligence-vs-VRAM** — "what does Q4 cost YOUR model on YOUR GPU, measured." Price is AA's axis because their user picks an API; VRAM/quant is ours because our user picks a deployable local setup.
2. **CIs are first-class everywhere.** AA treats its <±1% composite CI as negligible and shows visible error bars only on its preference Arena, not the Intelligence Index scatter (verified). We draw a CI on **every** score — table cells, scatter points, axis bars, and especially the paired quant-deltas.
3. **Paired-delta honesty rule as a UI primitive.** The quant-delta is always a **paired** comparison on fixed items with its **paired** CI, scoped "on suite-v1 fixed items", rendered as a dominance verdict — never a universal percentage, never two independent CIs subtracted.
4. **Strict reasoning lanes, never merged.** AA folds reasoning/non-reasoning into one index and footnotes token burn; we split lanes hard, keep a persistent lane caveat on every leaderboard view, and show tokens/cost **beside** accuracy.
5. **Saturation/discrimination diagnostics published** (anchor spread, S_index, point-biserial/IRT) — the moat AA/LLM-Stats don't open.
6. **Decomposition over composite:** the per-axis profile is the headline; the composite is only the sortable summary.
7. **Contamination canary made visible:** the public-vs-private-sentinel gap is charted on run detail.

### 2.4 Dark-mode build notes

Dark is the only mode (no toggle). Depth via three stacked surfaces (`bg < panel-2 < panel`) + 1px `line` borders + the shipped soft black shadow on the primary table — never elevation via lighter grey fills (washes out on OLED). Plot areas: `panel` fill, `line` gridlines ~1px, `line-strong` spines. Glows are a focusing device only (the shipped axis-point teal glow `0 0 14px rgba(50,210,180,0.65)` is reused by the quant-delta verdict chips and the selected scatter point). `~chance` renders as a 45° hatch in `muted-2` over a **hollow** marker (visually "not a real point"), never a solid dot below the chance line.

---

## 3. Pages

### 3.1 HOME — Local leaderboard (`/`)

**Purpose:** lead with the local/quantization wedge; the quality-vs-VRAM scatter + per-axis profile are the headline, the composite is the sortable summary. Must not read as an AA frontier-index clone.

```
+--------------------------------------------------------------------------------------+
| local-bench            Leaderboard · Methodology · Trust · [Submit a run]   suite-v1  |
+--------------------------------------------------------------------------------------+
| suite-v1 · index-v2                                                                   |
| H1  Local AI quality leaderboard — measured, with confidence intervals               |
| Sub  Every setup on the same frozen suite across 5 domains. The headline is the       |
|      quant cost on YOUR model; the composite is just the sortable summary.            |
|                                                                                       |
| [ ! Quick = personal estimate, UNRANKED. Standard is the ranked board; ranks only     |
|     within a reasoning lane. Rows sorted for browsing only. ]   <- LaneCaveatBanner    |
+--------------------------------------------------------------------------------------+
| HERO: QUALITY vs VRAM                          | lane:[answer-only|native-reasoning]  |
|  100|------------------------------------------|  - - - - Opus 4.8  82  (anchor)       |
|     |        8  12  16   24    32      48 GB    |  - - - - GPT-5.5   80                 |
|  80 |- - - - - - - - - - - - - - - - - - - - - -|  - - - - Gemini    78                 |
|     |   (most attractive: top-LEFT)            |                                       |
|  60 |        o-+   o (CI whisker)   o          |  o community run (teal, 95% CI)        |
|     |        Q4    Q5_K_M          bf16        |  vertical bar = 95% CI                 |
|  40 |   o                                      |  dashed amber = frontier anchor       |
|     +------------------------------------------|  y headroom-buffered (SOTA~80)        |
|       model memory footprint (GB) [lin|log]    |                                       |
+--------------------------------------------------------------------------------------+
| FilterBar: [community|anchor]  lane[v]  tier[v]  VRAM<=[==24GB==]  search[__________]  |
+--------------------------------------------------------------------------------------+
| Rank | Model            | Kind | Composite | Know | Math | IF | Agent | Code | Tier  |
|      |                  |      |  +CI bar  | bar  | bar  |bar |  bar  | bar  | Lane  |
|------+------------------+------+-----------+------+------+----+-------+------+-------|
|  1   | Opus 4.8         |ANCHOR| 82 ±0.9   | 88   | 71   | 90 |  79   |  74  | Std   |
|  --  | Qwen3.5 9B  N=3  | COMM | 71 ±1.0   | 75   | ~ch  | 83 |  66   |  61  | Quick |
|      |  ... sortable, tokens + cost columns to the right (mono) ...                   |
+--------------------------------------------------------------------------------------+
| Footnote: composite = domain-weighted mean of chance-corrected axes, within lane.     |
| Tokens/cost shown beside accuracy, never folded in. See Methodology for every weight. |
+--------------------------------------------------------------------------------------+
```

**Key components:** TopNav · VersionStamp · LaneCaveatBanner · QualityVsVramScatter (hero, lane-switchable, VRAM tier guides, anchor reference lines) · FilterBar · LeaderboardTable (5 domain columns + composite + tier + lane + tokens + cost + rank-within-lane) · AxisMiniBar×5 · ScoreBar · KindBadge/TierBadge/LaneBadge/ReplicatedBadge · RankMarker.

**Charts:** QualityVsVramScatter (hero); in-table composite ScoreBar + 5× AxisMiniBar.

### 3.2 MODEL — one base model, all quants (`/model/[slug]`)

**Purpose:** all quants on a per-model quality-vs-VRAM scatter against frontier anchors, **plus the launch hero**: the QUANT-DEGRADATION STRIP of paired deltas with paired CIs and dominance verdicts. Also the per-axis profile, the REPORTED shelf, and the runs table.

```
+--------------------------------------------------------------------------------------+
| < Back to leaderboard                                                       suite-v1  |
| [COMMUNITY · N=7 runs]   [replicated]                                                  |
| H1  Qwen3.5 9B                          lane:[answer-only | native-reasoning]          |
| Sub All quants for this model vs frontier anchor reference lines.                      |
+--------------------------------------------------------------------------------------+
| QUANT-DEGRADATION STRIP  (vs bf16 baseline, on suite-v1 fixed items)  [delta|absolute]|
|   bf16   |================================ 0 (baseline)                                |
|   Q8_0   |                      [--o--]  -0.4 +/- 1.1   = tied (within uncertainty)    |
|   Q5_K_M |                 [---o---]      -1.8 +/- 1.6   v worse (within uncertainty)  |
|   Q4_K_M |          [----o----]           -4.6 +/- 1.9   v worse                       |
|   Q3_K_M |   [-----o-----]                -9.2 +/- 2.3   v worse  (+ -41% tokens)      |
|          -15 ......... -5 ....... 0 ..... +5   composite delta (paired)               |
|   [expand a quant -> its 5 per-domain paired deltas: Know = / Math v / IF = ...]       |
+--------------------------------------------------------------------------------------+
| QUALITY vs VRAM (this model)                    | - - Opus 82  - - GPT-5.5 80  ...     |
|  100|------------------------------------------|                                       |
|   80|- - - - - - - - - - - - - - - - - - - - - |  o each quant w/ 95% CI whisker        |
|   60|     o(Q3) o(Q4)  o(Q5) o(Q8) o(bf16)      |  x grows with footprint               |
|     +------------------------------------------|                                       |
|        4    6     8    10    16  GB                                                    |
+--------------------------------------------------------------------------------------+
| PER-AXIS PROFILE (best run)         [bars | radar]      worst axis: Math (amber)       |
|  Knowledge 25% |##########====| 75 +/-3                                                |
|  Agentic   20% |########==|     66 +/-4                                                |
|  IF        20% |###########=|   83 +/-4                                                |
|  Math      20% |##~chance~|      ~chance                                               |
|  Coding    15% |#######=|       61 +/-5                                                |
+--------------------------------------------------------------------------------------+
| REPORTED ELSEWHERE (not measured here)  -- labeled, never charted on a measured axis   |
|  SWE-bench Verified .. GPQA Diamond .. HLE .. Aider .. LiveCodeBench   [source links]  |
+--------------------------------------------------------------------------------------+
| RUNS  (run -> /run/<id>)                                                               |
|  run_id | quant | footprint | composite+CI | 5 axes | tier | lane | tok | tok/s | $ | hw|
+--------------------------------------------------------------------------------------+
```

**Key components:** TopNav · VersionStamp · KindBadge/ReplicatedBadge · lane segmented control · **QuantDeltaStrip** (launch hero) · QualityVsVramScatter (per-model) · PerAxisProfile (bars/radar, worst-axis highlight) · ReportedShelf · RunsTable · LaneCaveatBanner · TokenEconomicsInline.

**Charts:** QuantDeltaStrip; QualityVsVramScatter (per-model); PerAxisProfile / AxisRadar.

### 3.3 RUN DETAIL — one run, full provenance (`/run/[runId]`)

**Purpose:** per-axis-per-rung profile, the public-vs-private contamination canary, tokens/cost/latency, conservative-ranking note for thin coverage, full manifest + provenance hashes. Everything to trust and reproduce one number.

```
+--------------------------------------------------------------------------------------+
| < Back to model                                                            suite-v1   |
| suite-v1 · index-v2                                                                    |
| H1  Qwen3.5 9B   run_id: qwen3-5-9b__q4-var1                                           |
|                                                                                       |
|   71.0   +/-1.0  95% CI     composite, chance-corrected, native-reasoning lane         |
|   [ ! data-quality: 0 errors, 4 no-answer items ]                                      |
|   [ conservative ranking applied: thin coverage -> mu - 3*sigma ]                      |
+--------------------------------------------------------------------------------------+
| AXIS x RUNG BREAKDOWN                                   worst axis: Math (amber)       |
|  Knowledge & Reasoning  75 +/-3                                                        |
|     SuperGPQA easy   |############| 81           middle |######| 49   hard |##~ch~|     |
|     MMLU-Pro (floor) |##########| 75             BBEH-mini (stretch) |##| ~chance       |
|  Math  ~chance                                                                        |
|     generated-v2 |####| 38   MathArena-fresh |#| ~ch   Olympiad |#| ~ch                 |
|  Agentic (BFCL-AST) 66 +/-4                                                            |
|     simple |#######| multiple|#####| parallel|####| relevance|######| irrel|#####|     |
|  Instruction-Following 83   |  Coding (CRUXEval-O) 61                                  |
+--------------------------------------------------------------------------------------+
| CONTAMINATION CANARY                                                                   |
|   public set 38  vs  private sentinel 36   gap +2  [ canary clean ]                    |
|   (a large public>>private gap = contamination / answer-lookup / gaming)               |
+--------------------------------------------------------------------------------------+
| TOKEN ECONOMICS    median 452 tok-to-answer · p95 2387 · 302 tok/s · $-- · wall 9.4m   |
+--------------------------------------------------------------------------------------+
| MANIFEST  (DetailGrid)                                                                 |
|  model | quant Q4_K_M | runtime vLLM 0.x | hardware RTX 5090 31.8GB | os Win11          |
|  lane native-reasoning | thinking_mode on | caps {mcq:4096,...} | sampling temp/min_p   |
|  tokens prompt/compl/total | tok-to-answer med/p95 | tok/s | wall-time | est-cost       |
+--------------------------------------------------------------------------------------+
| PROVENANCE   suite_version: suite-v1   index_version: index-v2                         |
|   mmlu_pro      sha256: ....    supergpqa  sha256: ....   bfcl_ast sha256: ....         |
|   ifbench       sha256: ....    cruxeval_o sha256: ....   genmath  sha256: ....         |
+--------------------------------------------------------------------------------------+
```

**Key components:** TopNav · VersionStamp (suite + index) · CompositeScoreHeadline (60px) · data-quality note (conditional) · conservative-ranking note (μ−3σ, conditional) · RunAxisBreakdown + RungBreakdown (worst-axis highlight) · ContaminationChip + public-vs-private panel · TokenEconomicsInline · ManifestCard · ProvenanceList.

**Charts:** AxisRungBreakdown; public-vs-private sentinel mini-bars.

### 3.4 METHODOLOGY — the credibility moat (`/methodology`)

**Purpose:** publish every domain + per-bench weight (index-v2), the absolute chance-corrected normalization with each bench's chance baseline, the bootstrap CI method + three estimands, the strict lane policy, the sentinel framing, and the saturation/discrimination **diagnostics**.

```
| 1 DECOMPOSITION FIRST — per-axis profile is the headline; composite is summary.        |
| 2 WEIGHTS (index-v2)  WeightsTable                                                      |
|    Knowledge&Reasoning 25% = SuperGPQA 15 + MMLU-Pro 6.25 + BBEH-mini 3.75             |
|    Math 20% = genmath-v2 10 + MathArena-fresh 7 + Omni/Olympiad 3                       |
|    Instruction 20% = IFBench 13 + IFEval 7   Agentic 20% = BFCL-AST 20                  |
|    Coding 15% = CRUXEval-O 15      [weight follows discrimination; saturated -> cut]    |
| 3 NORMALIZATION  signed=(raw-c)/(1-c); c per bench (MMLU-Pro .10, SuperGPQA ~.10,      |
|    BBEH ~0, IF/genmath 0, BFCL-AST ~0, CRUXEval-O ~0, MathArena 0). No clamp pre-agg.   |
| 4 UNCERTAINTY  clustered bootstrap; 3 estimands (repeatability/paired-delta/general).   |
|    '~chance' when CI crosses chance. Marketing may not outrun the paired CI.            |
| 5 LANES  strict; composite within-lane only; tokens/cost beside accuracy.              |
| 6 DIAGNOSTICS  anchor-spread per axis [floor|==anchors=|ceiling] · S_index · discrim.   |
| 7 VERSIONING  suite-v{n} tags item-sets; index-v{n} tags weights; quarterly sat. gate.  |
```

**Key components:** WeightsTable (versioned) · normalization formula block (mono) · three-estimands explainer · lane-policy explainer · **DiagnosticsPanel** (anchor-spread bars, S_index gauge, discrimination strip) · versioning/saturation-gate explainer.

**Charts:** DiagnosticsPanel.

### 3.5 TRUST — threat model (`/trust`)

**Purpose:** a transcript is never proof of identity; the trust unit is **replication**. Explains the cheat-proxy attack, what server-side signals can/can't prove, and how the private sentinel + independent replication raise trust. Defines the badge labels used everywhere.

**Key components:** label-definition cards (community-reported / replicated / anchor, reusing KindBadge/ReplicatedBadge) · cheat-proxy explainer · trust-improvement explainer. **Charts:** none.

### 3.6 SUBMIT — contribute a run (`/submit`)

**Purpose:** contributor funnel + integrity gate. The exact CLI to run the frozen suite via an OpenAI-compatible endpoint; what uploads (manifest + per-item scores + versions + SHAs, **not** the user's prompts/data); lane/tier rules (Quick=unranked, declare your lane, footprint recommended for the VRAM scatter); the replicated path.

**Key components:** copyable code block (mono) · upload-manifest explainer · tier/lane rules · ReplicatedBadge-path explainer. **Charts:** none.

---

## 4. Chart specifications

All charts are hand-rolled SVG + Tailwind (no chart lib), matching `components/model-scatter.tsx` and `components/run-axis-breakdown.tsx`.

### 4.1 QualityVsVramScatter — FLAGSHIP (home hero + per-model)

- **X:** model memory footprint (GB) = weights + KV at the run's context — the *deployability* axis. Linear default with a **log** toggle on home (footprints span ~3 → 80+ GB; log keeps the 8–48 GB consumer band readable). X-domain padded 8% (the shipped `getXDomain`). On home, faint **vertical VRAM-tier guides** at 8/12/16/24/32/48 GB labeled along the top → reads "what fits my card" directly.
- **Y:** composite (0–100), chance-corrected, **within one lane**. **Headroom-buffered for display** so current frontier-anchor SOTA maps to ~80/100 (LLM-Stats 1.25); raw chance-corrected values stay internal for delta math. Gridlines 0/25/50/75/100 (shipped `Y_TICKS`); rotated title "composite (within lane)".
- **Most attractive quadrant = TOP-LEFT** (high quality, low VRAM) — annotated once with a faint "better →" hint (inverts AA's low-price intuition onto our axis).
- **CIs:** every community point = filled teal circle (r6, dark stroke) with a **vertical 95% CI whisker** (capped I-bar: line hi→lo + 12px caps — the shipped construction at `model-scatter.tsx` lines 89–93). CI crossing chance → hollow hatched marker + `~chance` tag. Anchors carry no whisker on their line (references, not measured-against points); their dashed line is 1.5px; tooltip exposes the anchor's own CI.
- **Lanes:** renders **one lane at a time** (segmented control above; active lane named in subtitle + y-title). Native-reasoning points carry the indigo lane-edge ring; answer-only are plain teal. Switching lanes re-fetches that lane's points + anchor lines — lanes never co-plot. Each point's hover card shows tokens-to-answer + est-cost. Anchor reference lines: dashed amber, right-margin-labeled `<model> <score>`, vertically de-collided (shipped `layoutAnchors`).

### 4.2 PerAxisProfile — the headline decomposition (model & run)

- **Default:** five stacked horizontal 0–100 CI bars, one per domain, ordered by index-v2 domain weight (heaviest top), with the weight printed as a faint right tag (extends the shipped `AxisWhisker`). **Radar toggle:** 5 spokes 0(center)→100(rim), score polygon filled teal at low opacity + a fainter dashed-amber anchor-median polygon. Bars are default because CIs are honest on a linear track and distorted on a radar; radar is offered for "shape of capability" at a glance.
- **CIs:** translucent teal band (left=lo, width=hi−lo) + bright 1px point marker with the shipped teal glow (`run-axis-breakdown.tsx` lines 51–60). CI crossing the axis chance baseline → hatched `~chance` segment + `~chance` numeric. Worst axis highlighted amber.
- **Lanes:** per-lane (segmented control switches the whole profile). A compact tokens/cost micro-stat sits beside each domain score so a domain "won" only by burning tokens is visible.

### 4.3 QuantDeltaStrip — the LAUNCH HERO (model page, NEW)

- **Axes:** one row per quant comparison for one base model, on a shared **signed-delta axis centered on 0** (e.g. −15 … 0 … +5 composite pts). **DELTA framing default** (each quant a point at quant−baseline — the honest paired quantity); **ABSOLUTE framing toggle** (dumbbell: baseline marker → quant composite, showing both level and drop). X-title: "composite delta vs `<baseline>`, on suite-v{n} fixed items." A row expands into its 5 per-domain deltas.
- **CIs — the central honesty object:** each delta point carries a **paired** 80/95% CI bracket from paired bootstrap / McNemar on item-level discordance (**never** two independent CIs subtracted) — the ~1.9pt paired MDE vs ~13pt unpaired is the whole reason this chart exists. Reference line at 0 solid; CI overlapping 0 → "= tied (within uncertainty)"; entirely left → "▼ worse" (coral); entirely right → "▲ better" (green-teal); per-domain rows disagreeing → parent "◬ mixed" (violet). Each row literally prints `on suite-v{n} fixed items, −X.X ± [paired CI]` — never a universal %.
- **Lanes:** deltas computed **within a lane** (cross-lane pairs greyed out). Token/cost delta shown as a **separate** secondary dumbbell (e.g. "−2.1 pts, −38% tok"), never combined into one number.

### 4.4 AxisRungBreakdown (run detail)

- **Axes:** each domain's parent bar expands into child **rung** bars on the same 0–100 track, ordered easy→hard: Knowledge → SuperGPQA easy/middle/hard + MMLU-Pro(floor) + BBEH-mini(stretch); Math → genmath-v2 / MathArena-fresh / Omni-Olympiad; Agentic → BFCL simple/multiple/parallel/relevance/irrelevance; Coding → CRUXEval-O. Anchor median per rung = faint amber tick.
- **CIs:** each rung bar has its own CI band + point; small-n rungs commonly render `~chance` (hatched). Parent bar = weighted roll-up with CI.
- **Lanes:** the run's single lane; tokens/cost in the axis header.

### 4.5 DiagnosticsPanel (methodology — NEW)

- **(1) Anchor-spread per axis:** horizontal float bar local-floor→frontier-ceiling per domain (short bar = saturating → weight-cut candidate); anchors drawn as individual amber ticks so "all within ~1 pt" is literally visible as ticks bunching. **(2) S_index gauge** per axis: `S_index = exp(−R_norm²)` 0..1, green→red, with the "all anchors within ~1 pt" threshold marked. **(3) Discrimination strip:** per-axis point-biserial / IRT-α heat-bar (grey→teal), the internal 2PL early-warning surfaced read-only.
- **Lanes:** per-lane; defaults to answer-only with a toggle.

### 4.6 LeaderboardCompositeColumn + AxisMiniBars (home table)

- Composite column = ScoreBar (mono score + inline CI + magnitude bar). Five domain columns = AxisMiniBar (mono score + inline CI + thin bar). Tokens/cost mono. Rank = rank-within-lane or "Unranked".
- **CIs:** inline in every cell (`formatCi`); mini-bar shows magnitude only; `~chance` substitutes the number when a cell CI crosses chance.
- **Lanes:** Lane column + LaneBadge; FilterBar lane selector filters to one lane for true ranking; "all lanes" is browse-only with the persistent caveat. Anchor rows tinted amber; community plain.

---

## 5. Component inventory (build list)

**Shell/nav:** AppShell · TopNav · VersionStamp · LaneCaveatBanner · FilterBar · EmptyState · inline Footnote/Caveat.
**Badges/chips:** KindBadge *(shipped)* · TierBadge *(shipped)* · LaneBadge *(shipped, +lane tint)* · ReplicatedBadge *(new)* · DominanceChip *(new)* · ContaminationChip *(new)*.
**Score primitives:** ScoreCell · ScoreBar *(shipped)* · AxisMiniBar *(shipped, +inline CI)* · CompositeScoreHeadline *(shipped)* · TokenEconomicsInline.
**Charts:** QualityVsVramScatter *(extends ModelScatter)* · AnchorReferenceLines *(extracted)* · PerAxisProfile *(new)* · AxisRadar *(new)* · QuantDeltaStrip *(new, hero)* · AxisRungBreakdown *(extends RunAxisBreakdown)* · DiagnosticsPanel *(new)*.
**Tables:** LeaderboardTable *(generalizes HomeLeaderboard)* · SortableHeader *(shipped)* · RankMarker *(shipped)* · RunsTable *(shipped)*.
**Detail:** ReportedShelf *(new)* · ManifestCard *(shipped)* · DetailGrid/DetailItem *(shipped)* · ProvenanceList *(shipped)* · WeightsTable *(new)*.

---

## 6. Data-model deltas required (for the engineering handoff)

The design assumes these additions to `lib/schemas.ts` / `web/build_data.py` (out of scope to implement here, but the UI depends on them):
1. **5-domain axes** replacing the fixed `{mmlu_pro, ifeval, genmath}` `AxesSchema` — keyed by domain (`knowledge`, `math`, `instruction`, `agentic`, `coding`) with each domain carrying its constituent **bench/rung** sub-scores (for AxisRungBreakdown) and a chance baseline `c`.
2. **`index_version`** alongside `suite_version` on every run/model/index (VersionStamp renders both).
3. **Paired-delta records** on the model payload: for each (quant, baseline, lane) a `{delta_point, paired_ci_lo, paired_ci_hi, verdict, per_domain[]}` object (QuantDeltaStrip). Must be computed paired on fixed items server-side — the UI never subtracts two CIs.
4. **Contamination canary** fields on run detail: `{public_score, private_score, gap}` per applicable axis.
5. **Reported-elsewhere** list on the model payload: `[{bench, value, source_url, as_of}]` for the ReportedShelf (rendered as text, never charted).
6. **Diagnostics** payload for methodology: per-axis `{floor, ceiling, anchor_ticks[], s_index, discrimination}` per lane.
7. **Lane-scoped queries:** index/model data must be filterable by lane without merging (scatter, profile, deltas all render one lane at a time).

---

## 7. Build order (suggested)

1. Generalize schema + `TABLE_AXES` to 5 domains; ship LeaderboardTable + AxisMiniBars + VersionStamp(index) → home table is correct.
2. Promote QualityVsVramScatter to the **home hero** with VRAM-tier guides, lane switch, headroom-buffered y.
3. Build **QuantDeltaStrip** (launch hero) — the single highest-value differentiator; gate it behind real multi-quant data.
4. PerAxisProfile (bars) + AxisRungBreakdown on model/run.
5. ContaminationChip + ReportedShelf + conservative-ranking note on run detail.
6. DiagnosticsPanel + WeightsTable on methodology; expand Trust label cards; add Submit page.
7. FilterBar (community/anchor, lane, tier, VRAM-budget slider, search) once row count grows.

**Honesty invariants the UI must never break:** (a) a quant claim is always paired + scoped "on suite-v{n} fixed items"; (b) `~chance` replaces any sub-chance point whose CI crosses chance; (c) lanes never merge and tokens/cost never fold into the capability number; (d) the per-axis profile is shown before/above the composite; (e) every score carries a visible CI.
