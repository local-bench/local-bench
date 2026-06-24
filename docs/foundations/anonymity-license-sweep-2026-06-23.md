# Anonymity + License Hygiene Sweep — 2026-06-23

Mechanical sweep of `cli/src`, `cli/tests`, `.gitignore`, and repo-level license/NOTICE
files. No scorer, axes registry, scorecard logic, board scripts, or `web/` files touched.

---

## 1. Identity / Path Leaks Found and Fixed

### 1.1 `cli/tests/board_fixtures.py` — line 96 (default `output_path` in `run_record()`)

**Leak:** `r"C:\Users\Michael\local-bench\cli\runs\fixture.json"` hardcoded as the default
`output_path` field in the shared fixture factory used by multiple test files.

**Fix:** Replaced with `r"C:\local-bench\cli\runs\fixture.json"` — still a Windows-style
path (needed by the board's path-stripping tests) but contains no personal directory.
Intent unchanged: the fixture provides a plausible run path for downstream tests.

**File:line:** `cli/tests/board_fixtures.py:96`

---

### 1.2 `cli/tests/test_board_manifest.py` — line 54 (operator-identity test input)

**Leak:** `r"C:\Users\Michael\local-bench\cli\runs\fixture.json"` injected as the
sensitive `output_path` that the board's anonymisation logic must strip.

**Fix:** Replaced `Michael` with `operator`:
`r"C:\Users\operator\local-bench\cli\runs\fixture.json"`.

**Intent preserved:** The forbidden-list check in this test uses `r"C:\\Users\\"` (no
username), so any `C:\Users\*` path satisfies the adversarial input requirement. The
test still verifies that personal Windows paths are stripped from board output.

**File:line:** `cli/tests/test_board_manifest.py:54`

---

### 1.3 `cli/tests/test_ifbench.py` — line 285 (reference-checker temp path)

**Leak:** `Path("C:/Users/Michael/AppData/Local/Temp/local-bench-ifbench-ref")` hardcoded
as the location for an optional reference checker (returns `None` if absent — the path
is a dev-only optional parity check, not a required test dependency).

**Fix:** Added `import tempfile` at the top of the file and replaced the hardcoded path
with `Path(tempfile.gettempdir()) / "local-bench-ifbench-ref"`. Resolves to the same
directory on the original machine and to the correct temp dir on any other machine.

**File:line:** `cli/tests/test_ifbench.py:285` (import added at line 7)

---

### Test results after fixes

Ran `pytest tests/test_ifbench.py tests/test_board_manifest.py -v` with the venv
interpreter (`cli/.venv/Scripts/pytest.exe`):

```
64 passed, 1 warning in 1.09s
```

All tests green. The 1 warning is an upstream `pkg_resources` deprecation in a
third-party wheel (`syllapy`) — unrelated to these changes.

---

## 2. .gitignore Changes

Both `.superpowers/` and `.pytest-review/` confirmed **untracked** (not git-tracked) via
`git ls-files`. Added two entries to the repo-root `.gitignore` under a new
`# Tooling / scratch (not product artifacts)` comment:

```
.superpowers/
.pytest-review/
```

No product directories (e.g. `cli/src/localbench/data/`, `release/`, `docs/`, `suite/`)
were touched.

---

## 3. License / NOTICE Reconciliation

### Release bundle (authoritative — already correct)

`release/suites/core-text-v1/<hash>/`:
- `LICENSES/IFBench-ODC-BY-1.0` — present and correct (ODC-BY-1.0, not Apache-2.0)
- `LICENSES/IFEval-Apache-2.0` — present and correct
- `LICENSES/MMLU-Pro-MIT` — present and correct
- `NOTICE` — lists MMLU-Pro (MIT) and IFBench_test (ODC-BY-1.0) correctly
- `ATTRIBUTION.md` — lists all three with correct source repos and revisions

No changes needed to the bundle.

### Repo-root NOTICE — fixed

**Gap:** `NOTICE` at repo root mentioned MMLU-Pro (MIT) and IFEval (Apache-2.0) but
**omitted IFBench entirely** — the dataset that a prior audit incorrectly labeled
Apache-2.0 before the correction to ODC-BY-1.0.

**Fix:** Added `- IFBench_test by AllenAI/Ai2, dataset license ODC-BY-1.0.` as a new
bullet between MMLU-Pro and IFEval. Text is consistent with the release bundle NOTICE.

No IFBench Apache-2.0 label found anywhere in the repo (the prior incorrect label was
already corrected before this sweep).

---

## 4. FLAGS — Items Left for Human Review

### FLAG-A: Repo-root `LICENSES/` is incomplete

`LICENSES/` at repo root contains only `Apache-2.0.txt`. There are no `MIT.txt` or
`ODC-BY-1.0.txt` files here, even though the repo-root NOTICE and the release bundle
both reference those licenses. The release bundle's `LICENSES/` directory is complete.

**Action required:** Either copy `MIT.txt` and `ODC-BY-1.0.txt` into the repo-root
`LICENSES/` dir, or add a comment to the NOTICE directing readers to the bundle for
full license texts, or confirm that the repo-root `LICENSES/` is intentionally minimal
(only covering IFEval/Apache-2.0 since that is the only code-derived license at repo
level — the dataset licenses travel with the bundle). This is a legal-policy call, not
a mechanical fix.

### FLAG-B: `cli/` has no `LICENSE`, `NOTICE`, or `ATTRIBUTION` at package level

The published wheel (`cli/`) contains no top-level license notice. If the wheel is
published to PyPI or distributed standalone, consumers get no in-package attribution.
Confirm whether a `cli/NOTICE` or `cli/LICENSE` is needed before public distribution.

### FLAG-C: IFBench verifier-code Apache-2.0 provenance (ATTRIBUTION.md note)

The release bundle `ATTRIBUTION.md` notes: "AllenAI IFBench code is Apache-2.0; local-bench
also reuses IFEval-style Apache-2.0 verifier patterns." This is already documented in
the bundle but is not reflected in the repo-root NOTICE. No change made here — the
repo-root NOTICE covers dataset redistribution; code-level provenance at scorer level
is a separate concern. Flag for review if you intend the repo-root NOTICE to be
exhaustive for code provenance too.

### FLAG-D: `cli/tests/board_fixtures.py` is imported by multiple test files

`board_fixtures.py` is a shared test helper (not in the package). `test_board_manifest.py`
imports it directly. Confirm that the new fixture `output_path` value
(`r"C:\local-bench\cli\runs\fixture.json"`) does not break any other test that
asserts a specific literal value from `run_record()["output_path"]`. A quick grep
found no other test asserting that literal, but a full test run (all tests, not just
the touched files) should be performed before shipping.

---

## Summary Table

| # | File | Line | Type | Action |
|---|------|------|------|--------|
| 1 | `cli/tests/board_fixtures.py` | 96 | Personal path in fixture | Fixed — `C:\Users\Michael\...` → `C:\local-bench\...` |
| 2 | `cli/tests/test_board_manifest.py` | 54 | Personal path in test input | Fixed — `Michael` → `operator` |
| 3 | `cli/tests/test_ifbench.py` | 285 | Hardcoded AppData/Local/Temp path | Fixed — `tempfile.gettempdir()` |
| 4 | `.gitignore` | — | Missing scratch-dir entries | Fixed — added `.superpowers/`, `.pytest-review/` |
| 5 | `NOTICE` (repo root) | — | IFBench omitted entirely | Fixed — added ODC-BY-1.0 attribution line |
| A | `LICENSES/` (repo root) | — | MIT + ODC-BY-1.0 texts absent | FLAG — policy call |
| B | `cli/` package | — | No in-package LICENSE/NOTICE | FLAG — needed before PyPI |
| C | Repo-root NOTICE | — | IFBench code provenance gap | FLAG — low priority, already in bundle |
| D | `board_fixtures.py` | 96 | Full test suite not run | FLAG — run all tests before shipping |
