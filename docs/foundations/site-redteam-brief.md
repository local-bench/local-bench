# local-bench — Website Design Red-Team Brief

*You are one of several independent frontier-model reviewers. Critique adversarially — attack the
design, do not flatter it. Be specific, opinionated, and ground every claim in the actual needs of
the audience. The goal is to decide WHAT the site should present BEFORE we build it.*

---

## 1. What local-bench is
A community **quality**-benchmark leaderboard for **LOCAL / open LLM setups**. A user runs a frozen
benchmark suite against their own rig — **model × quantization × runtime × hardware** — with one CLI
command pointed at any OpenAI-compatible endpoint (Ollama / vLLM / LM Studio / llama.cpp). Results
are server-scored and placed on boards and charts **alongside frontier "anchor" models measured on
the identical suite**. Tagline: *"Geekbench for local AI intelligence."*

## 2. The wedge (why anyone would use it)
The launch differentiator is a **quant-degradation dataset nobody else publishes**: *"what does
Q4_K_M actually cost YOUR model, measured, with confidence intervals."* Verified gaps in the market:
- **Artificial Analysis** — quality composites, but **API/datacenter models only**.
- **LocalScore** — community runs on local rigs, but **speed only** (tok/s), no quality.
- **HF Open LLM Leaderboard** — died on central-compute cost (our user-brings-compute model inverts that).

So nobody does community-run **quality** benchmarks on your **actual local setup**, anchored to
frontier. We measure **distance-to-frontier across the local range** — the frontier anchors are a
**reference ceiling**, NOT a frontier-vs-frontier ranking we try to win.

## 3. The audience
Local-LLM enthusiasts (think r/LocalLLaMA): people choosing a model + quant for their own 16–48 GB
consumer GPU, asking *"is Q4 good enough on my 3090?"*, *"what's the best model that fits 24 GB?"*,
*"how far is my local rig from GPT-5.5 / Claude / Gemini, really?"* They are technical, skeptical of
marketing, allergic to unverifiable numbers, and they already read AA and LocalScore.

## 4. The CURRENT design direction — CRITIQUE THIS
Dark-mode, Artificial-Analysis-inspired, **3-level information architecture**:
- **HOME**: all models ranked (composite sorts) **+ a quality-vs-VRAM scatter as the hero** above the
  table. Scatter has "what fits my card" VRAM-tier guide lines (8/12/16/24/32/48 GB), a lane toggle
  (reasoning / answer-only), and frontier anchors drawn as a dashed **reference ceiling**.
- **MODEL page**: hero is a **quant-degradation strip** — what each quant (Q4/Q5/Q8…) costs vs the
  FP16 baseline, with **paired confidence intervals** and a dominance verdict.
- **RUN DETAIL**: per-axis breakdown + the full hardware/config manifest + provenance hashes.
- Per-axis profile leads at depth; composite is the sortable summary. Reasoning lanes never merge;
  tokens + cost shown beside accuracy (never folded into the score).
- **CIs on every point** (AA does NOT show CIs on its Intelligence Index — we treat this as a
  differentiator). Hand-rolled SVG charts, dark-first palette.
- **Methodology + Trust pages**: trust = **replication, never "verified"** (a proxy that routes
  "local" calls to a frontier API defeats transcript verification, so we never claim cryptographic
  proof); published threat model. A **DiagnosticsPanel** shows measured anchor-spread / discrimination
  (our "we publish what AA doesn't" credibility moat).
- **Submit page**: the CLI contribution funnel (raw transcripts + manifest uploaded; server scores).

## 5. Hard constraints (any proposal must respect these)
- Data is **community-contributed** and **sparse at launch** (cold-start: maybe a handful of runs +
  4 frontier anchors on day one). The design must not look broken when near-empty.
- We are honest that the suite measures the **local range** vs a frontier ceiling — we are NOT
  crowning a local model as "the best AI." Don't propose anything that overclaims.
- No LLM-judge scoring; everything is programmatic + reproducible. (Affects what's chartable.)
- It must read as **credible to skeptics**, visually distinct from "AA but worse," and defensible vs
  AA / LocalScore.

## 6. YOUR TASK — attack, then rebuild
Answer these directly and concretely:
1. **Is this the right thing to present** for THIS audience and wedge? What is the single most
   compelling thing the **homepage should lead with** — and is a "quality-vs-VRAM scatter" actually
   it, or is something better (e.g. a *"find the best model for MY GPU"* finder; a quant-degradation
   table; a *"your rig vs frontier"* gauge; a model-vs-model diff)?
2. **What makes a local-LLM user bookmark this and come back weekly** vs dismiss it as another
   leaderboard / AA clone? Name the killer view.
3. **Is the quant-degradation strip the right MODEL-page hero**, or is it too niche / not the first
   thing people want to see?
4. **What is WRONG or risky** about the current direction — where will it fail to land, what's
   missing entirely, what's overbuilt (YAGNI)?
5. **Cold-start**: does the design survive a near-empty dataset? If not, what's the day-one design?
6. Propose the **ideal information design**: homepage lead + the 3–4 views that matter + what to CUT.

## 7. Output contract
Produce a structured markdown critique, ~1–1.5 pages, in this order:
- **VERDICT** (one line): KEEP current direction / REVISE / PIVOT — and the single highest-impact change.
- **Killer homepage lead** — what you'd put first, and why it beats the alternatives.
- **Model-page hero** — keep the quant strip or replace it; justify.
- **Biggest risk** — the one thing most likely to make this fail with the audience.
- **Cut list** — what to drop (be ruthless).
- **Concrete alternative IA** (only if you'd REVISE/PIVOT) — the pages + the lead view of each.
Ground every claim in the audience's real behavior. Prefer concrete examples over abstractions.
If you reference how AA / LocalScore / other leaderboards do something, be specific about what and why.
