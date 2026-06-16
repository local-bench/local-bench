# Move 2 — difficulty-stratified suite restructure: SPEC for sign-off (2026-06-17)

*The single scoring/suite restructure. Absorbs Move 1 (floors). Built from: the flat-wedge finding
(`quant-ladder-v11-findings-2026-06-17.md`), the GPT-5.5 red-team (SOUND-WITH-FIXES), the MDE/power
computation, and the r/LocalLLaMA model research. This is the interview-first artifact: react to it before
codex builds anything. **Nothing here spends API $. Reference-ladder runs are local-only ($0 GPU).**

## 0. What changed vs the original work order
The original plan (one 40-70% difficulty band, floors as a quick config edit) is superseded on two proven points:
1. **Floors aren't config** — weights live in code (`metadata.py:DOMAIN_WEIGHTS`), `bfcl-AST` can't be floored
   without splitting the Agentic domain, and ~10 tests bake equal weights into their *fixtures*. So floors fold
   into THIS build. (Move 1 reverted; suite green at 524.)
2. **A single difficulty band is a design flaw** (red-team crux + confirmed by the MDE): one fixed band can't
   discriminate across 1B→frontier — it re-saturates the top or floors the bottom. Replace with **stratified tiers**.

## 1. Purpose (primary vs secondary — keep these distinct)
- **PRIMARY: de-saturate and discriminate across the local range.** This is the product (distance-to-frontier
  across local models). It is independent of whether a quant wedge exists. lcb 95-100% and BFCL-AST 91% are
  measured-saturated; the suite currently can't separate a 9B from a 27B from frontier on those axes.
- **SECONDARY: test whether a quant wedge exists at all, and where.** The MDE result (below) shows the 27B
  reasoning-on wedge is ~0 on *current* items; the open question is suppressed-by-saturation vs intrinsic. The
  hard tier + smaller models is the experiment that decides it. Do NOT let the wedge (secondary) gate the
  de-saturation work (primary).

## 2. The MDE finding that frames the wedge (from tonight's clean data)
Pooled 27B reasoning-on paired wedge vs Q6 (200 items/step, all 5 axes):

| Step | net flips (deg-gain) | flip-rate | McNemar p |
|---|---|---|---|
| Q6→Q4 | +6 | 3.0% | 0.33 |
| Q6→Q3 | 0 | 0.0% | 1.00 |
| Q6→Q2 | -2 | -1.0% | 0.85 |

Detectable wedge: **n=40 → only ≥17.5%; n=400 → ~1.75%; n=2000 → ~0.35%** (one-directional, ~80% power).
→ The 27B reasoning-on wedge is statistically zero + non-monotonic on current items. Either suppressed by
saturation (hard items would flip) or intrinsic (reasoning error-corrects). **Implication: the wedge, if real,
needs (a) harder items AND (b) smaller models / more n — not the current easy items at n=40.**

## 3. Core design — difficulty is measured PER REFERENCE RUNG, tiers are BAND-SPECIFIC
The mistake to avoid: "difficulty" is not one global scalar. An item easy for a 27B can discriminate a 3B; an
item that splits a 27B-vs-frontier floors a 3B. So:

- **Measure per-item difficulty on EACH reference rung** (not a single pooled score). Every item gets a profile:
  `{correct_3B, correct_12B, correct_27B}` (and frontier-anchor later, $-gated).
- **Tiers are band-specific.** `easy` = items where the weak rung (3B) sits ~40-70%; `medium` = where the mid
  rung (12B) sits ~40-70%; `hard` = where the strong rung (27B-Q6) sits ~40-70%. An item can belong to more than
  one tier; that's fine.
- **Score band-matched.** A model under test is scored on the tier(s) matched to its size class, and the
  composite reports **where** it is being separated (small models read on easy/medium, 27B+ on hard). This is the
  red-team's "band-aware sub-scores," and it is what kills the re-saturation problem.
- **The quant wedge for a given model size uses THAT size's hard tier** (items that size finds ~40-70%) — this
  also resolves the red-team's circularity worry (Q3): we never select items for a model's quant-robustness, only
  for its difficulty.

## 4. Reference ladder (from the r/LocalLLaMA research — confirm the picks)
3 distinct families for diversity (red-team requirement), all servable $0 on the 5090:
- **Weak (1-3B):** **Llama-3.2-3B** (ubiquitous small baseline). Alt: Phi-4-mini 3.8B.
- **Mid (7-14B):** **Gemma-4-12B** — the current r/LocalLLaMA "best capable model on one consumer GPU" (3 Jun
  2026, runs 16GB, clean license, the hottest *non-Qwen* family). Family diversity vs Qwen is the point.
- **Strong-ref (27B):** **Qwen-3.6-27B @ Q6_K** (near-lossless), the model already characterised.
- Families span **Llama / Gemma / Qwen** → difficulty is not Qwen-specific (anti-circularity + transfer).
- **Decoupling:** calibration (binning items into tiers) and wedge-evaluation use the reference rungs only; live
  models being ranked never reshape the frozen tiers. Gemma-4's **QAT** quants are a bonus wedge data point (a
  quant-aware-trained model should degrade differently — a natural contrast to Qwen's post-hoc GGUF quants).
- **Model-size wedge (Michael's "yes"):** run the quant ladder on **Gemma-4-12B AND a small model** in addition
  to the 27B, each on its own hard tier → the launch story becomes **"quant cost vs model size,"** not a
  single-model wedge. This is the cleanest test of suppressed-vs-intrinsic.

## 5. Floors + Agentic split (absorbed Move 1)
- **Floor** (kept as floor rungs, not removed): `Coding` (lcb), `Agentic-SingleTurn` (split out of Agentic),
  `Math` (frontier-only reference). `Agentic-MultiTurn` carries the agentic axis (resolves #63).
- **Reconcile the THREE weight sources** into one authoritative source: `metadata.py:DOMAIN_WEIGHTS` (runtime),
  `suite.json` axes (probe + display), `web/build_data.py:COMPOSITE_WEIGHTS` (site). Best: make the composite
  read weights from `suite.json` so there is ONE source. (Touch `web/` only with Michael's ok — it's the site
  workstream.)
- **Re-engineer the equal-weight test fixtures** (e.g. `test_compare_runs` offsets via Math, which only nets zero
  at equal weight — re-plant the offset through a kept-weight axis).
- **lcb rescue:** flooring removes the only coding signal; Move 2 should attempt to re-select HARDER lcb
  output-prediction items (the hard tier) before accepting coding as permanently floored.

## 6. Source-pool sufficiency (the N-floor gate — flag thin axes BEFORE building)
Each axis must fill its tiers with enough items that the paired-delta MDE stays meaningful (§2). First-pass read:
- **mmlu_pro** — 12k-item source pool → can fill 3 tiers easily. ✅
- **ifbench** — constraint checkers are regeneratable at difficulty → ✅
- **ruler_32k** — generatable at any difficulty/length → ✅ (the durable core, Move 3)
- **bfcl_multi_turn** — 100 items → thin; maybe 2 tiers, not 3. ⚠️ flag
- **lcb** — 129 items → thin; harder-item re-selection may not fill a hard tier. ⚠️ flag (may need a new exec-free
  coding source)
- **math** — floored (frontier-only), no local tiers needed.
Where a pool can't fill a tier, **flag it** (needs more source items) — do not silently ship a thin tier.

## 7. Required-proof gates (red-team — the build is NOT "done" until these pass)
Guard against the plan "confirming itself" (a clean datasheet that doesn't improve separation). Acceptance:
1. **Non-saturation per tier** — no tier sits >90% or <15% for its target band.
2. **Stable model ordering** — the calibrated suite ranks the reference ladder in the right order, with CIs.
3. **Item-test correlation** — kept items correlate with the axis total (discriminating, not noise).
4. **Paired-delta CIs** reported on the wedge (not point estimates).
5. **Detectable effect size** — state the MDE for each axis/tier at the chosen n (per §2).
6. **Live-probe** — calibrated sets show *wider* between-model spread than the old sets on a held-out check
   (don't trust the selection logic; measure it).

## 8. Build sequence (all $0 / GPU-only until the anchor step, which stays on hold)
1. **Sign-off on this spec** (Michael) + confirm the ladder picks (§4).
2. **Validate Gemma-4-12B + Llama-3.2-3B serve** on the 5090 llama.cpp build (sm_120), single-instance,
   concurrency 1, pre-flight clean-check (post-concurrency-incident discipline).
3. **Calibration pass** ($0, overnight, sequential): reference ladder × full item pools, reasoning-on → per-item
   per-rung difficulty profiles. (This is the un-gated local half of the pre-registered probe — NOT blocked by
   the probe's $-hold.)
4. **Bin + freeze + datasheet** (seeded, deterministic, versioned beside suite.json).
5. **codex builds** the scoring restructure (tiers + band-aware composite + floors + Agentic split + reconciled
   weights + re-engineered fixtures). I review every diff + run the suite green.
6. **Verify** (§7 gates) + **model-size wedge re-check** on the calibrated hard tiers, reasoning-on.
7. Report: wedge visible (→ it was suppression) or still flat (→ intrinsic; re-aim to smaller/lower-bit).

## 9. Open decisions for the interview
1. **Ladder picks** — Llama-3.2-3B / Gemma-4-12B / Qwen-3.6-27B-Q6? (or Phi-4-mini for the weak rung?)
2. **Tier count** — 3 tiers (easy/med/hard) standard; 2 for thin axes (bfcl-multi-turn, lcb). OK?
3. **Single weight source** — make `suite.json` authoritative and have the composite read it (touches the
   `web/` copy — coordinate with the site workstream or leave web for later)?
4. **lcb / coding** — attempt harder-item rescue, or accept coding as floored-for-now and flag for a better
   exec-free source?
5. **Scope of the model-size wedge** — which small model joins Gemma-4-12B + 27B in the wedge sweep?
