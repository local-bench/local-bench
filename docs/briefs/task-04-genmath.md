<task>
Fourth slice for local-bench: the generated-math engine — our own contamination-resistant,
licensing-clean math benchmark. Templates produce parameterized problems with
programmatically computed answers.

1. Generator package: suite/genmath_gen/ (standalone, run with the cli venv; NOT part of
   the localbench runtime package):
   - Template = a class/record with: name, category (arithmetic | number_theory | algebra |
     combinatorics | probability | geometry | rates_word), difficulty (easy|medium|hard),
     param sampler (seeded RNG -> params dict, with bounds), statement renderer (params ->
     natural-language problem text), answer fn (params -> exact answer as int or Fraction).
   - AT LEAST 60 distinct templates spread across all 7 categories (≥6 per category),
     difficulty mix roughly 30% easy / 45% medium / 25% hard. Word problems must read
     naturally (varied names/objects via seeded choice lists), not like mad-libs.
   - Answers MUST be plain integers or simple fractions a/b (the math_numeric scorer
     handles only those — no LaTeX, no decimals requiring rounding, no units in the
     expected answer). Statement must end with: "Give your final answer as a single
     number." (or fraction variant).
   - Independent verification: every combinatorics and probability template MUST include a
     brute-force checker (exhaustive enumeration over a small instance space) used in
     tests to verify the closed-form answer fn on >=50 seeded instances. Algebra/geometry
     templates verify via substitution/recomputation where feasible.

2. Build script: suite/genmath_gen/build.py:
   - Deterministic: --seed 20260612 → identical output files.
   - Generates suite/v0/genmath_standard.jsonl (120 items: max 2 instances per template,
     stratified by category and difficulty) and genmath_quick.jsonl (40 items ⊂ standard).
   - Item fields: id ("genmath-v0-<template>-<k>"), template, category, difficulty,
     statement, answer (string), params (for audit).
   - Updates suite/v0/itemsets.lock.json with the two new files (count + sha256 + seed),
     preserving existing entries. Adds a genmath entry to suite/v0/suite.json (template
     file suite/v0/templates/genmath.txt = "{statement}", decoding policy: temperature 0,
     max_tokens 8192, chance_baseline 0.0).
   - Writes docs/genmath-review.md: for EVERY template — name, category, difficulty, one
     fully rendered sample instance with its computed answer, and (where applicable)
     "brute-force verified: yes/n-instances". This file is for the manager's line-by-line
     math review.

3. Tests: cli/tests/test_genmath_gen.py (import via path or make suite/genmath_gen a tiny
   installable/-e package — your choice, note it):
   - Per-template: 100 seeded instances → answer fn runs without error, renders without
     unfilled placeholders, answer is int or Fraction within sane magnitude (|answer| <
     10^9, denominators < 1000).
   - Brute-force agreement tests for all combinatorics/probability templates.
   - Determinism: two builds with same seed produce byte-identical JSONL.
   - Distribution: standard set has >=10 items per category, both difficulties mixes
     present, no template contributes >2 items.
</task>

<action_safety>
Touch only: suite/genmath_gen/, suite/v0/ (the two new JSONL files, suite.json genmath
entry, templates/genmath.txt, lock-file update), cli/tests/test_genmath_gen.py,
docs/genmath-review.md. Do not modify cli/src, existing item sets, or repo root. No git.
</action_safety>

<completeness_contract>
Done = pytest fully green via cli/.venv; build.py run twice → identical outputs; the two
JSONL files + lock entries + suite.json entry + docs/genmath-review.md all exist with the
counts above.
</completeness_contract>

<verification_loop>
Run the full pytest suite and the double-build determinism check yourself; fix before
finishing. Spot-check 5 rendered problems by solving them independently in your reasoning
and confirming the answer fn agrees; report those 5 checks explicitly.
</verification_loop>

<missing_context_gating>No questions; decide and note.</missing_context_gating>

<compact_output_contract>
Final message: (1) template count per category/difficulty, (2) pytest line + determinism
result, (3) your 5 manual spot-check results, (4) <=8 bullets decisions/deferred.
</compact_output_contract>
