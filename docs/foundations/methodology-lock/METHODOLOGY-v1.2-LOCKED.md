# local-bench — METHODOLOGY v1.2 (LOCKED, CONSOLIDATED) — 2026-06-19

*Single canonical methodology record. Folds and SUPERSEDES, for day-to-day reference, the separate
decision/result docs in this folder: `DECISION.md` (dual red-team + Michael's sign-off), `SUITE-LOCK.md`
(the v1.2 lock), `WEDGE-RESULT.md` (accuracy-wedge NO-GO), `LADDER-RESULT.md` (Gemma quant matrix),
`KLD-RESEARCH.md` + `KLD-VALIDATION.md` (KLD adoption). Those remain as dated EVIDENCE; this doc is the
spec everything implements. Reversible ONLY if new discrimination data contradicts a specific call below.*

---

## 0. What local-bench measures (the product claim)
"**Verified local quality vs frontier**" — distance-to-frontier on a frozen, reproducible suite a local-LLM
user can actually run on their own rig, anchored against frontier models measured on the identical suite.
The quant story is a **secondary, honest** finding, NOT the headline: quantization costs you **VRAM and
speed/compute**, and shifts the output **distribution** (KLD drift), but — with reasoning ON — does **not**
cost task accuracy until a low-bit cliff. See §6.

## 1. Lane (LOCKED)
- **Reasoning-ON only** ("capped-thinking"). This is the single headline lane; users run reasoning-on.
- Graceful **reasoning-budget 8192** (server-side; truncates reasoning gracefully, not mid-token). `max_tokens`
  ceiling **16384** (runaway bound, not a fairness lever). Serve **f16 KV** (no KV quant), **64k** standard
  context, **≥12k tokens/slot**. Tokens-to-answer captured as a first-class dimension (accuracy AND compute).
- Composite is computed **within a lane only**; answer-only / api-uncapped are secondary views, never merged
  into the headline.
- *Open calibration (deferred, sign-off-gated):* a 4k/8k/12k/16k budget sweep on ~300 mixed items to confirm
  8192 doesn't under-measure verbose R1-class models. Until run, 8192 stands.

## 2. Axis registry (THE contract — one source of truth)
Each axis has a canonical id, a member bench set (with v0 back-compat benches), a **role**, and a **composite
weight**. This table is the authoritative spec; the code registry (`localbench.scoring.axes`) mirrors it
exactly and is the SOLE weight source (see §8).

| Axis (canonical) | Bench(es) — v1 | Legacy (v0) | Role | Composite weight | Evidence |
|---|---|---|---|---|---|
| `knowledge` | mmlu_pro | supergpqa | **headline** | **0.5** | discriminates: Gemma-12B 77% vs frontier ~90% |
| `instruction_following` | ifbench | ifeval | **headline** | **0.5** | discriminates: Gemma-12B 79% vs frontier ~90%+ |
| `math` | olymmath_hard + amo (pooled) | genmath | candidate | 0.0 | floors locals ~0 → REBUILD pending (§9.1) |
| `long_context` | ruler_32k | — | candidate | 0.0 | differentiator; local discrimination UNCONFIRMED (§9.2) |
| `agentic` | bfcl + bfcl_multi_turn | — | experimental | 0.0 | BFCL-AST saturated/gameable (both red-teams) |
| `coding` | lcb (output-prediction) | — | experimental | 0.0 | saturated, "decorative" (both red-teams) |

- **headline** → enters the composite at its weight. **candidate** → measured + displayed, NOT in composite
  until validated (then promoted with a spread-proportional weight). **experimental** → measured + displayed
  on model/run pages, never in the composite.
- Runtime display labels (back-compat, unchanged): `Knowledge`, `Instruction-Following`, `Math`,
  `Long-Context`, `Agentic`, `Coding`. Web/site keys (back-compat): `knowledge`, `instruction`, `agentic`,
  `math` (+ `long_context`, `coding` when those gain display data).

## 3. Composite (LOCKED)
- Composite = **equal-weight mean of the chance-corrected HEADLINE axes present in the run**, normalized over
  the headline axes actually measured. Today that is `knowledge` + `instruction_following` at 0.5 each.
- A run missing a headline axis normalizes over the present headline axes and is flagged **partial** (not
  comparable to a full headline run).
- **Weakest headline axis is reported beside the composite** (arithmetic mean hides single-axis collapse).
- Weighting policy: stay equal-weight until **≥3 headline axes** validate, then move to **spread-proportional**
  weights (observed local→frontier spread, with caps) over the discriminating set. No equal-weight-over-all
  claim; non-discriminating axes never silently dilute the headline.

## 4. Knowledge axis hardening (carry-over)
MMLU-Pro (MIT, expert-cleaned keys) is the knowledge bench (SuperGPQA retired). The "93.8% proves a broken
scorer" alarm was **refuted** (hardened `mcq.py`: marker-anchored, negative-lookahead, "A or B"→ambiguous,
trailing-explanation ignored, bold-only-if-ends-response). The real residual concern — top-end knowledge
saturation + MMLU-Pro contamination — is managed by harder re-stratification + the private genmath sentinel
as a contamination canary; revisit if frontier anchors bunch at the top.

## 5. Stats (LOCKED) — three estimands kept distinct
1. **Run-to-run repeatability CI** (same config, re-run) — the "is this stable?" band.
2. **Paired quant-delta CI** (same items, Q8 vs quant; bootstrap + McNemar) — supports 2–3pt quant claims ON
   THE FIXED ITEMS, never as a universal %.
3. **Cross-item generalization CI** (do results transfer beyond these items) — the wide one; universal claims
   need Standard/pooled sizes.
Bootstrap CIs (items aren't iid); per-axis + worst-axis deltas; difficulty-stratified subgroup-regression
flags. Every displayed score carries a CI; deltas labeled "on suite-v1.2 items ± paired CI".

## 6. Quant / degradation reporting (LOCKED) — accuracy is NOT the story; the metric hierarchy is
**The accuracy quant-wedge is a NO-GO** (`WEDGE-RESULT.md`): Gemma-12B Q8→Q4 pooled +2.4pp, CI spans 0;
truncation-clean +0.5pp (nil). Reasoning recovers precision loss by spending **+35–40% more compute/tokens** —
Q4 isn't dumber, it's slower. The Gemma ladder (`LADDER-RESULT.md`) confirms it across the curve: **flat
Q8→Q4, cliff at Q3** (−5.7pp, heavy truncation). So the model page reports quant tradeoff as **VRAM + speed
(tok/s)**, with quality as a ~flat reassurance line that shows the low-bit cliff where one exists.

Underneath the flat accuracy, three metrics of increasing sensitivity (`KLD-VALIDATION.md`, validated on Gemma-12B):
- **Accuracy** — coarsest; flat-then-cliff; MASKS drift. The "does it still get the answer" check.
- **Churn** (task flips Q8→quant) — FREE + UNIVERSAL (any model, no FP16 baseline, from every task run);
  reveals hidden change (~12% of answers flip at Q4 despite flat net accuracy; 18% at Q3).
- **KLD** (KL-divergence of the output distribution vs full-precision) — smoothest + most granular; separates
  every quant level (Mean KLD ≈ doubles per step: 0.18→0.40→0.60→0.91→1.59 for Q8→Q3); expert gold-standard
  (Unsloth/llama.cpp); the early-warning signal accuracy hides.

**How it ships (guardrails, LOCKED):**
- Model-page **"drift" column**: KLD (median + q99) + Same-top-p, framed *"drift from the full-precision
  reference — lower = more faithful; **NOT a task score**,"* beside accuracy + churn + VRAM + speed.
- **Reference type is first-class:** BF16/FP16 where it fits; **"reference = Q8"** labeled visibly for big
  models where FP16 is infeasible on a 5090 (the Q8-proxy ≈ BF16 was validated). Never mix FP16-relative and
  Q8-relative on one scale.
- KLD never colors a quant "worse" alone — only paired with task-delta / churn / subgroup movement.
- The product is the **DECISION LAYER**: accuracy + churn + KLD + VRAM + speed → "run Q4 unless you need
  low-drift; Q3 is the cliff."
- **Calibration corpus** must be a model-suited, multi-slice **hashed** set (prose/instruction/code-math) for
  published absolutes; the validation used a wikitext slice (shape robust, absolutes inflated — see
  `KLD-VALIDATION.md` caveat). Reference type + calib hash recorded in the run manifest.

## 7. Demoted / retired
- **Coding (LCB output-pred)** + **Agentic (BFCL single/multi-turn)** → experimental profile axes (saturated/
  gameable); shown on model/run pages, never in the headline composite.
- **Retired, not doing:** difficulty-stratification (over-engineering for launch, both red-teams); answer-only
  lane as a headline (users run reasoning-on); quant-**accuracy**-wedge as the public differentiator (NO-GO).

## 8. Single weight source (the reconcile — DONE this pass, see §9.3)
Weights/roles/bench→axis membership live in EXACTLY ONE place: the code registry
`localbench.scoring.axes.AXES`. `DOMAIN_WEIGHTS` and `BENCH_DOMAINS` are DERIVED from it; the web build
(`web/build_data_axes.py`) IMPORTS its composite weights + bench groups from it (no hardcoded copy);
`suite/v*/suite.json` carries NO independent axis-weight numbers, and a test asserts the manifest's axis
membership matches the registry (drift gate). The run manifest records the resolved weights as provenance.

## 9. The four open items — resolution status (this consolidation pass)
1. **Math rebuild → mixed-difficulty.** SPEC written (`docs/foundations/methodology-lock/MATH-REBUILD-SPEC.md`):
   compose an easy→hard set targeting a 10–70% local band so Math discriminates across local→frontier. The
   item-set assembly + the local-band **validation run are sign-off-gated and DEFERRED** (no benchmarks this
   pass). Math stays a **candidate** (weight 0) until the validation run confirms the band.
2. **RULER local discrimination → confirm.** Requires a GPU run → **DEFERRED** (sign-off-gated). Spec'd as the
   first long-context rung of the next validation stage (`RULER-CHECK-SPEC.md`). Long-context stays a
   **candidate** (weight 0) until that run shows local→frontier spread.
3. **Weight reconcile → DONE** (§8). One registry; runtime + web derive from it; suite.json weight copies
   removed; drift test added.
4. **KLD in the CLI → DONE.** The ad-hoc `gemma_kld.sh` is replaced by a committed, unit-tested module +
   `localbench kld` subcommand (runner + panel parser + churn), tested against captured llama-perplexity
   output. Executing a ladder remains a benchmark (sign-off-gated); the code path is built and green.

## 10. Reproducibility (one command)
A frozen suite + a one-command run are documented in `docs/REPRODUCE.md`. Summary:
- **Task suite:** `localbench run --endpoint <url> --model <name> --lane capped-thinking --tier standard`
  → deterministic first-N item slice per bench (paired runs use identical items), server-scored, manifest
  emitted, run JSON written. Build the site data with `web/build_data.py`.
- **Quant drift (KLD):** `localbench kld --reference <f16.gguf> --quant Q8_0=<…> --quant Q4_K_M=<…>
  --calib <hashed.txt> --llama-perplexity <bin> --model-label <name> --out drift.json`
  → two-pass llama-perplexity, parsed KLD/churn panels → drift JSON for the model page (full flags in `docs/REPRODUCE.md`).
Every number gates through `reconcile`/manifest provenance; suite identity is the sha256-hashed `suite.json`.

## 11. Evidence index (dated, in this folder)
`DECISION.md` · `SUITE-LOCK.md` · `WEDGE-RESULT.md` · `LADDER-RESULT.md` · `KLD-RESEARCH.md` ·
`KLD-VALIDATION.md` · `gpt55-review.md` · `gemini-review.md` · `00-redteam-brief.md`. Raw KLD logs: `~/kld/`.
