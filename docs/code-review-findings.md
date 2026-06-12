# Code review findings (2026-06-12) → refactor agenda

Read-only adversarial review (codex, grounded). Verdict: NEEDS FIXES. Drives the
`refactor/architecture` branch. Each fix is live-tested (pytest + build_data + Playwright E2E)
and committed separately.

## Findings

### HIGH (correctness / statistics)
1. `cli/src/localbench/_scoring.py:91` — `chance_corrected` is `max(0.0, corrected)`: clamps
   below-chance performance to 0 and the clamp propagates into `composite()`. Biases weak models
   upward. **Fix:** store the UNCLAMPED signed score; clamp only in explicitly-labeled display code.
2. `web/build_data.py:134` — CI bootstrap drops errored items, but the CLI point counts errors as
   incorrect → the interval can exclude failures the point includes (point/CI inconsistency).
   **Fix:** count errored scored items as `False` in the bootstrap inputs too; track error counts separately.
3. `web/build_data.py:87,95` — web CIs use a single artificial stratum per bench and pass flat bool
   lists, losing the stratified bootstrap estimand the scoring module implements. **Fix:** carry
   per-item strata (difficulty) in the run JSON and feed real `BenchSample`s to `per_bench_ci`/`composite_ci`.

### MED
4. `cli/pyproject.toml` — `langdetect` not a runtime dep; IFEval language checks silently fall back to
   ASCII heuristics (`scorers/ifeval/_shared.py:71`) → non-English items mis-score on normal installs.
   **Fix:** require langdetect, or skip+warn explicitly.
5. `cli/src/localbench/scorers/ifeval/_checks_format.py:47` — constrained-response accepts any allowed
   phrase as a substring → "respond with exactly one of …" can wrongly pass with extra text. **Fix:**
   require the stripped response to equal exactly one allowed option.
6. `cli/src/localbench/_requests.py:147` — **security**: HTTP provider error bodies persisted verbatim
   into result errors → can store echoed API keys / proxy diagnostics / unbounded text. **Fix:** store
   status + a short redacted snippet; never the full body by default.
7. `suite/genmath_gen/build.py:115` — private sentinel falls back to the PUBLIC deterministic seed when
   `LOCALBENCH_GENMATH_PRIVATE_SEED` is unset → "private" items become reproducible if misconfigured.
   **Fix:** require an explicit secret seed for private builds; reserve the default for tests only.
8. `web/components/home-leaderboard.tsx:40` — **honesty**: assigns rank numbers and sorts by composite
   across the whole index, while the site states Quick is UNRANKED and lanes don't mix (anchors are
   api-uncapped, Qwen is answer-only). **Fix:** partition ranked Standard vs Quick estimates and by lane;
   suppress rank numbers for unranked rows.

### LOW
9. `web/build_data.py:119` — `replicated` set from anchors-or-≥3-runs, but trust = independent-account
   replication; the bundled triplet is identical-config self-repeat. **Fix:** require explicit
   independent-replication metadata before setting the flag.
10. `cli/src/localbench/scorers/mcq.py:12` — final-answer marker patterns disable the distinct-letter
    conflict check → "Final answer: A or B" scores as A. **Fix:** reject final-answer spans with
    multiple distinct allowed choices.

## Solid (keep): bootstrap/paired-delta determinism + paired alignment + weight normalization;
genmath verification + public/private disjointness; React escaping + static export + `dynamicParams=false`.

## Refactor steps (architectural through-line: ONE scoring source of truth, consistent point+CI)
- **Step 1 — scoring unification (1,2,3):** unclamp stored chance-corrected (display-clamp only);
  runner emits per-item difficulty/stratum; build_data reuses scoring with consistent error-handling +
  real strata. Rebuild web data; live-test (numbers/CIs consistent; site renders).
- **Step 2 — leaderboard honesty (8,9):** partition by lane + ranked/unranked; suppress rank for
  unranked; fix `replicated` semantics. Playwright E2E on the new structure.
- **Step 3 — hardening bundle (4,5,6,7,10):** langdetect dep; IFEval exact-match; redact provider error
  bodies; require private seed; mcq conflict check. pytest + targeted tests.
- Final: full E2E + re-review + merge decision.
