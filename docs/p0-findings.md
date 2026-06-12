# P0 validation spike — findings & go/no-go (2026-06-12)

**Verdict: GO to P1.** The concept is validated on real hardware, the hard problems are
understood with data, and P0 caught several issues that would have silently corrupted a
site built without it. Build cost so far: ~$0.02 of API + one day. Below is what we learned.

## What P0 had to prove, and did

1. **The pipeline runs end-to-end on a real rig** — prompts → local model → answer extraction
   → server-side scoring → manifest → run JSON. Validated against a local vLLM endpoint
   (Qwen3.5-9B stand-in) and a real metered API (OpenAI). 104 automated tests green.
2. **Setups can be ranked reliably** — the make-or-break question. Run-to-run composite
   **SD = 0.49** at Quick tier (252 fixed items); the leaderboard concept is statistically
   viable. This was the single biggest concept risk and it cleared with margin.
3. **The trust model is sound** — the cheat proxy proves transcript scoring can't detect a
   faked submission (94.4% from a "potato-7b" claim); only replication + private items catch
   it. We will never claim "verified"; replication is the trust unit. (docs/threat-model.md)
4. **The scoring math holds up** — methodology v2 red-teamed by GPT-5.5 (approve-with-changes);
   absolute normalization survived; the field's gold-standard composite (Epoch ECI) uses our
   exact techniques (chance-correction + IRT). (docs/scoring-methodology.md, external-crossref.md)
5. **Anchors are affordable** — measured cost log says a full 3-anchor Quick pass is ~$12-75.
   (docs anchor section below.)

## Reference numbers measured (suite-v0, Quick tier)

| Setup | Lane | Composite | MMLU-Pro | IFEval | genmath |
|---|---|---|---|---|---|
| Qwen3.5-9B (local, vLLM) | answer-only | ~85.4 (SD 0.49) | 77 | 83 | 98 |
| gpt-4.1-mini (API anchor, 10/bench) | api | 93.0 | 89 | 90 | 100 |

Ordering is sane (frontier-mini above local 9B; genmath saturates → too easy, flagged).

## Issues P0 caught (the payoff)

- **Cap truncation**: at 2048 tokens, 13/112 MMLU-Pro answers were cut off mid-reasoning, not
  wrong — understating score ~9 pts. Raised to a calibrated runaway ceiling (12288).
- **Reasoning-model parser bug**: vLLM splits thinking (`reasoning_content`) from answer
  (`content`); truncated-mid-think gave empty content and **crashed 43/120 think-on runs**.
  Fixed — now recorded as a (wrong) no-answer, with reasoning captured. 5 new tests.
- **Small models over-think**: the 9B fails to terminate on ~25-36% of hard items even at
  14k tokens (genuine non-termination, not loops) — set the runaway ceiling honestly and is a
  reportable model trait.
- **Reasoning API param mismatch**: GPT-5-series reject `max_tokens`/`temperature` (need
  `max_completion_tokens`, no temp) → P1 anchor-adapter task created.
- **Tiers are lane-dependent**: native-reasoning Quick ≈ 46 min vs answer-only ≈ 9.5 min on
  the 9B — "Quick" must be defined per lane in P1.

## Anchor cost (measured, not guessed)

- gpt-4.1-mini, 30 items, all benches: **$0.019**, 0 errors. Our prompts are tiny (~150 tok);
  cost is driven entirely by output/reasoning tokens.
- Extrapolated full 3-anchor Quick pass: **~$12 (terse) to ~$75 (heavy reasoning)**; Standard
  ~$40-240. Early signal (gpt-5.4-mini answered MCQs in ~30 tokens) hints at the low end, but
  unconfirmed for full frontier models. **Protocol: one ~5¢ probe per provider to get real
  per-model numbers before any committed run; no full anchor spend without Michael's OK.**
- Validates the plan envelope (~$75-250 initial). All three provider keys (OpenAI, Claude,
  Gemini) are available.

## Known limitations carried into P1

- 27B-FP8 (28.5 GB) won't fit the 32 GB card alongside desktop → the FP16 / large-model
  baselines need rented GPUs (already planned); 9B fully validated the methodology.
- IFEval checkers are *adapted*, not byte-vendored → parity test before trusting absolutely
  (task #13).
- genmath saturates a 9B (98%) → may be too easy; verify discrimination against stronger
  models, add harder templates at the quarterly window.
- v0-simple scoring (chance-corrected arithmetic mean) is what's coded; the v1 machinery
  (paired deltas, bootstrap CIs, stratification, private sentinel) is specced but unbuilt
  (tasks #15, #16).

## What P1 needs (ordered)

1. Reasoning-model anchor adapter (#17) → then real anchor probes (measured cost) → 3 anchors.
2. v1 scoring implementation (#15) + private genmath sentinel (#16).
3. Lane-aware tiers + final cap policy; clamp max_tokens to user context window.
4. Web app (Next.js, dark mode, 3-axis profile leads) + manifest-complete CLI + GitHub OAuth.
5. The one-family seeded quant study (the launch hero) — needs a rig that fits the FP16 baseline.

## Open decision for Michael
- UI hierarchy: **3-axis profile leads, composite sorts** (recommended; red-team + Epoch both
  favor decomposition). Confirm before web build.
