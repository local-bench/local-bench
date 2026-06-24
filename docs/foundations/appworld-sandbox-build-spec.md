# Build spec: AppWorld-C process-isolation sandbox + eval seam (security foundation)

Implements the SANDBOX + eval-seam sections of `agentic-axis-design-LOCKED-2026-06-23.md`.
This is the security foundation for the AppWorld-C (interactive API-coding) candidate axis. It is a
re-architecture, not a patch — the canary suite proved AppWorld in-process execution is NOT a sandbox.

## NON-NEGOTIABLE ACCEPTANCE GATE
The build is DONE only when BOTH hold (I will re-run these myself):
1. **`cli/tools/appworld_canary_suite.py --json` reports `SUCCEEDED: 0` (all 55 BLOCKED)** when the
   model code is executed THROUGH the new sandbox instead of raw `world.execute()`. Today that suite
   reports **31 SUCCEEDED / 14 CRITICAL** against raw `world.execute()` (independently reproduced; see
   `docs/foundations/appworld-canary-attack-surface-2026-06-23.md`). Every one must flip to BLOCKED.
   **GATE ON THE PARSED SUCCEEDED COUNT, NOT THE EXIT CODE** — AppWorld's `SafetyGuard.__init__`
   globally rebinds `builtins.SystemExit = Exception`, so in-process `sys.exit`/exit codes are
   unreliable (observed: same run reporting 31 successes exited 0 once and 1 another time).
2. A **scripted NON-LLM agent** solves >=2 real dev tasks (e.g. `fac291d_1`, `50e1ac9_1`) end-to-end
   THROUGH the sandbox (incremental code blocks via the `apis` proxy, then harness `complete_task` +
   `evaluate`), reaching `success: True` — proving the proxy preserves legitimate task-solving.

If any canary still succeeds, the sandbox is NOT done — do not work around the suite; fix the boundary.

## ARCHITECTURE (the only boundary that works: process isolation)
Two processes per task, communicating over a private unix socket / pipe. (Separation is mandatory not
only for the untrusted code but because **AppWorld init has GLOBAL host side-effects** — e.g.
`SafetyGuard.__init__` rebinds `builtins.SystemExit = Exception` process-wide — which must not pollute
the harness/scorer; only the trusted env-host should ever import/init AppWorld.)

- **TRUSTED process** ("env host"): owns the real AppWorld `world` (and thus the data, `requester`,
  DBs, `ground_truth`, evaluator). Runs in the WSL appworld venv with `APPWORLD_ROOT` set. Exposes a
  narrow RPC server with exactly these operations:
  - `call_api(app, api, kwargs) -> json` : executes `apis.<app>.<api>(**kwargs)` in the real world and
    returns the JSON-serializable result (or a structured API-error mirroring what the model would see).
  - `api_docs(...)` : forwards `apis.api_docs.*` (on-demand docs) so the model is not handed all 457 APIs.
  - `finalize(answer) -> verdict` : harness-owned; runs
    `world.execute("apis.supervisor.complete_task(answer=<answer>, status='success')")` then
    `world.evaluate().to_dict()`; returns `{success, passes, failures, ...}`.
  - NOTHING else. No file reads, no raw code exec from the untrusted side, no `requester` exposure,
    no `world` object exposure, no eval/state-management passthrough.
- **UNTRUSTED process** ("code runner"): runs the model-written Python blocks. MUST NOT be able to
  reach AppWorld data, `world`, `requester`, or the env host internals — proven necessary because the
  canary suite escapes every in-process namespace restriction (aliased `open`, `os.environ` path
  rebuild, `apis._requester`, `__closure__`/`__globals__`, `__subclasses__()`). Therefore the boundary
  is the PROCESS + FILESYSTEM, not a namespace allow-list:
  - Launch under **bubblewrap** (`bwrap`) if available (install via apt in WSL if needed), else
    `firejail`, else document the fallback. Required isolation: NO bind-mount of `APPWORLD_ROOT` or the
    appworld package data; an **empty tmpfs** scratch as cwd and `$HOME`; **scrubbed env** (no
    `APPWORLD_ROOT`, no paths that lead to the data tree); **no network** except the single unix socket
    to the env host; `--unshare-all` (keep only the socket), drop caps, `no_new_privs`; CPU / memory /
    PID / wall-time limits; fresh process per task (no cross-task contamination).
  - Inside it, run model code via `exec()` in a namespace whose only AppWorld surface is a thin `apis`
    proxy object: `apis.<app>.<api>(**kwargs)` -> serialize -> RPC `call_api` -> return result. Keep a
    secondary in-process allow-list (safe builtins + `re`/`json`/`math`/`datetime`/`itertools`/
    `collections`) as a BELT, but the wall is the process/FS isolation — even a full namespace escape
    must find nothing sensitive in this process.
  - The `apis` proxy must NOT carry any attribute (`_requester`, `__closure__` globals, client, etc.)
    that leads back to a real Requester/TestClient/world. It is a plain object built in the untrusted
    process that only knows how to send `(app, api, kwargs)` over the socket.

## EVAL SEAM (fix the 3 adapter bugs from the feasibility proof; lives in the TRUSTED host)
- Replace the non-existent `world.verify(...)` call (`agentic_exec/adapter.py:107`) with the
  `finalize` flow above (complete_task then `evaluate().to_dict()`).
- Map results (`agentic_exec/adapter.py:111`): `passed = to_dict()["success"]`;
  `collateral_damage = ("assert no model changes." in failed-requirements)`; build `checks` from
  passes+failures requirement strings. Do NOT reference non-existent `.passed`/`.collateral_damage`.
- Observation parsing: `json.loads` -> `ast.literal_eval` -> raw str (never assume JSON).

## DETERMINISM (in the untrusted runner)
AppWorld fixed task time (no real `datetime.now()`); seed/disable `random`; fixed `PYTHONHASHSEED`,
locale, timezone, task order; deterministic observation canonicalization; per-block stdout capture.

## SCOPE / CONSTRAINTS
- WSL Python 3.12 appworld venv (per `appworld-install-results.md`). The sandbox is a Linux/WSL
  component. Build it under `cli/src/localbench/scoring/agentic_exec/` (new modules e.g.
  `sandbox.py`, `env_host.py`, `apis_proxy.py`) + tests under `cli/tests/`.
- ADDITIVE: do NOT change `web/`, `axes.py`, scorecard, the scorer, `top_k`, the headline lanes, or
  `cli/runs/`. Do NOT register the agentic axis in the registry (stays weight-0 candidate). Do NOT
  `git push`/`commit`.
- GPU-free / endpoint-free build + tests (no model, no llama-server; port 8000 is busy). The scripted
  agent is hand-written deterministic code, not an LLM.
- This build is the sandbox + eval seam ONLY. The Protocol C agent loop (model-output -> code-block ->
  sandbox -> observation -> iterate, turn cap 24, per-block rollback) + diagnostics + scorer wiring are
  SEPARATE follow-up builds; keep the sandbox interface clean so the loop can sit on top.

## DELIVERABLES
- The sandbox + env-host + apis-proxy modules + eval-seam fix, with a clean Python API the agent loop
  will call (e.g. `with AppWorldSandbox(task_id) as sb: obs = sb.run_block(code); ...; v = sb.finalize(ans)`).
- A pytest that runs the canary suite THROUGH the sandbox and asserts 0 successes, plus the scripted
  2-dev-task solve. Report: canary before/after counts, the scripted-solve verdicts, and the WSL
  command to reproduce. STOP and report if bwrap/firejail are unavailable and no robust fallback exists,
  rather than shipping a namespace-only "sandbox" that the canary suite would defeat.
