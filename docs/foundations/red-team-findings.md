# Suite-v1 red-team findings (verdict: REVISE)

Adversarial review of the synthesis (`suite-v1-methodology.md`). Produced by the
`benchmark-foundations-research` workflow (run `wf_a0ab00d8-67a`, 2026-06-13). The
verdict is **REVISE**: the proposal is a strong draft but **repeats the v0 saturation
mistake on ~3 of its 5 axes** by setting launch weights from (often month-stale)
leaderboard numbers instead of measured anchor discrimination.

## Biggest risk (verbatim)

> The redesign repeats the v0 failure on new benches. The proposal's stated root cause is
> "averaging saturated axes," but it hardcodes 35% of the composite (Coding 15% + Agentic
> 20%) onto two benches that are VERIFIED saturated at the frontier in 2026 — CRUXEval-O
> (GPT-4-class already ~77-82%; a Jan-2024 800-item code-trace task trivial for any
> reasoning model) and BFCL non-live AST (Berkeley re-weighted V4 specifically because
> single-turn AST saturated). Chance-correction, the headline math fix, cannot de-saturate
> either because both have c≈0. The Math axis is also undercut: MathArena declared the
> entire final-answer-competition format dead at the frontier on 2026-05-12 (GPT-5.5 solved
> the last Apex problem; Apex Shortlist 90%+), yet the proposal adopts exactly those rungs
> as its frontier discriminator citing month-stale 23% numbers. Net: of 5 axes, only
> SuperGPQA and IFBench reliably discriminate at the frontier; 2-3 of 5 are decorative —
> structurally the same 2-of-3-flat composite that produced "a 9B looks near-SOTA." The fix
> is non-negotiable: run all four current anchors on every proposed bench and set each axis
> weight proportional to MEASURED frontier spread (weight→0 if anchors fall within ~3 pts)
> BEFORE launch, and be willing to ship fewer, genuinely-discriminating axes rather than
> five where two compress the top.

## Findings

| Sev | Area | Issue | Fix |
|---|---|---|---|
| **CRITICAL** | Coding / CRUXEval-O | Presented as exec-free coding core citing stale "Code Llama 34B ~44-47%". Verified ceilings GPT-4 ~82% / GPT-4.1 77% / GPT-4o ~70% (2024 *non*-reasoning). A Jan-2024 800-item "trace a 3-13 line function and predict output" task is trivial for any 2026 reasoning model → saturated-at-frontier, plus a contamination magnet with no freshness mechanism. The v0 genmath failure transplanted. | Do **not** ship as a scored core axis. Either drop coding from the launch composite (label "reported only" until a Docker lane exists) or demote CRUXEval-O to a labeled saturated-floor rung. Run all 4 anchors on a sample and confirm spread >~5 pts before any weight. |
| **CRITICAL** | Math / MathArena | Leans on MathArena fresh + Apex as discriminators, but on 2026-05-12 MathArena declared the final-answer-competition format **dead at the frontier** (GPT-5.5 solved the last Apex problem; Apex Shortlist 90%+; AIME-2026 avg 0.838). Cites the very blog that kills these rungs. | Drop Apex as a meaningful stretch. Keep fresh-comp only as a floor→mid discriminator + contamination canary (base-7B 0 → reasoning-7B 53% is useful for the *local* range), not frontier headroom. Lean headroom on Olympiad-numeric (Apache-2.0). State honestly that frontier-math separation may be unavailable to a self-hostable final-answer suite. |
| **HIGH** | Agentic / BFCL-AST | The "default-local core" at 20% weight, claimed "no saturation". But BFCL V4's own notes say single-turn tasks "approach saturation" and V4 re-weighted *away* from them. Old 88.5% top numbers; discriminates locally, flat at frontier. | Keep it (it is the only safe local agentic option and discriminates across the *local* range) but cut the weight hard, verify anchor spread first, and label "saturated at frontier — local-range discriminator only". |
| **HIGH** | Composite still averages saturated axes | Launch weights hardcoded *before* any anchor discrimination data exists; ≥2 axes (CRUXEval-O, BFCL-AST) are verified frontier-saturated yet get 35% combined. Chance-correction does nothing (both c≈0). Of 5 axes only SuperGPQA + IFBench reliably discriminate at frontier → structurally the same 2-of-3-flat composite as v0. | Gate weights on **measured** anchor spread, not AA precedent. Weight ∝ measured discrimination, hard floor ~0 for any axis where anchors fall within ~3 pts. Be willing to launch with FEWER axes. "Lead with the profile" helps presentation but does not rescue a composite that blends flat axes. |
| MED | Licensing (serving traps) | (1) SuperGPQA ODC-BY shell wraps "transformed content from other datasets" → inherits unaudited upstream terms; needs item-level provenance filtering before public serving. (2) MathArena fresh+Apex are CC-BY-NC-SA — NC blocks monetization, SA could force derived data under SA. (3) BBEH verified clean (Apache code + CC-BY-4.0 data) — close that flag. | Filter SuperGPQA to clean-provenance items before serving. Prefer generate-our-own fresh-comp math (we own a templating engine) and use MathArena only as an internal cross-reference. Close BBEH flag. |
| MED | SuperGPQA frontier headroom thinner than claimed | Correctly the discriminating core (ODC-BY, post-cutoff, spreads the local range: 7B ~30% → R1 62%). But hard-vs-overall gap at the frontier is only ~5 pts → little frontier-vs-frontier separation. | Keep as the anchor of the suite but right-size the claim: a local-range / small-to-mid discriminator, not a frontier separator. Fine — the product measures distance-to-frontier. Verify 7-14B numbers on our own anchor runs. |
| LOW | IFBench under-sold | Strongest new pick after SuperGPQA: top ~85% (Jun 2026), Apache-2.0 + ODC-BY, programmatic verifiers (no judge), and AA confirms it has *not* saturated in 6 months because instruction-following is orthogonal to what labs train. | Promote to a load-bearing axis with confidence. Apply the IFEval-checker parity discipline (task #13) to the vendored IFBench verifiers. |

## Benches flagged NOT actually local-runnable
- **tau2-bench** — needs API-side tokens for an LLM user-simulator + judge; opt-in only, not "local".
- **BigCodeBench-Hard + LiveCodeBench** — execute model code → Docker-only (so the Coding axis has *no* frontier-grade local-runnable option at all).
- **MathArena Apex** — api-only and now near-saturated → neither local nor a useful stretch.
- **SuperGPQA full set** — runnable (plain MCQ) but not cleanly *servable* without provenance filtering.

## Missing axes worth considering
- A frontier-grade, license-clean, judge-free, local-runnable hard-reasoning bench beyond SuperGPQA may simply **not exist** — if so, state plainly that frontier-vs-frontier is out of scope and the product measures distance-to-frontier.
- **Calibration / hallucination-discipline** axis (own items, programmatic pushback scorer, ±1/0) — orthogonal + saturation-resistant; arguably more valuable than the saturated CRUXEval-O/BFCL axes.
- **Long-context** — a judge-free RULER subset (8k/16k/32k) still sharply separates models and is contamination-clean (synthetic); a stronger discriminator than the coding/agentic cores being shipped.
- An **execution-based coding signal** is absent → be honest that coding ability is essentially unmeasured at launch (CRUXEval-O is a saturated proxy).
