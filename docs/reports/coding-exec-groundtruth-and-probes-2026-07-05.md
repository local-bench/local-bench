# Coding-exec verifier: ground-truth + adversarial-probe report (2026-07-05)

First real execution of the suite-v2 BigCodeBench-Hard verifier in the hardened rootless-Docker
sandbox (image `bigcodebench/bigcodebench-evaluate@sha256:a3cd34ec…`, WSL2 Ubuntu). Two checks
the oracle mandated before any model runs: (1) canonical solutions pass (harness correctness),
(2) named gaming vectors are caught (harness integrity).

## Integration bug found + fixed (the ground-truth check earning its keep)

First run: 0 results, JSON-parse error on empty stdout. Root cause: the evaluation image ships
`ENTRYPOINT=[python3 -m bigcodebench.evaluate]`; `docker_run_argv` never overrode it, so our
`python /work/runner.py …` was appended as arguments to the image's own evaluator. Unit tests
never caught it — they inject a fake runner and never invoke Docker. Fix: `--entrypoint ""` in
`docker_run_argv` (+ regression test). We use the image only as a pinned Python+deps environment.

## Ground-truth (canonical solutions must pass)

Built `scripts/build_groundtruth_run.py`: fetches upstream canonical solutions at the pinned
dataset revision, confirms all 148 tests are byte-identical to our frozen items, feeds each
`code_prompt + canonical_solution` through the PRODUCTION extractor → assembler → sandbox.

- Run 1 (30s/task, default env): 139/148 = 93.9%.
- The 9 failures characterized:
  - **5 network/data-dependent** (bcbh-006, 007, 035, 096, 104): tests need live network
    (urlopen, Google Drive, Wikibooks) or downloaded corpora (NLTK). Our sandbox mandates
    `--network none` for untrusted code — these are **permanently unscoreable here** and every
    model (canonical included) fails them, so they add noise without discriminating.
  - **1 cache-write** (bcbh-043, librosa/numba): numba could not write its JIT cache against the
    read-only rootfs. Fixed by routing library caches into the writable /tmp tmpfs
    (`NUMBA_CACHE_DIR`, `MPLCONFIGDIR`, `XDG_CACHE_HOME`, `HF_HOME`, `NLTK_DATA`, … in
    `runner._sandbox_env`). Security-neutral: confined to the bounded tmpfs, network still off.
  - **3 timeouts** (bcbh-014, 067, 074): heavy imports (TensorFlow-class) exceeded 30s cold.
    Recommended per-task timeout raised to 60s.
- Run 2 (60s/task, cache-env fix): see `runs/groundtruth/bcb-groundtruth.v2.json` — the
  network/data set is the residual; those items are marked non-scoreable in the frozen suite so
  the coding axis is pass-rate over sandbox-scoreable items only. Rationale is forced by the
  security model, not a judgment call.

## Adversarial probes (named gaming vectors must be CAUGHT)

`scratchpad/build_probe_tasks.py` builds 10 probes (2 controls + 8 attacks) whose task is trivial
(`task_func()==42`) so an honest harness fails every attack. Run through the real in-container
runner:

| probe | passed | expected | verdict |
|---|---|---|---|
| control_correct | True | True | OK |
| control_wrong | False | False | OK |
| redefine_testcases | False | False | OK (real test still loads) |
| child_outlives_timeout | False | False | OK (--init reaps; wrong answer fails) |
| network_egress | False | False | OK (--network none) |
| os_exit_before_tests | **True** | False | **GAMED** |
| sys_exit_before_tests | **True** | False | **GAMED** |
| atexit_os_exit | **True** | False | **GAMED** |
| assertEqual_noop | **True** | False | **GAMED** |
| patch_wasSuccessful | **True** | False | **GAMED** |

**Isolation holds; in-process grading integrity does not.** All 5 gamed vectors exploit the same
root cause `program.py` already documents: generation and test share one Python process, and
`pass = subprocess exit 0`. Premature `os._exit(0)`/`sys.exit(0)`/`atexit` forge the exit code;
`assertEqual`/`wasSuccessful` monkeypatches neuter the assertions.

## Blast radius (why this does NOT block tonight)

- Our own project runs (Gemma, Qwopus) are non-adversarial — genuine solutions score correctly.
- Honest models don't game, so the ranking of measured models is unaffected.
- suite-v2 design already forbids community self-reported coding verdicts from ranking, and
  community ranked coding is gated behind moderation (ZT-1+, not live). No adversarial coding
  submission can reach the ranked board today.

## Hardening design (gates adversarial-submission coding ranking; task #39)

Two layers, both required, defeat all 5 vectors:
1. **AST gate on `sanitized_code`** (conformance failure, not a pass, if violated): reject
   `os._exit`/`sys.exit`/`os.kill`/`atexit` references and any top-level statement that is not a
   def/class/import/benign-assign (blocks top-level `unittest.TestCase.assertEqual = …` and
   `TestResult.wasSuccessful = …`). BigCodeBench solutions are ordinary library code; false-
   positive risk is low.
2. **Proof-of-completion sentinel**: the trusted epilogue prints a sentinel with real counts
   (testsRun, failures, errors) computed from the result object; the runner requires the
   sentinel present AND failures==errors==0 AND testsRun>0 — never bare exit 0. Premature exit
   (even from inside `task_func`) means no sentinel → not a pass.
Acceptance test = this probe suite committed as a permanent regression: all 5 attacks must flip
to caught, both controls preserved. To be oracle-red-teamed before any adversarial coding ranks.
