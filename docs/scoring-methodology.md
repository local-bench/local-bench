# Scoring methodology — composite index design (v2, post-red-team)

Status: 2026-06-12. Red-teamed by GPT-5.5 xhigh (verdict: approve-with-changes; 10 findings,
9 adopted). The composite is the sortable summary; the 3-axis profile is the headline.
Current code ships the v0-simple path (§2 chance-corrected arithmetic mean) for P0 validation
only; the paired/bootstrap/stratified machinery below is the P1 build.

## 0. Purpose (drives every downstream choice)

Answers: *"where does my setup (model × quant × runtime × settings) sit, and is the ordering
of my own quants stable, sensible, and honestly bounded?"* Not AA's job (rank the frontier).
- **Monotonicity over discrimination** in the local + quant region (Q8 ≥ Q6 ≥ Q4; 27B > 9B).
- **Temporal stability** — your score must not move when someone else ships a model.
- **Lead with the 3-axis profile; composite is the sortable summary, not the hero**
  (red-team #7). The scalar sorts; the per-axis profile diagnoses (which is what quant-
  shoppers actually need). Quant ordering uses dominance language: better / worse / tied /
  **mixed**, each "within uncertainty".

## 1. Three estimands — never conflated (THE central correction, red-team #1)

The same raw scores answer three different questions with three very different error bars:

| Estimand | Question | Error source | Quick-tier (252) magnitude | Supports |
|---|---|---|---|---|
| **Repeatability** | does my score reproduce across reruns of the SAME items? | run-to-run only | composite SD ≈ 0.49 → 95% ≈ ±1.0 | "stable score" |
| **Paired quant-delta** | did Q4 differ from FP16 ON THESE items? | run-to-run, paired (item noise cancels) | SE ≈ √2·0.49 ≈ 0.69 → 95% ≈ ±1.4; 80%-power MDE ≈ **1.9 pts** | **2-3 pt quant deltas ✓** |
| **Generalization** | would this hold over the UNIVERSE of such questions? | item-sampling | single-run 95% ≈ ±6.5; two-setup 80% MDE ≈ **13 pts** | only ≥Standard / pooled n |

**Product consequence (honesty rule):** quant deltas are reported as *"on local-bench
suite-v0 fixed items, −X.X ± [paired CI]"* — NEVER as a universal "Q4 degrades knowledge by
X%". Universal claims require the generalization estimand → Standard tier or pooled
cross-user data. The marketing language may never outrun the paired CI.

## 2. Per-bench score (v0-simple, already in code)

`raw` = accuracy; `signed = (raw − c)/(1 − c)`, c = chance (MMLU-Pro 0.10; IFEval, genmath 0).
**Do NOT clamp for inference** (red-team #3 — clamping at 0 clips sub-chance noise and biases
floor scores upward). Carry the SIGNED value through all math/CIs; clamp to [0,1] for cosmetic
display ONLY, and render "≤0 (≈chance)" when the CI crosses zero.

## 3. Normalization: ABSOLUTE (survives red-team)

Chance-corrected absolute scaling, not relative/Elo — temporal stability is non-negotiable for
"track my setup / compare my own quants." Caveat accepted (red-team #2): chance-corrected
accuracy is an ORDINAL-ish, not interval, scale — a 5-pt gain on saturated math ≠ a 5-pt gain
on hard MMLU-Pro. Mitigation = bench-quality gates, not a different normalization:
- target per-item pass rates roughly 20-80% across the model range; report each bench's
  effective information / discrimination; a saturated bench (e.g. genmath 98% for the 9B in
  P0 — too easy) gets harder items or is down-weighted/revised at the quarterly window.
- saturation is a BENCH-QUALITY problem, never papered over with rescaling.

## 4. Uncertainty: bootstrap, not Wilson+quadrature (red-team #4, #5)

Items are NOT iid Bernoulli (subjects, templates, graders, IFEval multi-instruction →
correlated failures, reduced effective n). Therefore:
- **Per-bench / per-domain CI:** stratified item bootstrap (resample within
  subject/template/difficulty strata), not Wilson.
- **Composite CI:** nested bootstrap (item resample ⊗ repeated-run stochasticity); do not
  combine asymmetric interval endpoints in quadrature.
- **Quant-vs-FP16:** paired bootstrap / McNemar on item-level discordance — NOT two
  independent CIs subtracted.
- Always report repeatability CI and generalization CI as separate numbers.

## 5. Aggregation + weighting

- Weight by capability DOMAIN, not bench count; v0 = Knowledge / Instruction-Following /
  Math, equal 1/3; added benches split their domain's weight.
- **Arithmetic mean for the composite index** (interpretable, sortable) — BUT it is fully
  compensatory and hides axis-specific damage (red-team #6: [66,66,48] and [60,60,60] both =
  60). So degradation is ALSO reported as per-domain delta + **worst-axis delta**, and the
  profile (not the scalar) is the headline. Geometric still rejected (collapses on one near-0
  axis).
- Weights are explicit, published, versioned (index-v1); slider override deferred.

## 6. Anti-gaming: private holdout (red-team #8)

A public frozen suite invites Goodhart/contamination (a 10-pt contaminated domain moves the
composite 3.3 pts — bigger than the quant deltas we sell). Defenses:
- **Generated-math is split:** publish the committed public set for reproducibility; keep an
  UNPUBLISHED sentinel (secret seed / withheld templates) at matched difficulty. Flag any
  setup whose public-vs-private gap is large → contamination/gaming canary. This sharpens
  (not replaces) the "generated variants are the moat" stance.
- MMLU-Pro/IFEval are already public → contamination is a disclosed caveat; the private
  generated-math sentinel is the canary that something is off.
- Publish formulas + aggregate stats, not necessarily every live anchor item.

## 7. Subgroup integrity (red-team #9 — Simpson's paradox)

Domain averages alone hide the degradation users care about (a quant that helps easy items
and breaks hard ones nets ~0 at domain level). So every domain is stratified by difficulty
bucket (+ subject/template, prompt length where available), and quant comparisons carry a
**"no severe subgroup regression"** flag computed on the strata, not just the mean.

## 8. Reasoning lanes / quant-sensitivity (unchanged)

Composite computed within a reasoning lane only. Tokens-to-answer reported beside accuracy,
never folded in. Quant-sensitivity is its own per-axis figure, not blended into capability.

## 9. Governance

index-v{n} tags {normalization, domains, weights, aggregation, CI method}; suite-v{n} tags
items independently; changes versioned, never silent; methodology page shows every formula
and weight.

## 10. Roadmap: latent-trait scoring — START SMALL (red-team #10)

2PL IRT is a solo-founder trap (needs dense per-item responses, DIF checks across model
families, local-independence violations). Minimum viable path instead:
1. fixed ANCHOR items + stratified randomized forms;
2. score with post-stratified means or **1PL/Rasch with item fixed effects + shrinkage**;
3. graduate to 2PL only with dense response data AND evidence it improves rank stability.
This still buys the subset-comparability benefit (anchor linking) without the full apparatus.

## Decisions banked / open
- BANKED (red-team-confirmed): absolute normalization; unclamp-for-inference; bootstrap CIs;
  three-estimand honesty rule; paired quant-delta design; private generated-math sentinel;
  difficulty stratification; 1PL-before-2PL.
- OPEN for Michael: §0 — confirm "3-axis profile leads, composite sorts" as the UI hierarchy
  (red-team strongly recommends; aligns with always-decomposable). Product call, not math.
