# Objective assessment vs original goals (2026-06-16)

*Requested: step back and judge whether the work has appropriately met the original goals — honestly,
including shortfalls. This is a verdict, not a victory lap.*

## The original goals (what we're grading against)
1. **A community quality leaderboard where a local user runs a frozen suite on their own setup and
   compares to FRONTIER models measured on the IDENTICAL suite.** ("Geekbench for local AI intelligence.")
2. **Launch wedge = the quant-degradation dataset nobody publishes** — what quantization costs your model,
   measured, with CIs.
3. **The hard validity gate:** the suite must **DISCRIMINATE across small-local → frontier.** This is the
   exact thing v0 failed (a 9B sat within 6 pts of frontier; 2 of 3 axes saturated) and the reason for the
   whole rebuild. Honest numbers, CIs, three-kinds-of-numbers kept distinct, never claim "verified".

## Verdict (BLUF)
**The differentiator is delivered; the core validity proof and the comparison spine are not.** The quant
wedge is real and rigorous, the suite is far stronger and broader than the failed v0, and the codebase/site
are in genuinely good shape. **But the two things that were the actual POINT — (a) proving the suite
discriminates local→FRONTIER on *our own* harness, and (b) having *measured* frontier anchors as the spine
local users compare against — are not done.** We *inferred* frontier discrimination from public leaderboards
and *deferred* the frontier measurement. So this is roughly **two-thirds of the way to a credible launch**:
the wedge could ship; the headline promise ("compare to frontier on the identical suite") cannot yet, because
there is no measured frontier data on suite-v1.

## What is genuinely solid
- **Launch wedge — DONE & rigorous.** 5-rung Qwen3.6-27B ladder, paired bootstrap CIs, flat Q8→Q3 + a
  significant Q2 cliff (−6, CI excludes 0). Detecting a 5–6 pt quant gap with CIs *is* fine-grained
  sensitivity — the opposite of v0's saturation. This is the differentiator and it's measured, not vibes.
- **Suite breadth & validity posture — much improved.** From v0's 3 saturated axes to **6 license-clean
  axes** (knowledge/instruction/agentic/math/coding/long-context) chosen for discrimination + contamination
  resistance (SuperGPQA, IFBench, BFCL, OlymMATH/AMO, LiveCodeBench output-pred, RULER 32k). Real serving
  built from scratch (native llama.cpp sm_120), thinking-suppression, a long-context truncation assertion.
- **Methodology rigor.** Chance-correction, bootstrap CIs, hardened scoring (cluster-robust / FDR / exact
  McNemar) merged, **per-axis composite** consistent CLI↔site, a discrimination-probe framework.
- **Engineering health.** Six divergent branches reconciled into one; **488 tests green**; site migrated to
  suite-v1, real data, build + e2e (12/12) green.

## The load-bearing gaps (the honest part)
1. **Local→FRONTIER discrimination is NOT measured on our harness — only inferred.** We have exactly ONE
   between-model pair on suite-v1: Qwen3.6-27B vs Gemma-4-12B (~11 pt gap on knowledge/instruction). That's
   encouraging *local-tier* discrimination, but **no frontier model has been run on suite-v1.** The
   discrimination-probe verdict ("keep all 4 axes; they spread") came from *public leaderboards*, not our
   items/harness. So the precise failure that killed v0 — does the full range actually spread on *our*
   exam — is **not yet closed with our own numbers.**
2. **No measured frontier anchor spine on suite-v1.** The product's central promise is "compare your setup
   to frontier measured on the identical suite." There are **zero** frontier runs on suite-v1 (the anchor
   spend was deferred). The site shows **2 real local models + 7 synthetic demo models** — the frontier
   reference line a user compares against is currently demo data, not measured.
3. **The two new axes have zero model runs.** Coding (LCB) and long-context (RULER) are built + unit-tested
   but **no model has been scored on them.** They're infrastructure, not yet evidence.
4. **The wedge is thin vs the plan.** One model (+ a single Gemma glance), **N=80** (Quick-ish, ±~3 CIs),
   **answer-only lane** (reasoning suppressed; local think-on proved impractical). The plan envisioned a
   ~30-run seeded family study at Standard-N in the native-reasoning HEADLINE lane. We're below that.
5. **Not deployed / no live community path.** Site runs locally only; no PyPI/Vercel/Supabase/OAuth (these
   need your accounts and were always launch-time, but the "community can submit" loop isn't live).

## What would actually close the gap (concrete, small)
- **Measure the spine + prove discrimination (the one that matters):** run 2–3 frontier anchors **+ ≥1
  deliberately weak local (e.g. a 4–8B)** on suite-v1 (the deferred ~$10–15 API spend + one local run).
  That simultaneously (a) builds the real frontier comparison line and (b) demonstrates the full
  weak→frontier spread *on our harness* — directly closing the v0 failure with our own numbers.
- **Run the existing 6 local models on coding + long-context** (free, 5090) so those axes carry evidence.
- **Consider Standard-N** for the wedge to tighten the ±3 CIs (or pool), and add a capped-thinking lane.

## Fairness note
Most gaps are **deferred-by-decision, not execution failures**: the anchor spend was the cost you explicitly
told me to avoid pending a public-data check; the new axes were only just built; the wedge scope was the
launch differentiator, not the full seeded study. The work done is substantial and sound. But the deferred
items **are the core of the original promise** — so "appropriately met our original goals" is, honestly,
**not yet**: we built the differentiator and the machine, but not the proof that the machine measures what we
claim, nor the frontier reference it's meant to measure against.

---
## MEASURED UPDATE (2026-06-16, later same day)
Michael had me close the gap. First confirmed (research agent) that **public data cannot supply a frontier
composite** — no model has published scores across all 5 of our benchmarks; coverage is sparse, cross-version,
cross-harness (only IFBench carries current frontier). So we measured our own, cost-disciplined.

**Measured matched ladder** — same 25 items, 3 comparable axes (knowledge/instruction/agentic), api-uncapped
frontier vs answer-only locals, BFCL re-scored with the bug fix below:

| model | knowledge | instruct | agentic | 3-axis |
|---|---|---|---|---|
| Gemini 3.1 Pro | 68 | 96 | 100 | **88.0** |
| GPT-5.5 xhigh | 52 | 96 | 100 | **82.7** |
| Opus 4.8 max | 52 | 56 | 96 | 68.0 |
| Qwen3.6-27B Q4 | 52 | 48 | 100 | 66.7 |
| Gemma-4-12B Q4 | 40 | 28 | 96 | 54.7 |
| Qwen3-4B Q4 | (floor, running) | | | |

### Verdict update: the v0 discrimination failure is SUBSTANTIALLY CLOSED — measured, not inferred.
Frontier (82–88) separates cleanly from locals (55–67): a ~20–30 pt gap and a ~33 pt weak→frontier range.
Nothing like v0's "everyone within 6 points." The comparison spine now exists as real measured data.

### But honestly, the win is uneven and these are real follow-ups (not yet done):
- **Instruction (IFBench) carries the discrimination.** It spreads cleanly across the full range (96/96/56/48/28).
- **Knowledge (SuperGPQA) under-discriminates at the top:** GPT-5.5 = Opus = Qwen-27B all at 52 on this
  25-item subset; only Gemini breaks away. Either N=25 noise or the subset doesn't separate strong models.
  → review/expand the knowledge subset; raise N.
- **Agentic (BFCL) saturates** at the top (96–100 for every capable model). → swap in a harder agentic set
  (ToolHop / multi-turn), per the original adopt plan.
- **N=25 is too small** for confident per-axis claims (each item = 4%). The aggregate spread is robust; the
  per-axis numbers are noisy. → Standard-tier N before any of this is published as ranked.
- **Opus ≈ Qwen-27B** is a *real* result (Claude's known IFBench weakness, published Opus ~58–62), amplified
  by small N — not a suite failure.
- **Lane caveat:** locals are answer-only (think-on impractical), frontier is native-reasoning. Different lanes;
  documented, not merged. The cross-lane gap is the honest "your practical local config vs frontier as it runs."

### Bonus: a real scorer bug found + fixed in the process.
BFCL's AST arg parser coerced JSON-style booleans (`avoid_tolls=true`) to the string `"true"`, **false-flooring
frontier models** that emit lowercase booleans (Opus agentic 84→96 once fixed). Committed (0e67ede). Exactly the
"brittle scorer" failure mode — worth a sweep of the other scorers for similar format assumptions.

### Cost: ≈ $9 total (Opus N=25 ~$4, Gemini N=40 ~$3, GPT-5.5 N=40 ~$1.5, probes ~$0.5). Within budget.

### Where this leaves the original goals (revised)
The differentiator (wedge) was always there; now the **core validity claim is measured**: the suite discriminates
local→frontier on our own harness. That moves the project from "impressive machine, unproven measurement" to
"measurement demonstrated, on a small N, with two axes needing hardening." The remaining honest work is
*scale + axis quality* (bigger N, harder agentic, knowledge-subset review), not a fundamental validity question.
Runs: runs/anchor-{gpt55,gemini,opus}-v1.json + runs/qwen3-4b-instruct-q4.json.
