<task>
Refactor step S0 on branch `site-overhaul`: make the cli test suite GATEABLE — runnable cleanly from the
repo root regardless of cwd — WITHOUT changing any production behavior or any test's pass/fail outcome
(other than fixing the genuinely-stale test noted below). You implement; Claude reviews + byte-checks.
</task>

<context>
Repo: C:\Users\Michael\local-bench (branch site-overhaul). Python cli under cli/ (src-layout package
`localbench` at cli/src; tests at cli/tests; venv at cli/.venv). A loose top-level package `attack/`
(cheat-proxy) sits at the REPO ROOT. The web pipeline `web/build_data.py` uses bare sibling imports
(`from build_data_support import ...`) and is shelled out to as a subprocess by `cli/tests/test_web_build_data.py`.

KNOWN PROBLEMS (verified):
- Running `pytest` from `cli/` aborts the WHOLE suite: `cli/tests/test_cheat_proxy.py` does
  `from attack.cheat_proxy import ...` but `attack/` (repo root) is not importable -> collection ImportError.
- `cli/tests/test_web_build_data.py` is STALE: it asserts the built index has NO `index_version`
  (~line 37) but `web/build_data.py` now emits `index_version`. It also depends on gitignored `runs/`
  data that is ABSENT in a fresh checkout (0 tracked run files) -> it errors on missing
  `runs/anchor-gpt55-quick.json`.
- 3 genmath tests in `cli/tests/test_genmath_private.py` fail on a build-hash mismatch. DO NOT touch these
  — that is a separate, behavior-CHANGING issue (version-unstable RNG) flagged for Michael. Leave them failing.
</context>

<deliverables>
1. Add a single `conftest.py` (at the REPO ROOT, or `cli/conftest.py` — your call, whichever makes the
   suite collect from any cwd) that ensures these are importable when running the cli tests:
   `localbench` (from `cli/src`), `attack` (from repo root), and the `web` sibling modules used by
   `test_web_build_data` (so its subprocess and any imports resolve). Prefer minimal, explicit `sys.path`
   additions over packaging churn. Do NOT add unsupported pytest ini options — `addopts` already has
   `--strict-config`, so an unknown option will ABORT collection. Do not change existing addopts.
2. Fix `cli/tests/test_web_build_data.py`:
   - Update the stale `index_version` expectation so it matches what `build_data.py` actually emits.
   - Make it robust to ABSENT `runs/` data: SKIP gracefully (`pytest.skip(...)`) when the required run
     inputs are missing, OR synthesize a minimal temp run fixture so it can exercise the pipeline. Prefer
     skip-when-absent — do not commit any real `runs/` data.
3. Do NOT change any production code (no scoring/genmath/runtime/web behavior). Only `conftest.py` + that
   one stale test. If `attack/` needs an `__init__.py` to be importable, adding an empty one is acceptable.
</deliverables>

<constraints>
- Branch `site-overhaul` ONLY; never main. No production behavior changes. No `runs/` data committed.
- Use the existing venv `cli/.venv/Scripts/python.exe` for verification.
</constraints>

<verification_loop>
- From the REPO ROOT: `cli/.venv/Scripts/python.exe -m pytest cli/tests -q` must COLLECT cleanly (no
  import/collection abort) and run the full suite. The ONLY remaining failures should be the 3 known
  `test_genmath_private` hash tests; `test_web_build_data` must PASS or SKIP (not error); everything else passes.
- Report the exact pass/fail/skip counts before and after.
- Commit on site-overhaul with a clear message.
</verification_loop>

<output_contract>
Return: what you added (conftest location + path additions), the test_web_build_data fix, the before/after
pytest counts (from repo root), and confirmation that NO production code changed (list files touched).
</output_contract>
