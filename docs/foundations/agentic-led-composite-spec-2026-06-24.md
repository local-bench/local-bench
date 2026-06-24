# Agentic-led composite — design spec (v2.0)

**Status:** LOCKED 2026-06-24 (owner decision + GPT-5.5 red-team). **Supersedes:** METHODOLOGY-v1.2-LOCKED
(headline = equal-weight K+I).

## DECISION (locked 2026-06-24)

Owner chose the BOLD weight over GPT-5.5's staged hedge, and to KEEP the existing name. GPT-5.5's
non-weight hardening is adopted in full (it backs the bold weight with maximal transparency).

**Headline name:** `Local Intelligence Index` (kept — owner call; "Intelligence" now spans agentic +
knowledge + instruction).

**Formula (v2.0):**
```
A* = clamp(AppWorld-C ASR / 50 * 100, 0, 100)      # ceiling 50 = frozen EXTERNAL anchor (GPT-4o ~49% on
K* = clamp((MMLU-Pro - 10) / 90 * 100, 0, 100)     #   AppWorld normal); -> 60 iff our frontier anchors >50
I* = clamp(IFBench, 0, 100)                         # chance-correct K (MMLU-Pro is 10-choice)
Local Intelligence Index = 0.50*A* + 0.25*K* + 0.25*I*
```

**Adopted from the red-team (REQUIREMENTS, not optional):**
1. **Hash the transform constants** — add a frozen `AXIS_TRANSFORMS` registry (per-axis kind/floor/
   ceiling/clamp/raw_unit) and fold `axis_transforms_digest` + payload into `scorecard_identity()`.
   Without this a future ceiling 50->60 silently re-scores history. (Biggest catch.)
2. **AppWorld-C is a NEW measured bench** — register it (new `scorer_version`, suite membership);
   do NOT relabel the existing experimental `bfcl`/`bfcl_multi_turn` agentic axis.
3. **Freeze the full agentic harness identity** in the scorecard: AppWorld version + dataset split
   digest, `evaluate()` version, agent-loop version, system-prompt digest, tool-contract digest,
   max-steps/wall/tokens, generation params, backend + quant policy, container/image digest.
4. **Frontier anchors:** same formula, shown, but NO Local Rank (label "reference, not local-ranked").
   Raw AppWorld-C always visible; do not compare anchors to each other on the clamped normalized axis.
5. **Display:** always show raw + normalized axis + index + a CI/tie band (binary ASR is noisy).
6. **Compensatory composite** — document that strong K/I can partially offset weak agentic (additive),
   but agentic has the largest marginal effect. Optional later: an "agentic eligibility floor"
   (e.g. <5% ASR => ranked but "not agent-ready"), NOT a hidden nonlinear penalty.
7. **Validation gates as a CONFIDENCE SIGNAL (not a weight gate, since weight is fixed at 50%):**
   surface coverage / run-to-run repeatability (target median rerun delta <=0.5pp) / discrimination
   (P90-P10 >=8pp) / rank-stability on the methodology page so 50% is transparent about validation.
8. **Contamination:** AppWorld's public test set is not fully hidden; at 50% weight add raw
   contamination flags, no per-model prompt tuning, a suspicious-jump audit.

**Marginal influence (per raw point, at 50/25/25, agentic ceiling 50):** +1 raw ASR pt = +1.0 index
pt; +1 raw IFBench pt = +0.25; +1 raw MMLU-Pro pt = +0.278 (after /90). Agentic is ~3.6-4x as
influential per raw point as either proxy — it dominates, as intended.

**Gated on:** agentic campaign coverage (every ranked model scored — running) + the build above.
Re-freeze as METHODOLOGY-v2.0. Board is pre-launch, so this revises a pre-launch design.

---

### Original draft (pre-decision) follows — retained for reasoning; §4.1 weight + §4.5 name are
### superseded by the DECISION block above; the red-team REQUIREMENTS above amend §4.2/§5.

## 1. Decision being implemented

The headline composite ("Local Intelligence Index") currently = equal-weight mean of **Knowledge**
(MMLU-Pro) + **Instruction-Following** (IFBench). Agentic (AppWorld-C ASR) is shown as an
experimental, **0%-weight** column.

Owner decision (2026-06-24): **agentic should drive the headline "more than anything."** Chosen
shape (from three offered): **one agentic-led Index** — fold K + I + agentic into a single composite
with agentic the dominant weight. Not "agentic replaces the headline," not "two side-by-side
indices." One number, agentic-driven.

This spec proposes the weighting + scaling + integration, and lists the open questions for red-team.

## 2. Why this is defensible (and why it was 0% before)

- For a **local-deployment decision layer**, tool-use / agentic capability is the *actual task*;
  knowledge and instruction-following are proxies for it. Weighting the proxy above the task is
  backwards for the stated purpose.
- It was 0% in v1.2 for two reasons, **both now resolved**:
  1. v1.2 locked the headline to the only **validated, discriminating** axes (K, I). Agentic had no
     validated judge-free bench at lock time.
  2. The old agentic axis was **BFCL** — saturated and gameable, deliberately un-promotable.
  The new **AppWorld-C** harness is judge-free (deterministic `evaluate()`), and early data
  discriminates across models (gemma 11.5% vs Qwen 14.6%). The campaign now scoring every model
  will establish how cleanly it separates the field (incl. across quants).

## 3. The core problem: combining axes on different scales

Raw axis levels are not commensurable:

| Axis | Bench | Local 27B raw | Frontier (lit.) | Chance |
|------|-------|---------------|-----------------|--------|
| Knowledge | MMLU-Pro | 75–87 | ~88–92 | ~10% (10-way) |
| Instruction | IFBench | 48–76 | ~85 | ~0 |
| Agentic | AppWorld-C ASR | 11–15 | ~30–60 | ~0 |

A naive weighted mean of **raw** values has two failures:
- **Cratering:** composite ≈ 0.5·14 + 0.25·86 + 0.25·76 = ~47 for everyone; the headline "looks
  broken" and compresses.
- **Magnitude ≠ weight:** even at 50% weight, raw agentic contributes only ~7 of ~47 points, so it
  does *not visibly* dominate — contradicting the decision. Its *level* (low) drowns its *signal*
  (discrimination).

So a deliberate **scaling** step is required before weighting.

## 4. Proposed design

### 4.1 Weighting
`composite = 0.50·Agentic* + 0.25·Knowledge* + 0.25·Instruction*` (`*` = scaled, §4.2).
Agentic = the other two axes **combined**. Dominant, not sole. **Tunable** — exact value is a
red-team output, but the floor is "agentic ≥ K and ≥ I individually, and ≥ ~0.45 of the total."

### 4.2 Scaling — fixed-reference per-axis normalization (STABLE)
For each axis, freeze a `[floor, ceiling]` at v2.0 lock and map:

```
scaled = clamp( (raw - floor) / (ceiling - floor) * 100, 0, 100 )
```

The floor/ceiling are **frozen design constants** recorded in the scorecard — **not** computed from
the current field. So a model's score never moves when other models are added (reproducibility
preserved, same philosophy as v1.2's frozen scoring object). Re-scaling only happens on a
deliberate re-lock (v2.1+).

**Proposed constants (the main red-team target):**

| Axis | floor | ceiling | rationale |
|------|-------|---------|-----------|
| Knowledge | 0 | 100 | raw accuracy is already a fair 0–100 |
| Instruction | 0 | 100 | raw accuracy is already a fair 0–100 |
| Agentic | 0 | **50** | AppWorld-C ASR ~50% is a strong result for this class; 50→100 lifts agentic into a comparable magnitude without making 14% read as "14/100" |

Worked example (Agentic ceiling 50): Qwen 14.6% → **29.2**; gemma 11.5% → **23.0**. Then composite
(Qwen, K≈86, I≈76) = 0.5·29.2 + 0.25·86 + 0.25·76 = **55.1**. Agentic now contributes ~15 of ~55
(visible), and its 6.2-scaled-point spread vs gemma drives ranking.

**Alternative considered — "% of frozen frontier reference":** ceiling = a designated frontier
anchor's score on each axis, frozen at lock. Makes the composite read as "% of frontier capability,
agentic-weighted" (directly on-thesis: local vs frontier). Rejected as *primary* only because it
couples the scale to a specific anchor set that must itself be frozen + justified; offered to
red-team as a strong contender.

### 4.3 Coverage rule
A **ranked** composite requires all three axes present. A model with no agentic run is
`agentic-pending` — shown, but **not ranked** on the agentic-led Index (no fabricated 0). The
running campaign scores every measured model, so this is transitional. Catalog shells (no scores)
are unaffected (already score-less).

### 4.4 Integration / re-lock
- New `SCORECARD_VERSION = "scorecard-v2.0"`; AXES registry: agentic role `headline`, weight 0.50;
  knowledge/instruction 0.25 each. New `registry_digest` → new `scorecard_id` (intended break).
- New frozen artifact `board_v2.json`; `board_v1.json` retained as historical. Site renders v2.
- Agentic column bar flips **purple → green** (it's a real axis, no longer "experimental/separate").
- Scaling constants (`§4.2`) recorded in the scorecard so every run is self-describing.

### 4.5 Naming / migration
- "Local Intelligence Index" was K+I. Options: (a) keep the name, redefined; (b) rename (e.g.
  "Local Agentic Index" / "Local Capability Index"). K and I remain as **visible columns** + as
  composite inputs; nothing is hidden.
- v1.2 → v2.0 is a deliberate methodology bump, documented in a new METHODOLOGY-v2.0 lock that
  references this spec.

## 5. Risks / open questions for red-team

1. **Over-weighting one hard bench.** Agentic = a single bench (AppWorld-C). 50% weight on one bench
   is concentration risk (one bench's quirks/contamination/format-sensitivity move the headline a
   lot). Mitigation options: cap agentic <50%; add a second agentic bench before lock; report
   agentic CI prominently. **Is 50% on one bench acceptable, or stage it (e.g. 0.4) until a 2nd
   agentic bench exists?**
2. **Scaling ceiling for agentic (the "50").** Arbitrary? Better tied to (a) a frozen frontier
   reference, (b) the bench's empirical strong-result, or (c) left raw with a higher weight? What is
   the *most defensible, stable* choice?
3. **Noise vs signal.** Local agentic spread so far is ~3pp (gemma→Qwen) and the run-to-run
   determinism delta is still being measured. If agentic's noise floor ≈ its cross-model spread,
   a 50% weight amplifies noise into the headline. **What discrimination/repeatability bar must
   agentic clear before it earns 50%?**
4. **Reproducibility of fixed constants.** Does freezing `[floor, ceiling]` as design constants
   (vs deriving from a frozen reference set) create a hidden "we picked numbers that flatter the
   field" critique? How to justify the constants publicly.
5. **Composite interpretability.** After scaling+weighting the number is "weighted % of frozen
   achievable range." Is that honestly explainable on the methodology page, or does it obscure?
6. **Anchors.** Frontier anchors will have much higher agentic ASR; with agentic at 50% they may
   leap the local models on the headline. Is that desired (honest: frontier is better at the real
   task) or does it undercut the "local leaderboard" frame?

## 6. Sequencing
Spec (this) → red-team → finalize constants/weight → implement (registry + board_v2 + web) →
**populate as the campaign finishes scoring every model** → re-freeze METHODOLOGY-v2.0. The board is
not yet launched, so this revises a pre-launch design, not a published number.
