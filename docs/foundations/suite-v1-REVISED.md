# suite-v1 — REVISED spec (post-red-team, measure-first)

**Status: paper revision for Michael's review. Supersedes the axis/weight choices in
`suite-v1-methodology.md`. Nothing implemented; no benchmarks run.** 2026-06-13.

This is the tightened spec Michael asked for after the red-team verdict (REVISE). It keeps the
verified core, drops the saturated/encumbered picks, adds two verified discriminators
(long-context), and — most importantly — **replaces leaderboard-based weighting with a
measure-first rule**. Grounded in the committed research + red-team + three follow-up
verification passes (long-context, license-clean math, calibration/coding-honesty).

---

## 0. The one rule that changes everything

The v0 failure and the red-team's verdict have the **same root cause**: axis selection and
weights were set from *published leaderboard numbers*, which (a) go stale in weeks and (b)
describe frontier-vs-frontier, not our local range. The fix is a hard rule:

> **No axis enters the composite, and no weight is assigned, until we have MEASURED its
> floor→frontier spread on our OWN runs.** Weight ∝ measured discrimination. Any axis where the
> four anchors cluster within ~3 pts gets weight → 0 (it's decorative). Be willing to ship
> FEWER axes than planned.

Everything below is therefore a **candidate set with a measurement plan**, not a fixed suite.
The numbers cited are current (2026-06-13, sourced) but are used only to decide *what to
probe*, never to set final weights.

## 1. Scope reframe (resolves half the tension)

local-bench measures **distance-to-frontier across the LOCAL range** (1B → ~32B), with frontier
anchors as a **reference ceiling**, not a ranking we resolve. So an axis only needs to:
1. **discriminate across the local range** (a 7B, a 14B, a 32B land at visibly different points), and
2. **keep the frontier anchors clearly above the locals** (the exact thing v0 genmath failed: 9B = 1.00).

Frontier-vs-frontier separation is **largely out of reach** for a license-clean, judge-free,
locally-runnable suite — especially in math and coding. We **state that honestly** and let the
axes that *do* carry frontier signal (SuperGPQA, IFBench, long-context) do that work.

## 2. Hard constraints (every pick obeys all five)

1. **License-clean to redistribute/serve** (no CC-BY-NC; no gated/no-republish data).
2. **Local-runnable** via an OpenAI-compatible endpoint on a single 16-48GB GPU — no sandbox, no browser, **no code-exec on the user's machine**.
3. **Discriminates across the local range** (validated by the probe, §6).
4. **Contamination-resistant** (synthetic/regenerable, date-windowed, or private-sentinel-canaried).
5. **Programmatic scoring — NO LLM judge** (deterministic + reproducible).

## 3. The revised suite (candidates, tiered by confidence)

### TIER A — adopt (red-team-verified, build now)

**Axis: Knowledge & Reasoning**
| Rung | Bench | License | Role | Notes |
|---|---|---|---|---|
| core | **SuperGPQA** (hard-weighted, stratified) | ODC-BY (data)¹ | discriminating core | spreads the local range (7B ~30% → R1 62%); open where GPQA is gated. ¹**serve-gate:** filter to clean-provenance items first (card warns of "transformed content from other datasets"). |
| floor | **MMLU-Pro** | MIT | floor rung | keeps weak-local separation; sub-score with CIs, never the whole axis. |
| stretch | **BBEH-mini** (460) | Apache code + CC-BY-4.0 data | frontier stretch (probe-gated) | floors sub-30B → informs the TOP only; normalized. |

**Axis: Instruction-Following**
| Rung | Bench | License | Role | Notes |
|---|---|---|---|---|
| core | **IFBench** (single-turn) | Apache + ODC-BY | discriminating core | built *because* IFEval saturated; programmatic verifiers; AA confirms unsaturated 6 mo. Vendor verifiers + parity-test (extends task #13). |
| floor | **IFEval** | Apache | floor rung | saturated at frontier but 7-8B ~72-74% floor still sorts weak locals. |

### TIER A — adopt, but needs a build prerequisite

**Axis: Math (license-clean ladder)** — *prerequisite: upgrade `math_numeric.py` from regex+Fraction to a sympy/`math_verify` equivalence checker (symbolic answers √3/intervals/tuples otherwise mis-graded).*
| Rung | Bench | License | Role |
|---|---|---|---|
| backbone | **HARP** (6 difficulty levels, 4,780 sympy-checkable) | **MIT** | floor→mid→hard in one dataset (AJHSME→AMC→AIME→USAMO). The find. |
| hard | **OlympiadBench** `OE_TO_maths_en` (674) | Apache-2.0 | hard headroom, sympy 1e-8. Drop proof/multimodal items. |
| hard | **Omni-MATH** rule-based subset (`omni-math-rule`) | Apache-2.0 | judge-free (authors shipped a rule subset to avoid Omni-Judge). |
| floor | **generated-math v2** (ours, hardened) | ours | floor→low-mid; contamination-immune; private sentinel = canary. Harden via reasoning-HOP depth (valid lever), NOT NoOp distractors (discredited 2026). |
| canary | **AIME-2025** (opencompass, 30, integer EM) | MIT | contamination canary only — saturated at frontier. |
> **DROP MathArena** (CC-BY-NC-SA — NC blocks monetization/serving) from the core; keep only as an internal, non-served cross-reference. **Honest cap:** this ladder separates small→mid→strong *local* models and pins anchors at the top; it does **not** resolve frontier-vs-frontier (final-answer math is dead at the frontier — MathArena 2026-05-12). Label the top "frontier reference ceiling."

**Axis: Long-Context** (NEW — the red-team flagged it; verification confirms it's a strong, clean discriminator)
| Rung | Bench | License | Role | Notes |
|---|---|---|---|---|
| core | **RULER @ 32k** (multikey-NIAH, var-tracking, aggregation, hotpot-QA) | Apache-2.0 | core | synthetic/regenerable (best contamination posture); programmatic recall scoring. **Drop ≤16k (saturated no-op).** |
| stretch | **RULER @ 64k** | Apache-2.0 | probe-gated stretch | wide, *size-independent* separation; **VRAM-gated** — runner must assert the endpoint served the full context (64k+ FP16 KV blows most consumer cards; offer KV-quant). |
| core | **LongBench v2** (≤32k subset) | MIT | core | MCQ accuracy (deterministic); NOT saturated (frontier 63% vs human 54%); clean monotonic local ladder. Static → re-check frontier-vs-human gap each cycle for leakage. |

### TIER B — keep only if the probe earns it, and label honestly

**Axis: Agentic (static function-calling only)**
- **BFCL non-live AST subset** (Apache-2.0): the *only* safe local agentic option (deterministic AST match, no sandbox/judge). Discriminates across the **local** range but is **saturated at the frontier** (Berkeley re-weighted V4 away from single-turn AST). → Keep **only at a small, probe-set weight**, labeled "local-range discriminator — saturated at frontier"; **never** the 20% the draft gave it. Main build risk: normalize tool-call shape (OpenAI `tool_calls` vs inline JSON vs Python) before AST compare; parity-test vs official `bfcl-eval`.
- **tau2-bench** (MIT): best dynamic agentic discriminator but needs API-side user-sim + judge tokens → **opt-in module, not default, not "local."**

### TIER C — defer (do NOT ship as launch core)

- **Coding → DEFERRED to a Docker-only opt-in module.** Verified: there is **no** clean exec-free coding signal. CRUXEval-O is contaminated (fine-tuning 3×'d a 1.5B's score) and compressed at frontier; RepoBench is FIM/similarity-scored (wrong shape); LiveCodeBench is a live harness that won't package static. Genuine coding ability needs execution. **Be honest: coding is unmeasured at launch.** The Docker lane (BigCodeBench-Hard + date-windowed LiveCodeBench) is the eventual home.
- **Calibration / hallucination-discipline → v2.** Every off-the-shelf set needs an LLM judge (SimpleQA, AA-Omniscience) or doesn't scale (AbstentionBench: "scale has almost no effect"). The only judge-free path is **build-our-own** false-premise/unanswerable pushback detector (regex refusal markers + "stated the false premise as real" check) — promising and orthogonal, but a v2 differentiator, not launch-gating.
- **Multilingual** (INCLUDE / Global-MMLU — cheap judge-free MCQ) → opt-in module unless the probe shows we want it in core.

## 4. What this means: likely launch shape

A realistic, honest launch is **4 measured-discriminating axes + 1 labeled-narrow axis**, not the
draft's 5-with-padding:

1. **Knowledge & Reasoning** (SuperGPQA core) — carries local AND frontier signal ✅
2. **Instruction-Following** (IFBench core) — carries local AND frontier signal ✅
3. **Math ladder** (HARP/Olympiad/Omni + hardened-gen) — local signal; frontier = reference ceiling
4. **Long-Context** (RULER 32k + LongBench v2) — local AND frontier signal ✅
5. **Agentic-static** (BFCL-AST) — local signal only, small weight, labeled saturated-at-frontier
   — *included only if the probe confirms local-range spread; otherwise dropped.*

Coding, calibration, multilingual, dynamic-agentic = clearly-labeled deferred/opt-in modules.

## 5. Composite design (math UNCHANGED; content + weighting changed)

**Keep the entire v0 scoring stack** (it's sound — this is a content swap, not a math rewrite):
absolute chance-corrected normalization, unclamp-for-inference (display-clamp only), **clustered**
bootstrap CIs, the three-estimand honesty rule (repeatability / **paired** quant-delta /
generalization), strict reasoning lanes (composite within a lane only; tokens/cost shown beside
accuracy), per-axis difficulty stratification, dated `suite-v{n}`/`index-v{n}` governance.

**Change — weighting:** weight by **measured discrimination** (§6), not leaderboard/domain-count.
Per-bench chance-correct *before* aggregating (fixes "Gemini wins by acing high-chance MCQ"). Hard
weight floor ~0 for any non-discriminating axis. **Lead with the per-axis profile; the composite is
only the sortable summary.** Display: headroom-buffered scale (map current SOTA anchor → ~80/100)
so the frontier doesn't visually pin the ceiling — display-only; raw chance-corrected values drive
the quant-delta math.

**Change — saturation gate becomes PRE-LAUNCH, not just quarterly:** §6 is the gate.

## 6. The discrimination probe (the gate — run after Michael signs off on this spec)

For every candidate bench, BEFORE assigning weight:
1. Run the **4 anchors** (Gemini 3.1 Pro, GPT-5.5, Opus 4.8, Sonnet 4.6) + **≥3 local models** spanning the range (e.g. a 1-3B, the Qwen 9B, ~a 32B) on a **sample** (Quick-tier item counts).
2. Compute per-bench **floor→frontier spread** + point-biserial discrimination (the §10 1PL/2PL proxy).
3. **Keep/weight rule:** weight ∝ measured spread; **drop** any bench where anchors fall within ~3 pts (frontier-flat) OR where all locals floor near chance with no mid-range signal.
4. Lock weights from the measured numbers; publish the saturation diagnostics on the methodology page (the credibility moat).

Estimated probe cost: ~$5-15 anchor spend + a few hours of 5090 time (pauses mining; restore after). **This is the only remaining benchmarking step and it is gated on sign-off.**

## 7. Open questions — resolved recommendations

| # | Question | Recommendation |
|---|---|---|
| Exec-sandbox | code-exec on user machines? | **No.** Coding deferred to a Docker-only opt-in module; ship no exec-free proxy. |
| Agentic scope | BFCL now? | Ship BFCL-AST **only if the probe confirms local spread**, at small weight + "saturated at frontier" label; tau2 = later opt-in. Defensible to defer agentic entirely. |
| Axis count | how many? | **As many as measurably discriminate** — likely 4 (Knowledge, IF, Math, Long-context) + BFCL if it earns it. Not a fixed 5. |
| MathArena NC | use it? | **No.** HARP (MIT) + OlympiadBench/Omni-rule (Apache) + our generated core cover the ladder license-clean. MathArena internal cross-ref only. |
| Serving licenses | serve the data? | SuperGPQA → provenance-filter first. HARP/OlympiadBench/Omni-rule/LongBench/RULER → clean. Confirm each **scorer-code** license before vendoring. |
| Calibration | build it? | **Defer to v2** (build-our-own pushback detector). Not launch-gating. |
| Refresh cadence | re-saturation? | Quarterly item regeneration (generated-math, RULER) + anchor re-run; AA climbed 50→60-65 in ~6 mo. FP16 baselines still need rented GPUs. |
| UI hierarchy | profile vs composite? | **Per-axis profile leads, composite sorts.** Confirmed (red-team + Epoch agree). |

## 8. Build prerequisites surfaced by the research (for the implementation phase)

- **sympy/`math_verify` scorer** to replace regex+`Fraction` in `cli/.../scorers/math_numeric.py` (blocks the whole math ladder).
- **RULER generator integration** + a runner assertion that the endpoint served the requested context length (no silent truncation); VRAM/KV-quant guidance per tier.
- **BFCL AST scorer + tool-call-shape normalizer** (parity-test vs `bfcl-eval`).
- **IFBench verifier vendoring + parity test** (extends task #13 to IFBench).
- **SuperGPQA item-provenance filter** before serving.
- Generalize the hard-coded 3 axes (`web/.../home-leaderboard.tsx` `TABLE_AXES`, the data pipeline, model/run pages) to the new profile.

## 9. Provenance

Built from: `research-dossiers.json` (9 tracks) + `red-team-findings.md` + three 2026-06-13
verification passes (long-context: RULER/LongBench-v2/HELMET; math: HARP/OlympiadBench/Omni-rule
+ GSM-Symbolic 2026 audit; calibration+coding: SimpleQA/AA-Omniscience/AbstentionBench +
CRUXEval-O contamination). Full sources in those docs and the agent transcripts.
