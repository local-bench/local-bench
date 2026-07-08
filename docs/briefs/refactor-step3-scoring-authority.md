<task>
Refactor Step 3 on branch `site-overhaul`: make `localbench.scoring` the SINGLE AUTHORITY for the scoring
math, eliminating the re-implementations in the web `build_data` pipeline — WITHOUT changing the generated
`web/public/data` by a single byte. Highest-leverage but riskiest step; **byte-identity of public/data is a
hard STOP gate.** You implement; Claude byte-diffs independently.
</task>

<context>
The scoring math (signed-score chance-correction, composite, worst-axis, percentile/interval/CI) is
currently RE-DERIVED in Python in `web/build_data.py` (a `_scoring()` block + a `CLI_SRC` `sys.path`
injection near line 219) and a THIRD chance-correction copy in `web/build_data_demo.py` (`_raw_accuracy`,
~line 154). The canonical implementation is `cli/src/localbench/scoring/` (signed_score.py, bootstrap.py,
metadata.py, ...).

CRITICAL CONSTRAINTS (from a red-team of THIS step — heed them):
- `web/build_data.py` runs as a SUBPROCESS (`cli/tests/test_web_build_data.py` shells out to it; the real
  pipeline runs it). So `localbench` must be importable in THAT interpreter — KEEP a subprocess-safe import
  mechanism (retain the `cli/src` sys.path injection at the TOP of build_data.py, or otherwise ensure the
  package resolves). A pytest conftest does NOT cover the subprocess.
- `localbench.scoring` does not currently expose web-ready `interval`/`worst_axis` helpers. If you add a
  public surface, it must reproduce the EXISTING web Python formulas EXACTLY — no clamping, rounding,
  weight-ordering, float-formatting, or JSON-serialization changes.
- The demo path's `_raw_accuracy` is the INVERSE of signed_score via `chance_for_bench` — preserve that
  exact inverse; do NOT "compute via signed_score".
</context>

<deliverables>
1. (3a) Expose a clean public scoring surface in `localbench.scoring` covering what the web re-derives
   (signed_score exists; add/expose composite, worst_axis, percentile/interval/CI, raw-accuracy inverse as
   needed), matching the existing Python formulas byte-for-byte. Do NOT change cli scoring behavior — only
   surface existing logic.
2. (3b) Replace the re-derived `_scoring()` in `web/build_data.py` and the chance-correction copy in
   `web/build_data_demo.py` with imports/calls to `localbench.scoring`; keep the subprocess-safe import
   path; delete the now-dead duplicated Python.
3. Regenerate `web/public/data` with the refactored pipeline.
</deliverables>

<constraints>
- Branch `site-overhaul` ONLY; never main.
- The regenerated `web/public/data` MUST be byte-identical to the committed version. **If you cannot achieve
  byte-identity, STOP and report the exact drift (file / field / number) — do NOT commit a drifting result.**
</constraints>

<verification_loop>
- After regenerating: `git diff --stat web/public/data` MUST be EMPTY (zero byte drift). Non-empty -> diagnose
  the formula mismatch and fix until empty, or STOP and report precisely.
- `pytest cli/tests` from the repo root still **173 passed** (incl. `test_web_build_data` which runs the subprocess).
- `npm run typecheck` / `npm test` / `npm run build` green.
- Commit on site-overhaul ONLY after byte-identity is confirmed.
</verification_loop>

<output_contract>
Return: the public scoring surface exposed; exactly what you deleted from `build_data*.py`; the
subprocess-safe import mechanism kept; and CONFIRMATION that `git diff web/public/data` is EMPTY
(byte-identical). If ANY drift remained, report it precisely instead of claiming success.
</output_contract>
