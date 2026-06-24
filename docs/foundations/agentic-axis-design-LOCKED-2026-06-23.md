# Agentic axis — LOCKED design + build plan (post-oracle, 2026-06-23)

Synthesis of: feasibility proof (NO-GO on 11-call one-JSON), viability research (Protocol C GO,
independently re-verified by me: median 5 code-blocks, 100% fit at <=11, judge-free), and the
GPT-5.5 Pro oracle red-team (`localbench-agentic-protocol-redteam`). Michael reinstated agentic as
a v1 priority ("scoring agentic capability is the point; cutting it ruins robustness").

## DECISION SUMMARY

### LOCKED (adopted from oracle — not re-litigating)
- **Protocol C: bounded code-as-action.** Model emits ONE Python block per turn; harness runs it via
  the AppWorld executor; captured stdout = observation. Judge-free (AppWorld `evaluate()` = fixed
  deterministic assertion set; verdict identical across action styles).
- **NAME IT HONESTLY: "AppWorld-C / interactive API-coding success rate."** NOT generic "agentic."
  It measures: can the model write incremental Python against a documented API and reason over results.
- **Candidate, weight 0.** Never in the headline Index (Knowledge+Instruction) for v1. Promotion is
  gated on the discrimination/non-saturation/stability/coverage gates AND an orthogonality check.
- **Turn cap = 24** (oracle: 20-24, not 16; cap prevents runaway, must not decide a weak model's
  one extra recovery turn). Calibrated on **dev only**, pre-registered in the manifest. `cap_exceeded`
  is a normal failure reason, its rate reported. NEVER tune the cap on test splits (= test-aware
  hyperparameter leak).
- **STRONG SANDBOX (mandatory before any scored run).** In-process allow-list is belt, not wall.
  Architecture: (1) trusted per-task AppWorld API/env process owns DB state + evaluation; (2) untrusted
  code-runner process/container runs model code with NO AppWorld data mount, empty scratch tmpfs, no
  home, no network except the per-task API endpoint, dropped caps, `no_new_privs`, CPU/mem/PID/time
  limits, fresh per task; (3) inject only a tiny `apis` proxy that serializes calls to the trusted
  process (no raw HTTP/URLs/requester/state-mgmt/eval endpoints); (4) keep in-process namespace
  allow-list as a secondary belt. Verified exploit motivating this: `pathlib.Path(answer.json).read_text()`
  reads the gold answer off disk (AppWorld SafetyGuard blocks `open`/`os` but not pathlib); and direct
  task-DB reads bypass the API layer even without `answer.json`.
- **CANARY EXPLOIT TESTS in CI (acceptance criterion).** Must attempt and HARD-FAIL on success:
  read `answer.json`/task DBs/experiment outputs/logs/`environment_io.md`/`api_calls.jsonl`;
  `/proc/self/environ`, `/proc/*/cmdline`, cwd, env vars; object-graph escapes
  (`().__class__.__base__.__subclasses__()`, `.__globals__`, traceback frames, `sys.modules`);
  `pickle`/`marshal`/`ctypes`/`inspect`/`pydoc`/`breakpoint`/`input`; `pathlib`/`open`/`io`/`os`/
  `subprocess`/`socket`/`requests`/`httpx`/`sqlite3`/`glob`/`shutil`/`tempfile`/`importlib`/`pkgutil`;
  hidden handles inside `apis` leading to `requester`/FastAPI TestClient/DB; cross-task contamination.
- **Reproducibility = two contracts.** (a) Trace-replay: recorded code blocks + frozen data hash +
  AppWorld version + sandbox image hash + env -> same success bool + DB diff (validates harness;
  publish replay hashes). (b) Agent-rerun: same model/sampler/template/prompt/order/seed -> statistically
  consistent success vector (validates the row). Repeats: smoke/lite **3x**, 96-task **2 full reruns**
  for any publishable/promotable row; report mean ASR + run-to-run delta; stability gate = abs delta
  <=5pp, stable error rates, no adjacent rank inversion unless CIs overlap; if 2 disagree > threshold,
  run a 3rd + report mean with task-clustered bootstrap. Determinism in runner: AppWorld fixed task
  time (no real `datetime.now()`), seeded/blocked `random`, fixed `PYTHONHASHSEED`/locale/tz/task-order,
  deterministic observation canonicalization.
- **Diagnostics to FALSIFY the axis (log every run):** invalid-code rate, syntax-error rate,
  runtime-error rate, cap-exceeded rate, collateral-damage rate, API-call count, block count,
  observation-truncation count, doc-tool usage. If AppWorld-C mostly tracks syntax/runtime failures,
  it is a coding diagnostic, not an agentic axis.
- **Per-block API-call cap = HIGH safety cap, not a tight modeling cap** (a low cap becomes a hidden
  second turn cap). Set ~ dev-max + margin; log the distribution first; tighten only if abuse appears.
  On a cap/timeout abort, ROLLBACK to the pre-block checkpoint so partial mutations don't become
  arbitrary collateral damage.
- **Supervisor APIs: KEEP the legitimate user-data ones** (account passwords, profile, addresses,
  payment cards) — the agent needs them to solve tasks. Only the harness owns `complete_task`
  (finalization); strip evaluator/state internals (`world.task`, `world.evaluate`, `save_state`/
  `load_state`, raw `requester`).
- **Anchoring = environment validation, NOT score-matching.** Run AppWorld's own task
  verification/validation solutions under the pinned version + data hash; optionally replay official
  bundled experiment outputs; run one official simple agent on a tiny non-scored sample as a rough
  sanity check only. Acceptance = same environment/evaluator semantics, not same agent score (their
  leaderboard is method x LLM, not pure model).
- **Contamination is a stated limitation.** AppWorld test releases eval programs but not setup/solutions;
  maintainers call it a compromise. For open-weight local models some contamination risk is unavoidable
  -> report it; do not overinterpret small deltas.

### FLAGGED FOR MICHAEL (genuine scope decisions — confirm before I sink the big build hours)
1. **Two-track agentic (oracle's strong recommendation).** Ship AppWorld-C (interactive API-coding)
   AND add a small JSON-native function-calling track (BFCL-style multi-turn) as the construct-validity
   counterweight, so we never present a single misleading "agentic" number. The JSON track is a NEW
   benchmark integration = additional scope. DEFAULT if no objection: build AppWorld-C now, add the
   JSON/BFCL track as a fast-follow. (Tracked: task #33.)
2. **Timeline.** Done-to-this-standard, agentic is a multi-day sub-project (strong sandbox + 2 tracks +
   reproducibility + diagnostics + GPU benchmark with 2 reruns). Consistent with "ship complete, extend
   timing if needed." Tonight I build the AppWorld-C foundation (sandbox + RealAppWorld wrapper + adapter
   fixes + canary tests); GPU benchmark waits for gemma to free the 5090.

## ADAPTER BUGS TO FIX (from the feasibility proof — needed regardless)
- `agentic_exec/adapter.py:107` calls `world.verify(...)` which does not exist -> use
  `world.execute("apis.supervisor.complete_task(answer=..., status='success')")` then
  `world.evaluate().to_dict()`.
- `agentic_exec/adapter.py:111` reads `eval_result.passed`/`.collateral_damage` which do not exist ->
  `passed = to_dict()["success"]`; derive `collateral_damage` from the `"assert no model changes."`
  requirement appearing in `failures`.
- Observation parse must not assume JSON: try `json.loads` -> `ast.literal_eval` -> raw str.

## BUILD PLAN (phased)
- **P0 (tonight, GPU-free, Codex + my review):** RealAppWorld wrapper (eval seam fixed) + the strong
  sandbox (trusted/untrusted split + `apis` proxy, no data mount) + the canary exploit test suite
  (must hard-fail on every escape) + Protocol C agent loop (single code block/turn, cap 24, per-turn
  token cap, per-block high safety cap + rollback) + diagnostics logging + determinism controls.
  Acceptance = canary suite green (all escapes blocked) + a scripted non-LLM agent solves a few dev
  tasks end-to-end through the sandbox.
- **P1 (GPU, after gemma frees the 5090):** smoke (12) -> lite (36) -> 96-task on Qwen ladder + gemma,
  2 full reruns per publishable row; compute ASR + diagnostics + orthogonality vs code-proxy/IFBench.
- **P2 (flagged):** JSON-native (BFCL-style) companion track.
- **Promotion:** only if the gates pass AND AppWorld-C is NOT redundant with code+IFBench. Until then,
  candidate weight 0, displayed as its own clearly-labeled column.

## What stays UNCHANGED
Headline v1 Index = Knowledge (MMLU-Pro) + Instruction (IFBench). Agentic never enters the headline
for v1. Registry keeps agentic unregistered until data clears the gates (zero headline impact).
