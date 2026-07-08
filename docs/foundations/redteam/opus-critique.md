# local-bench — Website Design Red-Team (Opus, independent reviewer)

*Adversarial critique of `website-design.md` against the brief's Section 6/7. I read the spec, the
handoff, the audit, AND the actual seed data in `web/public/data/`. The seed data changed my
verdict: the design is critiquing a product it cannot show on day one.*

---

## VERDICT

**REVISE — hard.** The IA is mostly right and the honesty primitives are genuinely differentiating,
but the design leads with **two heroes (the VRAM scatter on home, the QuantDeltaStrip on model) that
are both empty or illegal at launch** with the real seed dataset. The single highest-impact change:
**demote the scatter to "supporting" and lead the homepage with a single-model, fully-populated
"quant-degradation explainer" using your own RTX 5090 + the four anchors — a worked example, not a
leaderboard.** The wedge is a *claim about a method*; on day one you must teach the method on one
model, not render a sparse board that quietly reproduces the v0 non-discrimination failure in chart
form. Everything else (CIs everywhere, lanes-never-merge, diagnostics moat) is keep-worthy.

---

## The fact that reframes everything: I read the day-one data

`web/public/data/index.json` is the launch dataset. It contains **five models**: four anchors
(Gemini 94.4, GPT-5.5 92.9, Opus 92.0, Sonnet 91.4) and **one** community model, Qwen3.5 9B at 86.1
— and that 9B exists as **three repeat runs of a single quant** (`quick-9b-var1/2/3`), all `tier:
quick`, all `ranked: false`. This produces three concrete, falsifying problems the spec never
confronts:

1. **The model-page hero has no data and cannot be built.** QuantDeltaStrip is a *paired delta of
   quant vs FP16 baseline on fixed items*. There is exactly **one quant** for the only local model.
   No baseline, no second point, no delta. The "launch hero" and "single highest-value
   differentiator" (spec §7 build-order item 3) renders an empty axis on the only page it can appear
   on. The spec even hedges this — "gate it behind real multi-quant data" — which is an admission
   that **the differentiator is absent at launch.**

2. **The home hero scatter is illegal under your own lane rule.** The four anchors are
   `lane: api-uncapped`; the one community point is `lane: answer-only`. The spec's flagship rule
   (§2.3.4, §4.1) is *"lanes never co-plot; switching lanes re-fetches that lane's points + anchor
   lines."* So on day one the answer-only lane shows **one teal dot and zero anchor lines** (no
   answer-only anchors exist), and the api-uncapped lane shows **four dashed lines and zero community
   dots.** The hero literally cannot show a local point *against* a frontier ceiling in the same
   frame — which is the entire promise of the picture. A new visitor sees either a lonely dot or a
   ceiling with nothing under it.

3. **The board reproduces the v0 non-discrimination failure as a chart.** The seed composites:
   9B = 86.1 vs frontier 91–94. That is the *exact* ~6-8pt floor-to-frontier collapse the handoff
   says killed v0 ("a 9B scored within ~6 composite pts of frontier SOTA"), driven by genmath
   saturating at 100/100/100/97.5 and IFEval bunching high. If the website ships before the suite
   rebuild lands, **the homepage is a monument to the bug.** A skeptical r/LocalLLaMA reader will
   screenshot "Qwen 9B is 93% of Gemini" and the credibility is gone in one post. The design must be
   explicitly sequenced *behind* the discrimination probe, and should refuse to render a composite
   ranking until anchor-spread clears a threshold.

The brief asked "does the design survive a near-empty dataset?" The honest answer from the real data
is **no — both heroes are dark on day one, and the visible composite actively misleads.**

---

## Killer homepage lead — what I'd put first, and why it beats the alternatives

**Lead with a single worked example: "What Q4 actually costs — measured."** A self-contained,
fully-populated explainer card, above any table, built from the one thing you control on day one:
**your own RTX 5090 running one model at FP16 → Q8 → Q5 → Q4 → Q3, paired, with CIs, against the
four anchors as a reference ceiling line.** It is the QuantDeltaStrip's content, promoted to the
front door, as a *demonstration of the method* rather than a leaderboard entry. One model, one
honest dumbbell-with-paired-CI, one sentence: *"On suite-v1 fixed items, Q4_K_M costs this model
−4.6 ± 1.9 pts vs FP16 — and here's the frontier it's measured against."*

Why this beats the four candidates the brief named:

- **vs "quality-vs-VRAM scatter as hero" (current):** the scatter needs *population* to be a scatter
  — a cloud of community points is what makes "find your card's frontier" legible. With one local
  point it's not a scatter, it's a dot. And it can't co-plot anchors by your own lane rule. A scatter
  is the right hero in *month 6*, not *week 1*. Holding the scatter as hero is optimizing for the
  data you wish you had.
- **vs "find the best model for MY GPU" finder:** this is the best *eventual* primary CTA and I'd
  build the affordance immediately (a VRAM-budget control), but as a day-one *hero* it returns "for
  24 GB, we have Qwen 9B." A finder that finds one thing reads as broken. It becomes the hero once
  there are ~15-20 local setups across the VRAM tiers.
- **vs "your rig vs frontier gauge":** this is good and I'd keep it as the **secondary** module, but
  as the lead it overclaims in exactly the way the brief forbids — a gauge invites "how close is
  local to GPT-5.5" as a *score-to-beat*, when the whole reframe is that frontier is a ceiling, not
  an opponent. A gauge with the 9B at "93%" is the misleading-composite problem with a needle on it.
- **vs "model-vs-model diff":** needs ≥2 well-covered models; you have one. Later, "Qwen 9B Q4 vs
  Llama 8B Q5 on your card" is a fantastic shareable view. Not day one.

The quant-explainer-as-hero wins because it is **the only hero that is both fully populated on day
one AND is the actual wedge.** It teaches the thing nobody else publishes, using data you can
generate yourself before a single community run arrives, and it's the same component you scale into
the model-page hero later — so it's not throwaway.

---

## Model-page hero — keep the quant strip, but it's the *site's* hero, not just the model's

**Keep QuantDeltaStrip — it is the single best idea in the whole spec.** "Paired delta on fixed
items with a paired CI, rendered as a dominance verdict, never a universal %" is genuinely novel and
is precisely what AA/LocalScore structurally cannot say. The ~1.9pt paired MDE vs ~13pt unpaired is
the most defensible sentence in the entire project. Do not cut it.

But two corrections:

1. **It's wasted as *only* a model-page hero.** The very thing that makes it the wedge means it
   should be the **homepage** hero (see above). On the model page it stays the hero, fine — but the
   site's front door should be the quant story, not a board.

2. **It is not "too niche" — it is too *empty*.** The brief asks "is the quant strip too niche / not
   the first thing people want to see?" No: "is Q4 good enough on my 3090?" *is* the literal question
   the audience asks (brief §3). The strip answers it more directly than anything else on the site.
   The risk isn't nicheness, it's that **on day one it has one model's worth of data and that model
   is yours.** Solve that by seeding 3-4 *base models across the VRAM tiers, each with a full quant
   ladder, all from your own 5090*, before launch. That is the cold-start content investment that
   actually matters — far more than any component.

One thing the strip must show that the spec underplays: **the token-cost delta is the punchline, not
a footnote.** "Q3 costs −9.2 pts AND −41% tokens" is the decision a local user makes. The spec
relegates token delta to a "separate secondary dumbbell" — correct that it's separate (don't fold
it), but it deserves equal visual weight: the audience trades quality for VRAM *and speed* together.

---

## Biggest risk — the one thing most likely to make this fail with the audience

**Launching the website before the suite discriminates, so the first impression is a board where a
9B is 6-8 points off the frontier.** The handoff is explicit that v0 failed validity and the rebuild
is unfinished (the discrimination probe is "the only remaining bench step"). The seed `index.json`
is still `suite-v0`. If the site ships on this data, an r/LocalLLaMA reader does the thing that
audience always does — sanity-checks against what they already know — sees "Qwen 9B ≈ 93% of Gemini,
and Gemini > Opus," and concludes the benchmark is junk. **You do not get a second first impression
with skeptics.** AA survived this because it *replaced* its saturated benches (Intelligence Index v4,
top fell 73→50) *before* the credibility hit compounded; you have the same precedent and must respect
the same ordering. The website's launch must be **gated on the probe**, and the homepage should carry
a visible discrimination diagnostic (anchor-spread per axis) *above the fold* so the first thing a
skeptic sees is evidence the suite actually separates models — not a composite they can dunk on.

A close second risk: **"AA but worse" by trying to be a full leaderboard at all on day one.** With 5
rows, a sortable 8-column board with rank-within-lane, filters, tier badges, and a VRAM slider is
*theatre* — UI for data that doesn't exist. The audience reads sparse-leaderboard-with-elaborate-
chrome as a vibe, not a tool. Lead narrow and honest, not broad and empty.

---

## Cut list (ruthless — most of this is YAGNI at launch)

- **FilterBar (community/anchor + lane + tier + VRAM slider + search).** Five rows. Cut entirely
  until there are ~20+ setups. The spec already half-admits this ("once row count grows"). A search
  box over 5 models is self-parody.
- **The home composite leaderboard *table* as a launch centerpiece.** Keep a minimal anchors-plus-
  yours list for context, but it is not the hero and not a "ranked board" — every row is
  `ranked:false` anyway. Don't ship rank columns, sort affordances, and rank-within-lane machinery to
  order 5 unranked rows.
- **AxisRadar toggle.** The spec itself says bars are honest and radar distorts CIs. So why build the
  distorting view? Cut it; it's a "shape of capability" toy that fights your own honesty thesis.
- **AxisRungBreakdown at launch.** Per-rung sub-scores (SuperGPQA easy/middle/hard, BFCL
  simple/multiple/parallel) don't exist in current data and won't until suite-v1 runs land. Build the
  parent-axis profile only; add rungs when there's rung data.
- **The full DiagnosticsPanel triptych (anchor-spread + S_index gauge + point-biserial/IRT strip).**
  Keep ONE element — the **anchor-spread bar per axis** — and *promote it to the homepage* as the
  credibility lead. Cut the S_index gauge and the IRT heat-strip from launch: they're internal
  instrumentation that reads as jargon-flexing to a first-time visitor and you won't have stable IRT
  α's on tiny n. Surface them later on methodology for the people who ask.
- **`mixed` verdict (violet) + the whole 4-color/4-glyph verdict taxonomy** beyond better/worse/tied.
  Mixed per-domain disagreement is real but rare and confusing at launch; collapse to ▲/▼/= and add ◬
  when you actually have models that exhibit it.
- **Log-scale X toggle on the scatter.** Footprints don't span 3→80GB at launch (your local models
  cluster in the consumer band). Linear is fine until you have frontier-sized local footprints.
- **`/submit` as anything more than a static CLI block.** Correct to ship it (the audit flags it
  absent), but it's one copyable command + "what uploads vs stays local" + lane/tier rules. Don't
  build an upload UI; the CLI *is* the funnel.

Net: cut ~40% of the component inventory from the launch milestone. Everything cut is "build when the
data justifies it," not "never."

---

## Concrete alternative IA (the REVISE)

Same five routes — the IA skeleton is sound — but **re-rank what leads each page so the site is
fully-populated and honest on a 5-model day-one set**, and re-sequence the build so nothing ships
empty.

```
HOME (/)            LEAD: "What quantization costs — measured" quant-explainer card
                    (one model's FP16→Q3 ladder, paired deltas + paired CIs + token-cost delta,
                    four anchors as a single reference-ceiling line).
                    BELOW: anchor-spread-per-axis strip = "does this suite actually discriminate?"
                    (the credibility lead, above any ranking).
                    BELOW: a minimal context list (anchors + the local models we have), explicitly
                    labeled "reference + early community runs — not a ranking yet."
                    The VRAM scatter appears here ONLY once it has a real cloud; until then it lives
                    on the model page where one model's quant ladder IS a legible mini-scatter.

MODEL (/model/[slug])  LEAD: QuantDeltaStrip (kept, the wedge). THEN per-axis profile (bars only),
                    THEN the per-model quant scatter (legible with one model's ladder), THEN
                    ReportedShelf, THEN runs table. Worst-axis highlight kept.

RUN (/run/[id])     LEAD: composite headline + the contamination canary (public vs private sentinel)
                    promoted UP — it's the strongest "you can't game this" trust signal and it's the
                    most concrete thing a skeptic wants. THEN axis profile, manifest, provenance.

METHODOLOGY (/methodology)  LEAD: WeightsTable + the "weight follows MEASURED discrimination, saturated→cut"
                    rule stated plainly (this IS the moat narrative). Anchor-spread detail + the
                    deferred S_index/IRT diagnostics live here for the people who dig.

TRUST (/trust)      Keep. Replication-not-"verified", cheat-proxy threat model, badge definitions.
                    This page is good and differentiating as-is; don't over-engineer it.

SUBMIT (/submit)    Static CLI block + what-uploads + lane/tier rules. Nothing more at launch.
```

**Day-one content investment that makes this work (more important than any component):** before
launch, on your own RTX 5090, run **3-4 base models spanning the VRAM tiers (e.g. ~3B, ~8B, ~14B,
~32B), each with a full quant ladder (FP16/Q8/Q5/Q4/Q3)** on suite-v1. That gives the homepage hero
real content, gives the model pages real strips, gives the eventual scatter a real cloud, and — most
importantly — lets you *prove the suite discriminates* with your own runs before you ask the
community for anything. The cold-start fix is not a design trick; it's ~12-16 self-generated runs and
a probe that clears the anchor-spread gate. The website should not launch without both.

**One-line summary of the pivot:** stop presenting a *leaderboard* and start presenting a *measured
claim* — "here is exactly what quantization costs, with the uncertainty shown, on hardware you can
buy" — because that is the only thing that is (a) fully populated on day one, (b) impossible for AA or
LocalScore to say, and (c) the literal question your audience types into the search bar.
