# Cold-install QA audit — `localbench` CLI (2026-06-24)

Read-only audit of the clean-machine path `install → fetch-suite → run → verify → submit`, traced
through `pyproject.toml → cli.py → suite_resolver → orchestrate/runner → scorers → packaging`. Goal:
find what breaks/confuses a brand-new user BEFORE the wheel is built. No edits/installs/GPU were made.

**Good news up front:** `import localbench` is clean (empty `__init__.py`); a dead endpoint does NOT
traceback (per-item `httpx.TransportError` is caught); the agentic/AppWorld/bwrap harness is fully
isolated (imported only inside `scoring/agentic_exec/**` — the CLI never imports it); the coding-exec
lane is opt-in and shells out to `docker` (no POSIX-only imports); the intended public bundle exists
(`release/suites/core-text-v1/<hash>/`, MMLU-Pro 400 + IFBench 294 only).

## BLOCKERS (v1)

### B3 — pip/pipx users cannot OBTAIN the suite (THE launch-promise blocker)
`fetch_suite` requires `--source` to be an already-extracted **local directory**
(`suite_resolver.py:89-93`); there is NO download/URL path ("remote auto-fetch is not configured",
`suite_resolver.py:69`), and `assemble_core_text_v1_bundle` (`suite_bundle.py`) is **not wired to any
CLI subcommand**. The only valid `--source` is `release/suites/core-text-v1/<hash>/`, which exists
**only in a git clone**. → `pipx install localbench` (the stated v1 promise) has no `release/` dir and
no command to produce one ⇒ **cannot fetch the suite at all**. "install → fetch → run" holds only for
repo clones today.
**Fix (small):** (a) bundle `core-text-v1` into package-data exactly like `tiny-smoke-v1`
(`pyproject.toml:32`; it's a few hundred KB) and extend `_package_data_suite`
(`suite_resolver.py:151-153`, currently serves only `tiny-smoke-v1`); OR (b) publish the bundle as a
downloadable artifact + add a `fetch-suite` URL mode. **Home: #30 (host bundle) / revisits #28
(distribution decision — bundle exists but has no user-facing fetch path).** Decision for Michael.

### B1 — default `run --bench all` on the repo suite aborts at scoring (vendored BFCL evaluator)
A repo user pointing at the real superset (`--suite-dir suite/v1`, which the docs invite) with the
default `--bench all` renders `bfcl_multi_turn` (`suite/v1/suite.json:84`); at scoring,
`_scoring.py:score_bench` (no try/except, 63-90) → `score_bfcl_multi_turn` → `_backend.py:85-87`
**raises `BackendLoadError(f"Missing vendored BFCL evaluator at {_BFCL_ROOT}")`**, where `_BFCL_ROOT`
is hardcoded to `cli/.venv/bfcl-eval-ref/...` (`_backend.py:14-17`, inside gitignored `.venv`). The
whole run aborts AFTER driving the endpoint (all tokens spent) and **never writes a run JSON**. Same
for `lcb`/`ruler_32k`/`amo`/`olymmath_hard`. NOT fatal for users who fetch the *public* bundle
(mmlu_pro+ifbench only, `suite_bundle.py:16 PUBLIC_BENCHES`).
**Fix:** wrap the per-bench scorer so a scorer/`BackendLoadError` degrades that bench to errored items
+ a warning instead of aborting the run; and gate un-initializable benches BEFORE driving the endpoint
so tokens aren't wasted.

### B2 — REPRODUCE/quickstart skips the mandatory `fetch-suite` step
`DEFAULT_SUITE_ID = core-text-v1` (`suite_resolver.py:15`) but package-data ships only
`tiny-smoke-v1`; with no `--suite-dir`/`LOCALBENCH_SUITE_DIR`/cache, resolution raises
`SuiteResolutionError` (`suite_resolver.py:67-72`). `docs/REPRODUCE.md:13-21` presents `localbench
run …` as the one-command path with **no preceding `fetch-suite` and no `--accept-suite-terms`** — a
new user hits the resolver error immediately. (The author's own `release_test.py:58-68` DOES fetch
first, so the required sequence is known, just undocumented.) Interlocks with B3 (the `--source` it
would document only exists in-repo). **Fix:** document `fetch-suite … --accept-suite-terms` before
`run`, once B3 gives pip users a real source.

## SHOULD-FIX
- **S1 — no endpoint preflight.** Dead/cold server → N redacted `ConnectError` items + 0% composite +
  warning pile, no "nothing is listening at <endpoint>, start your llama-server" message
  (`_requests.py:126-131`; `_doctor` checks only the suite, `cli.py:296-305`). Add a fail-fast
  connectivity probe at the top of `_run` and/or have `doctor` probe `--endpoint`.
- **S2 — `transformers>=4.51` is a hard dep but only used by the opt-in `--hf-model-id` path**
  (lazy import `prompt_rendering.py:87`). Move to an optional extra `[hf]`; raise "install
  localbench[hf]" from the existing ImportError branch (`prompt_rendering.py:90-93`). Keep
  anyio/httpx/langdetect/math-verify core.
- **S3 — repo-relative `parents[N]` defaults break from a wheel.** `cli.py:462-463`
  `_default_v1_suite_dir()` (`parents[3]/suite/v1`) is the default for `localbench code` → unusable
  off-repo; `scoring/metadata.py:82` (`parents[4]/suite/v0`) silently drops ALL subgroup/stratum
  metadata in `compare` (degrades, no crash); `board_support.py:15-19` + `_backend.py:14` repo-anchored
  (board is scorer-side, lower priority). Resolve `code`'s default via `resolve_suite_dir(...)`; warn
  when metadata is unavailable instead of silently dropping it.
- **S4 — suite-identity mismatch.** `suite/v1/suite.json` is `"version":"suite-v1"` with **no `id`**;
  CLI canonical id is `core-text-v1` (bundle stamps it, `suite_bundle.py:65`). Repo runs work only
  because `--suite-dir` short-circuits verification. Manifest then records `suite_version:"suite-v1"`
  + `suite_id:"core-text-v1"` — a provenance inconsistency. Add an `id`/identity to the file, or
  document that `suite/v1` is the internal superset vs `core-text-v1` the published subset (genuinely
  different bench sets).
- **S5 — default `--lane answer-only` ≠ documented headline `capped-thinking`** (`cli.py:114-116` vs
  REPRODUCE). A bare-command user gets answer-only scores not board-comparable to the headline.
  Make the default match the headline lane, or warn on divergence. (Methodology call — Michael.)
- **S6 — NOTICE files not in package-data** (`pyproject.toml:32` ships only tiny-smoke + licenses).
  Wheel would ship IFBench/BFCL-derived scorer code WITHOUT its NOTICE (IFBench scorer carries the
  Ai2 Apache-2.0 header, `ifbench/scorer.py:1-13`) — a **license-compliance gap**. Add NOTICE files
  (+ `data/board_sources.json` if `board` stays user-facing) to package-data. Lands on #25 (license).

## NICE-TO-HAVE
N1 `--bench all` renders `bigcodebench_hard` (838 KB jsonl) then excludes it (`orchestrate.py:146`
after `render_benches`) — exclude exec-lane before rendering. N2 hardcoded `~/.cache/huggingface/...
gemma-4-31B-it` fallback (`prompt_rendering.py:120-129`, gated to `--hf-model-id`). N3 tracked
`cli/src/localbench.egg-info/` is STALE (SOURCES/requires.txt reflect an old layout) — gitignore/remove
(`.gitignore` already excludes `*.egg-info/`; this one predates the rule). N4 README "Status" still
says "P0 validation spike… naming TBD" + no quickstart (`README.md:18`). N5 see S5.

## Could NOT verify without building the wheel / clean env
Wheel actually contains `data/suites/tiny-smoke-v1/*`; `pip install` resolves all 5 deps cleanly on a
clean Win/Mac (esp. math-verify, transformers + torch transitive); B1 runtime (traced statically,
unambiguous, not executed); public-bundle SHA256SUMS/itemset-hash verify on fetch; end-to-end `run`
against a real endpoint (manifest population + run-JSON write); `web/build_data.py` execution.

---
*Full agent transcript in this session (agent a198…). Synthesis: B3 is the one true launch blocker
(decision needed); B1/S1/S3/S6 are a focused fix-sprint; B2/N4 are docs; S2/S5 are scope/methodology
calls for Michael.*
