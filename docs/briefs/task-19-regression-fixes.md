<task>
Fix THREE regressions the re-review found in the refactor (branch `refactor/architecture`). Each
gets a test. The goal of this refactor is to find-and-fix bugs, not introduce them.

FIX 1 — [high] suite/genmath_gen/build.py: the private-seed requirement now breaks the NORMAL public
rebuild. Running `python build.py` (or `build_files(seed=...)`) with no private seed must still build
the PUBLIC files successfully. Make private sentinel generation OPT-IN:
- `build_files` ALWAYS writes the public standard+quick files (no secret needed).
- It generates the PRIVATE sentinel ONLY when a private seed is resolvable (explicit `private_seed`
  argument OR `LOCALBENCH_GENMATH_PRIVATE_SEED` env). When neither is present, SKIP private generation
  (do not raise) and print a one-line notice that the private sentinel was skipped (no seed).
- Keep the hard failure ONLY for the case where a private build is explicitly requested but the seed is
  malformed/unusable. CLI: `python build.py` → public only, exit 0; `--private-seed N` or env → public+private.
- Public files remain byte-identical (verify sha256 unchanged).
Tests (cli/tests/test_genmath_private.py): `build_files` with no seed writes public files and NO
suite/v0/private dir; with a seed writes both; public hashes unchanged in both cases.

FIX 2 — [med] web/build_data.py `_axes`: the per-bench POINT still reads stored
`benches.<bench>.raw_accuracy`, while the CI is rebuilt from item-level `correct[bench]`. Make the
point derive from the SAME data as the CI: compute `raw_accuracy = mean(correct[bench])` (the rebuilt
list that already counts errors/no-answer as incorrect) and use it for the point via signed_score.
If the recomputed raw accuracy differs from the stored aggregate by > 1e-9, append a data_warning
(stale/inconsistent run JSON) but use the recomputed value. Keep determinism.
Test (cli/tests/test_web_build_data.py): a synthetic run whose stored raw_accuracy disagrees with its
items yields a point computed from the items AND a data_warning; current curated data still matches
(no warnings) and above-chance points unchanged.

FIX 3 — [low] cli/src/localbench/scorers/mcq.py: remove the COMMA from the marker-ambiguity joiners
(`_MARKER_PATTERNS`). Comma is too weak a signal — "Final answer: A, B is wrong" or "A, B is a
distractor" should extract A, not None. Keep `or`, `and`, `/` as ambiguity joiners so "A or B",
"A and B", "A/B" still return None.
Test (cli/tests/test_mcq.py): add ("Final answer: A, B is wrong",10,"A"), ("Answer: A, B is a
distractor",10,"A"); keep the "A or B"/"A and B"/"A/B" -> None cases.
</task>

<action_safety>
Touch ONLY: suite/genmath_gen/build.py, web/build_data.py, cli/src/localbench/scorers/mcq.py, and
their tests (cli/tests/test_genmath_private.py, test_web_build_data.py, test_mcq.py). Do NOT modify
other modules, the web app components, or re-run benchmarks. No git commits.
</action_safety>

<completeness_contract>
Done = full `cli/.venv/Scripts/python -m pytest cli/tests -q` green; `python build.py` (no seed) builds
public only and exits 0; public genmath sha256 unchanged; build_data point now derives from item list;
mcq comma cases extract the stated answer while or/and/slash stay ambiguous.
</completeness_contract>

<verification_loop>
Run the full suite. Run `python build.py` with NO seed (confirm exit 0 + public files + no private dir +
unchanged public hashes). Run build_data and confirm current curated points/CIs unchanged and no new
warnings. Confirm the mcq comma cases. Fix anything failing before finishing.
</verification_loop>

<missing_context_gating>No questions. If skipping private generation, keep the public lock/outputs exactly as before.</missing_context_gating>

<compact_output_contract>
Final: (1) files changed, (2) pytest line + `python build.py` no-seed result + public-hash-unchanged
confirmation, (3) one line per fix, (4) <=4 bullets on anything to double-check.
</compact_output_contract>
