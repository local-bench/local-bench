Start by running `git diff main...HEAD --stat` and then inspect the changed files (and their full diff
via `git diff main...HEAD <file>`) — this is the surface to review.

This is a RE-REVIEW of the `refactor/architecture` branch (diff vs `main`). The branch fixed the 10
findings in docs/code-review-findings.md across 4 commits (scoring unification; honest leaderboard;
hardening bundle; an mcq regression fix). Your job has TWO parts:

PART 1 — CONFIRM each of the 10 original findings is correctly and completely resolved (not just
superficially). For each: RESOLVED / PARTIAL / NOT-RESOLVED with the file:line of the fix.

PART 2 — HUNT FOR REGRESSIONS the refactor itself introduced. The whole point of this refactor is to
FIND bugs, not introduce them. One regression was already caught and fixed (the #10 mcq fix had
over-rejected "answer is A because B is wrong" -> None; now repaired). Look hard for MORE in the
changed code:
- web/build_data.py: the unclamped point recompute, error-as-incorrect CI inputs, and stratum_for_item
  wiring — is the point ALWAYS consistent with the CI now? any item double-counted or dropped? does the
  bench fallback for id-less items break stratification or determinism?
- cli/_scoring.py: unclamped signed_score storage — any consumer that assumed 0..1 and now breaks on
  negatives (manifest, comparisons, display)?
- cli/scorers/mcq.py: the new marker regex — any input where it now extracts the WRONG letter or misses
  a clearly-stated answer? adversarially try odd phrasings.
- cli/scorers/ifeval/_checks_format.py + _shared.py: does exact-match constrained-response now reject
  responses the OFFICIAL IFEval would accept? does the langdetect-absent path change pass/fail for
  present-langdetect installs?
- cli/_requests.py: does redaction ever corrupt a legitimate non-secret error, and is truncation applied
  after redaction (so a secret split across the 200-char boundary can't leak)?
- suite/genmath_gen/build.py: can any NORMAL workflow (tests, suite rebuild, build_data) now hit the
  raise-on-missing-private-seed unexpectedly?
- web leaderboard: does lane-scoped ranking / unranked handling break if a Standard row ever appears?

<grounding_rules>Cite file:line from the actual branch diff. Real issues only; mark hypotheses
[hypothesis]. Distinguish a true regression from a pre-existing limitation. Prefer few high-value findings.</grounding_rules>

<structured_output_contract>
Output ONLY:
1. VERDICT: SHIP / SHIP-WITH-NITS / FIX-FIRST.
2. Findings table — one per line: `[crit|high|med|low] file:line — issue — fix`. Put any REGRESSION first
   and tag it REGRESSION.
3. Per-finding resolution line for the 10 originals: `#N RESOLVED|PARTIAL|NOT — file:line`.
Keep it scannable. No preamble.
</structured_output_contract>

<action_safety>READ-ONLY. No edits, no commits, no network, no benchmark runs.</action_safety>
