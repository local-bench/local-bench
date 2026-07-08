<task>
Split the generated-math suite into a PUBLIC committed set and a PRIVATE held-back sentinel,
so we have items whose answers a cheater cannot look up (methodology v2 §6 + threat-model:
the contamination/gaming canary). The generator is suite/genmath_gen/ (build.py + templates).

1. suite/genmath_gen/build.py: add a build mode that produces TWO disjoint sets from the
   template bank at MATCHED difficulty/category distribution:
   - PUBLIC: suite/v0/genmath_standard.jsonl + genmath_quick.jsonl (as today), seed 20260612,
     COMMITTED. Unchanged in spirit; keep counts (120 / 40).
   - PRIVATE sentinel: suite/v0/private/genmath_sentinel.jsonl, a SEPARATE seed
     (read from env LOCALBENCH_GENMATH_PRIVATE_SEED, default a distinct constant), ~60 items,
     same category/difficulty mix, generated from the SAME templates but DIFFERENT parameter
     draws so no item overlaps the public set (assert disjoint by (template, params)).
   - suite/v0/private/ MUST be gitignored (add to .gitignore) — the sentinel is never
     committed/published; only its aggregate stats may later be shown.
2. Disjointness + integrity: build asserts zero (statement) overlap between public and private;
   writes suite/v0/private/sentinel.lock.json (count, sha256, seed-source note — NOT the seed
   value) which is ALSO gitignored.
3. docs/contamination-canary.md (committed): explain the design — a setup's public-genmath
   score vs its private-sentinel score at matched difficulty should agree within noise; a
   large public>>private gap flags contamination/answer-lookup/gaming. Note that server-side
   injection of sentinel items into runs + the gap test is a LATER server task; this brief
   only establishes the public/private generation split + gitignore hygiene.
4. Tests (cli/tests/test_genmath_private.py or extend test_genmath_gen.py): public+private
   build is deterministic per their seeds; public/private statements are disjoint; private
   matches the public category/difficulty distribution; private files land under
   suite/v0/private/ and are covered by .gitignore (assert the path is ignored via a
   `git check-ignore` subprocess OR by asserting the .gitignore rule text).
</task>

<action_safety>
Touch only: suite/genmath_gen/*, suite/v0/genmath_*.jsonl + suite/v0/itemsets.lock.json
(regenerate public set identically), .gitignore (add suite/v0/private/), docs/contamination-canary.md,
and the test file. Do NOT create committed files under suite/v0/private/. Do NOT modify cli/src
scorers/runner/providers. No git commits.
</action_safety>

<completeness_contract>
Done = pytest green via cli/.venv; running the build produces the committed public set
(unchanged hashes vs current, since same seed/counts) PLUS suite/v0/private/genmath_sentinel.jsonl
(~60 items, gitignored); disjointness test passes; `git status` shows NO new tracked files under
suite/v0/private/.
</completeness_contract>

<verification_loop>
Run build twice → public identical (same hashes as currently committed), private identical to
itself; assert public/private disjoint; confirm git does not track suite/v0/private/. Fix
before finishing.
</verification_loop>

<missing_context_gating>No questions; choose a sensible distinct default private seed and note it (the value itself may be a constant in code for now; flag that production should move it to env-only).</missing_context_gating>

<compact_output_contract>
Final: (1) files, (2) pytest line, (3) public hashes (confirm unchanged) + private count, (4)
<=5 bullets incl. the disjointness check result and gitignore confirmation.
</compact_output_contract>
