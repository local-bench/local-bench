<task>
Build a sympy-backed SYMBOLIC + numeric math-answer verifier for the local-bench suite-v1 math
ladder (AMO-Bench, OlymMATH-HARD). The existing scorer (cli/src/localbench/scorers/math_numeric.py)
only handles plain numbers via regex+Fraction; olympiad answers are LaTeX/symbolic (\frac, \sqrt,
pi, e, expressions like (x+1)^2, sets, tuples, intervals, ratios) and it cannot verify them.

Repo root: C:/Users/Michael/local-bench (your cwd). CLI package: cli/src/localbench. Tests:
cli/tests. Venv: cli/.venv (use ./.venv/Scripts/python.exe from the cli/ dir). Python 3.13.
</task>

<context>
- Scorer dispatch lives in cli/src/localbench/_scoring.py (a `match bench:` router) and prompt
  rendering in cli/src/localbench/_suite.py. DO NOT EDIT EITHER — the manager (Claude) owns dispatch
  wiring. Your job is the scorer module + tests + dependency ONLY.
- Existing math scorer API (cli/src/localbench/scorers/math_numeric.py), used by the genmath bench:
    extract_final_number(text) -> str | None
    equivalent(a, b) -> bool
    score_math(text, gold) -> bool
  Leave math_numeric.py UNTOUCHED.
- HARD CONSTRAINT — frozen-suite safety: the genmath itemsets (suite/v0/genmath_quick.jsonl,
  suite/v0/genmath_standard.jsonl) are frozen and published anchor scores depend on them. Your new
  verifier must NOT change genmath scoring. Genmath KEEPS using math_numeric.score_math. You must
  PROVE your new verifier agrees with the old one on the genmath gold answers (parity test below).
  Do not alter any suite/ file.
- Equivalence engine: use `math-verify` (HuggingFace, Apache-2.0, sympy-backed; PyPI name
  `math-verify`). It parses LaTeX + plain expressions, checks mathematical equivalence, and can
  extract the answer from raw model output (\boxed, "final answer", etc.). If math-verify cannot be
  installed or imported cleanly in cli/.venv on Windows, FALL BACK to a direct sympy implementation
  (sympy parse + a small LaTeX normalizer) and say so explicitly in your report. Add the chosen
  dependency to cli/pyproject.toml [project.dependencies] and install it into cli/.venv.
</context>

<deliverables>
1. cli/src/localbench/scorers/math_symbolic.py exposing exactly:
     extract_math_answer(text: str) -> str | None       # LaTeX/boxed/marker-aware extraction
     verify_math(response_text: str, gold: str) -> bool  # symbolic+numeric equivalence; gold may be LaTeX
   - verify_math returns True iff the model's extracted answer is mathematically equivalent to gold
     (gold may be LaTeX or plain).
   - Must handle at minimum: integers/decimals/fractions (incl. \frac), negative & signed values,
     scientific notation, surds (\sqrt), pi and e, simple symbolic expressions and equivalent forms
     ((x+1)^2 == x^2+2x+1), ratios (a:b), sets/tuples/intervals where the engine supports them, and
     \boxed{...} extraction. Pure-float comparisons keep a 1e-4 relative tolerance (match the existing
     scorer). Never raise on malformed/garbage model output — return False.
2. cli/tests/test_math_symbolic.py — parametrized unit tests covering EVERY supported answer type
   above PLUS rejection cases (wrong value, empty output, non-equivalent expression, unparseable
   gibberish). BDD naming (test_<thing>_when_<condition>), Given/When/Then comments, matching the
   style of cli/tests/test_math_numeric.py.
3. cli/tests/test_math_genmath_parity.py — load every item in suite/v0/genmath_quick.jsonl and
   suite/v0/genmath_standard.jsonl. For each item's gold answer assert verify_math AGREES with
   math_numeric.score_math on (a) a synthetic CORRECT response embedding the gold answer, and (b) a
   synthetic WRONG response (gold perturbed to a different value). i.e. the new verifier accepts every
   genmath correct answer the old scorer accepts and rejects the perturbed one. If any genmath gold is
   a type the new verifier cannot handle, FAIL loudly (do NOT skip) and name the offending item.
4. cli/pyproject.toml — add the chosen equivalence dependency to [project.dependencies].
</deliverables>

<action_safety>
Touch ONLY these paths: cli/src/localbench/scorers/math_symbolic.py, cli/tests/test_math_symbolic.py,
cli/tests/test_math_genmath_parity.py, cli/pyproject.toml. Install deps into cli/.venv only.
DO NOT edit: _scoring.py, _suite.py, math_numeric.py, anything under suite/, anything under web/, or
any existing test file. No unrelated refactors, no reformatting of code you did not author.
</action_safety>

<verification_loop>
From the cli/ directory: install the dependency into ./.venv, then run
  ./.venv/Scripts/python.exe -m pytest -q
The FULL suite must pass (currently 173; your new tests add to that). Iterate until green. If
math-verify breaks the import, switch to the sympy fallback rather than leaving the suite red.
Report the final pass count and the exact pip install command you ran.
</verification_loop>

<completeness_contract>
End with a concise plain-text report:
- Equivalence engine used (math-verify vs sympy fallback) and why.
- Genmath parity result: how many genmath items checked, all agreed (Y/N), any unsupported types.
- A table: answer types SUPPORTED vs NOT-SUPPORTED (be honest; do not claim untested coverage).
- Final pytest pass count.
Do NOT claim the math ladder is "done" — this is the scorer only; datasets are acquired separately.
</completeness_contract>
