# Discrimination probe — PRE-REGISTRATION v1.1 (2026-06-16)

*Supersedes the zero-spend public-data estimate `discrimination-probe-v1.md` (which predates the MMLU-Pro swap,
BFCL-multi-turn, lcb/ruler, the reasoning lane, and the AA-v4.1 saturation findings). This is the SPEC for the
spend-gated probe on Michael's hold. **Pre-registered**: the design, model set, budgets, and decision RULES are
fixed HERE, before any result is seen, so the probe measures the model — not the scaffold — and the keep/drop/
weight calls can't be fudged post-hoc (the methodology red-team's central requirement).*

## 0. Why pre-register
The red-team's sharpest point: a sloppy or model-varying harness measures scaffold quality, not capability. So we
fix everything that could vary, BEFORE running, and commit to numeric decision thresholds.

## 1. The suite under test (current, suite-v1.1)
6 axes: **knowledge** = mmlu_pro · **instruction** = ifbench · **math** = olymmath_hard + amo (pooled) ·
**coding** = lcb · **long-context** = ruler_32k · **agentic** = bfcl (AST floor) + bfcl_multi_turn (harder rung).

## 2. HELD CONSTANT across every model (the anti-scaffold contract)
- **Lane**: `capped-thinking` (reasoning ON for all — locals AND anchors), the calibrated per-axis caps
  (math 16384 · knowledge 12288 · ifbench/bfcl/lcb 8192 · ruler 4096; from the Qwen-Q4 calibration). Anchors run
  the SAME lane + caps (not their old api-uncapped data).
- **Prompts/templates**: the frozen suite templates, byte-identical across models. **Decoding**: temperature 0.
- **No per-model retries / reformatting / scaffold tweaks.** One attempt per item. Tool-call format identical.
  Agentic max-turns + step caps identical. Context budget identical. Item sets identical (the frozen fixed sets).
- Manifest records model/quant/runtime/template-hash so any deviation is visible.

## 3. Model set (Leg A needs real spread, weak→frontier)
- **Weak local**: a 1–3B (e.g. Qwen3-1.7B/3B or Llama-3.2-3B) — anchors the floor.
- **Mid local**: Gemma-12B + Qwen3.6-27B (Q4).
- **Strong local** (if it fits / time allows): a ~70B or the best open model we can serve.
- **Frontier anchors**: GPT-5.5 (xhigh), Gemini-3.1-Pro (high=max), Opus-4.8 (xhigh) — the reference ceiling band.
- Leg B (quant): the Qwen3.6-27B ladder Q2/Q3/Q4/Q6/Q8 (+FP16 if servable) on the FIXED items.

## 4. Two legs
- **Leg A — between-model (selection + weights):** run the model set on a per-axis SAMPLE (≥40 items/axis; full
  set for the small axes amo=39, ruler=60). Measures each axis's weak→frontier spread.
- **Leg B — within-model quant (resolution):** the quant ladder on the FIXED items → paired quant-deltas ± CI
  (the wedge). Confirms the suite can RESOLVE a quant step.

## 5. PRE-REGISTERED decision rules (fixed now)
Let `spread = frontier_anchor_mean − weak_local` (chance-corrected, per axis).
- **KEEP + full candidate weight** if `spread ≥ 15 pts`.
- **KEEP but flag** if `5 ≤ spread < 15`.
- **DROP / down-weight to floor** if `spread < 5` — i.e. SATURATED (a 27B ≈ frontier, like the standalone BFCL-AST
  case) OR FLOORED (weak AND mid locals ≈ 0, like SWE-bench).
- **Weights ∝ measured spread**, normalized over kept axes (replaces provisional equal 0.25). Editorial cap on any
  single axis ≤ 0.30 to avoid one axis dominating. Versioned in suite.json.
- **Agentic sub-weighting (resolves #63):** weight `bfcl` vs `bfcl_multi_turn` by THEIR measured spread, NOT by
  item count. Expectation from existing data: BFCL-AST saturates (down-weight to floor), BFCL-multi-turn carries
  the axis. Confirm, don't assume.
- **IFBench (provisional, AA-flagged):** if frontier + a 27B both cluster high in the reasoning lane (`spread < 5`),
  DEMOTE its weight and record the own-IFBench need. Confirm on the real sample (not the n=6 calibration).
- **Failure-taxonomy split (agentic):** report bad-call-syntax vs bad-state-reasoning separately; an axis that only
  separates models on syntax (not reasoning) is down-weighted.
- **Math watch:** the reasoning lane should lift locals off the answer-only ~0 floor; if locals are STILL ~0 with
  reasoning on, math stays a frontier-only reference-ceiling axis (kept, but its local-range weight reflects that).

## 6. Outputs (locked + versioned)
Finalized keep/drop set + per-axis weights (from §5 rules) written to `suite.json` (index-v1); the quant-delta
item-counts + CIs locked; a published probe datasheet (the measured spreads + the rule each axis triggered). After
this, the suite is calibration-frozen for v1.1.

## 7. Cost / GPU envelope (what authorizing this spends)
- **Leg A + B locals on the 5090** (capped-thinking): per the calibration, ~15 hrs/model full-suite; a probe
  SAMPLE (≥40/axis ≈ 250 items) is ~3–4 hrs/model → ~5–6 local models ≈ **~1 day of 5090** (no $). Concurrency 2
  (box-freeze caution); RULER needs a larger `-c` serving pass.
- **Anchors (API $$):** the 3 anchors on the probe sample in the same lane. **Cost-probe first** (~30 items,
  <$1) → measured per-item cost → full anchor probe est. ~$20–40. NO full anchor spend without sign-off.
- Everything here is GATED on Michael's go (GPU time + the anchor $). Pre-registration is the no-spend part.

## 8. Sequencing when green-lit
1. Calibrate RULER serving (large `-c`). 2. Leg A sample on the local ladder (overnight). 3. Anchor cost-probe →
sign-off → anchor sample. 4. Apply §5 rules → lock weights. 5. Leg B quant ladder → lock the wedge. 6. Rebuild
site data on the frozen v1.1. The probe measures the RIGHT suite because §1–2 are fixed here.
