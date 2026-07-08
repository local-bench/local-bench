# Red-team: why does our suite show frontier ≈ local 27B? (2026-06-16)

Michael (correctly) refused to believe Opus 4.8 ≈ Qwen3.6-27B on our suite and asked for a red-team.
Investigation findings, with evidence. **Conclusion: it is a measurement artifact, not reality. The suite
as-run systematically compresses the top of the range.**

## Finding 1 (MAJOR, verified): ~36% of SuperGPQA answer keys are wrong / ambiguous / garbage.
On the matched 25-item knowledge set, **9/25 items had GPT-5.5 AND Opus (independent frontier labs) agree on
the same answer that contradicts the gold key**; on 6 of those, even local Qwen agreed. When every model
independently agrees against the key, the key is wrong. Verified by hand:
- **supergpqa-002 (Doppler):** approaching 100 Hz, receding 50 Hz → source f₀ = 100·(v−vs)/v with vs=v/3 =
  **66.6 Hz (option H)**. All 3 models said H. **Gold key = B (33.3 Hz) is simply WRONG.**
- **supergpqa-010 (H Lyman/2nd Balmer):** Z²·(3/16)·13.6 = 10.2 → Z=2 → **He⁺ (G)**. Models said G. Gold = E
  (Li²⁺) is wrong.
- **supergpqa-024 (Deleuze's university):** 9 of 10 options are near-identical phrasings of "University of
  Paris (Sorbonne)" — a garbage question; "gold" is an arbitrary phrasing.
- **supergpqa-003:** gold = Provenzale (minority view) vs the textbook "Alessandro Scarlatti" the models picked
  (+ the option text is typo-corrupted "Alessa;ndro Scala").
- **supergpqa-017:** deciduous trees lose leaves "Seasonally" (frontier) vs gold "Annually" — both defensible.

**Effect:** bad keys are unwinnable, so they cap EVERY model at ~52–65% no matter how capable, swamping the
capability signal with key-noise → the frontier's real lead is erased. All three models scored exactly 13/25.

**SOURCE CONFIRMED: SuperGPQA's own keys, NOT our builder.** build_v1_supergpqa.py (L150-158) rejects items
unless the gold letter's option text equals the gold answer-text — so it faithfully imports the source
(letter,text) pair and only validates internal consistency, never correctness. Item 002 passed because
SuperGPQA itself pairs B with "33.3 Hz". So SuperGPQA's source answer keys are wrong (~36% here); a known
risk of large auto-constructed benchmarks. Builder gap: dedup catches only EXACT duplicate options, so
near-identical-option garbage (e.g. the Deleuze item) slips through.
**Action: re-grade/validate keys with a strong-model judge + drop near-duplicate-option items, OR replace
SuperGPQA with a cleaner knowledge bench.**

## Finding 2 (MAJOR, by design): we excluded the math axis from the frontier runs.
Math (OlymMATH/AMO) is where frontier reasoning dominates and a local *answer-only* model floors (~6%). We
dropped it to save cost. That deleted the single clearest discriminator → composite understates the gap.
**Action: run frontier on math.**

## Finding 3: agentic (BFCL) saturates. 96–100 for every capable model — tasks too easy. **Action: harder set
(ToolHop / multi-turn).**

## Finding 4 (found + fixed): BFCL scorer coerced JSON booleans to strings, false-flooring frontier
(Opus 84→96). Commit 0e67ede. Lesson: sweep every scorer for output-format assumptions.

## Finding 5: N=25 is far too small. Each item = 4%; per-axis numbers are noise.

## Honest bottom line
The earlier "discrimination substantially closed" verdict was WRONG — it was measuring through a broken
knowledge axis, a missing math axis, a saturated agentic axis, and a scorer bug. **The suite is not yet a
trustworthy measure of capability.** Priority fixes: (1) clean/validate SuperGPQA keys (or replace the subset),
(2) include math, (3) harder agentic set, (4) bigger N, (5) MCQ extraction robustness. Until then, do NOT
present a frontier-vs-local composite as meaningful.
