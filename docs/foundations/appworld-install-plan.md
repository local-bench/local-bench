# AppWorld install + wiring plan — `agentic_exec_appworld_lite_v0`

Date 2026-06-23. Status: **EXECUTION-READY PLAN (do this deliberately, in order).** This is the
real-AppWorld wiring step for the agentic axis. The harness package
(`cli/src/localbench/scoring/agentic_exec/`) is BUILT + unit-tested against a hermetic stub
(`stub_appworld.py`); this plan replaces that stub with **real AppWorld** and gates it.

Authorities honored: `agentic-harness-build-spec-v0.md` (BUILD AUTHORITY),
`v1-expanded-scope-plan.md` (binding v1 plan + AppWorld traps), `v1-launch-checklist.md`
(AppWorld pilot section). Where a fact is NOT determinable from the code/source it is marked
**[UNVERIFIED]** and listed as a maintainer decision.

> **GPU gate (standing rule):** nothing in this plan runs the RTX 5090. Steps 1–6 are install +
> verify + a NON-LLM scripted run (CPU). The 12-task smoke (step 7) needs the model server and is
> **explicitly out of scope here** — it waits for an explicit GPU go-ahead. Build/install/verify
> freely; do not launch any model.

---

## 0. The integration determination (READ FIRST — everything below follows from this)

### 0.1 How localbench calls AppWorld: **IN-PROCESS Python import** (not a server, not a subprocess)

The harness uses a clean SEAM pattern. `AppWorldLiteAdapter`
(`cli/src/localbench/scoring/agentic_exec/adapter.py`) holds a world object and calls four
methods directly on it — these are the seams the stub implements and real AppWorld must satisfy:

| Adapter seam (today → stub) | Real AppWorld equivalent | Mechanism |
|---|---|---|
| `world.load_task(task_id) -> spec` (instruction, family, band, allowed_tools) | `AppWorld(task_id=…)` + read `world.task.instruction`; family/band/allowed_tools come from **our manifest**, not AppWorld | in-process object construction |
| `world.call_api(tool, arguments) -> JsonValue` | **synthesize** `apis.<app>.<api>(**arguments)` as a one-statement Python string → `world.execute(code)` → capture result | in-process IPython exec |
| `world.verify(task_id, answer) -> EvalResult` | `world.execute("apis.supervisor.complete_task(answer=…)")` then `world.evaluate().to_dict()` | in-process |
| `world.task_ids()` | `from appworld import load_task_ids; load_task_ids("<dataset>")` | in-process |

Confirmed from AppWorld source/docs:
- AppWorld's ONLY native execution path is **`world.execute(python_code_string)`** (a stateful
  IPython shell — like a Jupyter cell). **There is NO structured single-API-call method.** So our
  `call_api(tool, arguments)` seam must **build a single Python statement** of the form
  `print(apis.<app>.<api>(**arguments))` (one call, one turn — this is precisely the
  "wrap AppWorld APIs behind a strict JSON protocol, NOT code-as-action" mandate). The adapter,
  not the model, writes that one line; the model only ever emits our JSON.
- Default mode is **in-process library mode**: AppWorld uses FastAPI's `TestClient` to simulate
  the 9 apps' HTTP without running a real server ("it is not necessary to start a server …").
  So a single Python process holds the live `AppWorld` object AND the app backends.
- Evaluation is the deterministic AppWorld unit-test suite over DB state snapshots
  (`world.evaluate()`), exactly the judge-free final-state verifier the spec wants.
- A **server mode exists but we do NOT use it** for v0: `appworld serve apis` (port 9000),
  `appworld serve environment` (port 8000), and `appworld serve mcp …`. The remote path
  (`AppWorld(task_id=…, remote_apis_url=…, remote_environment_url=…)`) is a documented escape
  hatch if in-process proves unstable — see Risk R3.

**Consequence:** the harness must run in the SAME interpreter that imports `appworld`. The four
seams are method calls on a live Python object with a stateful IPython session and per-task DB
reset — this cannot be split across processes/OSes without adopting AppWorld's server mode.

### 0.2 Windows vs WSL: **the harness runs in WSL Python 3.12; the Windows 3.14 CLI orchestrates it**

Hard environment facts on THIS box (probed 2026-06-23):

- **Windows**: the ONLY interpreter is **Python 3.14.2** (`%LOCALAPPDATA%\Programs\Python\Python314`).
  The localbench CLI venv (`cli\.venv`, `pyvenv.cfg` → 3.14.2) is 3.14. **No 3.11/3.12 on Windows.
  No conda/mamba anywhere.**
- AppWorld `requires-python = ">=3.11,<4.0"`; recommended setup is `conda create … python=3.11.0`.
  3.11/3.12 is the proven band. **Python 3.14 is too new** — its many native/pinned deps
  (sqlmodel, pydantic, freezegun, the encrypted bundle, faker, pendulum, …) are not validated on
  3.14; **do not even attempt AppWorld on the 3.14 Windows venv.**
- **WSL2 Ubuntu 24.04.3** is installed + running: **`python3.12` = 3.12.3**, `pip 24.0`, `venv`
  works, 78 GB RAM, x86_64, glibc Linux (AppWorld's native target). No `python3.11`, no conda —
  but **3.12 is inside AppWorld's supported `>=3.11,<4.0` band**, so 3.12 is the cleanest available
  home and avoids installing conda just for one env.

**The boundary, spelled out:**
- Because the call is in-process and AppWorld can't live on the Windows 3.14 venv, the agentic
  harness package executes inside **WSL Python 3.12**, where `import appworld` works in-process and
  `world.execute(...)` runs natively on Linux. **AppWorld lives ONLY in WSL — never on Windows.**
- The Windows `localbench.exe` CLI (3.14) does NOT and cannot host the agentic axis in-process. Its
  role is **orchestration**: it shells into WSL to launch the agentic run (or you run the agentic
  entrypoint directly inside WSL). The board-merge / scorecard-registry step (a pure-Python,
  AppWorld-free read of the produced run JSON) can stay on the Windows CLI.
- **Model endpoint reachability (the second leg of the boundary):** the harness drives the model
  over an **OpenAI-compatible HTTP endpoint** (`httpx` → `…/v1/chat/completions`, e.g.
  `http://localhost:8080/v1`; see `docs/REPRODUCE.md`, `cli/src/localbench/runner.py`). Running the
  harness in WSL means **WSL must reach the llama-server**:
  - If `llama-server` runs **inside WSL** (the box already uses WSL for llama.cpp/nvidia-smi): use
    `--endpoint http://localhost:8080/v1` — same network namespace, trivial.
  - If `llama-server` runs **on Windows**: WSL2 reaches the Windows host via the default gateway
    (probed: `172.18.64.1`) UNLESS mirrored-networking is on (then `localhost` is shared). Probed
    `http://localhost:8080` from WSL returned HTTP 000 (nothing serving right now — fine, no GPU).
    **Decision for maintainer (M4):** run llama-server in WSL (recommended — co-locates with the
    in-WSL harness, one namespace) OR pass the Windows host IP / enable mirrored networking.

**Net determination:** *in-process import, in WSL Python 3.12. The Windows 3.14 CLI is an
orchestrator only; AppWorld never touches the Windows venv. The only cross-boundary hops are
WSL→llama-server (HTTP) and Windows→WSL (process launch).*

### 0.3 What the harness was written against

- **No real `appworld` import exists anywhere yet** (grep: only `stub_appworld`). The harness was
  built 100% against the hermetic stub, by design (Codex sandbox blocks network — see build spec
  "Codex build instructions"). So the version to pin is a fresh decision (§2), not a recovered pin.
- `hashing.py` carries placeholder identity constants that MUST be updated at wire time (§6.4):
  `ADAPTER_VERSION="stub-appworld-lite-v0"`, `VERIFIER_VERSION="stub-final-state-v0"`,
  **`APPWORLD_VERSION="stub-appworld-api-shape-v0"`** → replace with the real pinned version +
  bundle/data hash so the scorecard identity reflects real AppWorld.
- The axis is **deliberately NOT registered** in `cli/src/localbench/scoring/axes.py` (explicit
  comment there: re-add the `Axis(...)` only "when the agentic data lands" with a frozen
  `scorer_version` + real items). Do not register it during install/verify; register only after the
  96-task scored run exists (§8).
- Config (`config.py`) hardcodes the spec lane: `max_tool_calls=11`, `max_turns=12`,
  `token_budget_per_turn=768`, `token_budget_per_task=6144`, `context_window=32768`, `temperature=0`,
  `top_k=1`. These are the budgets the feasibility proof (§5) tests against.
- Env vars the harness expects today: **none AppWorld-specific** (the stub needs nothing). Real
  AppWorld adds **`APPWORLD_ROOT`** (§3) and the determinism trio the spec mandates
  (`PYTHONHASHSEED=0`, `TZ=UTC`, `LC_ALL=C.UTF-8`). Dataset identifiers are AppWorld's standard
  splits: `train`, `dev`, `test_normal`, `test_challenge` (loaded via `load_task_ids(<split>)`).

---

## 1. Pre-flight (WSL, no network yet)

```bash
# All AppWorld work happens in WSL. Open a WSL shell:
wsl.exe
# Confirm the interpreter + tools (expect 3.12.3 / pip / venv OK):
python3.12 --version
python3.12 -m pip --version
python3.12 -c "import venv; print('venv OK')"
```

If `python3.12` were ever missing, install it in WSL (`sudo apt install python3.12 python3.12-venv`)
— do NOT fall back to the Windows 3.14 interpreter for AppWorld.

---

## 2. Pinned install — exact versions

**Python:** 3.12.3 (WSL system) — inside AppWorld's `>=3.11,<4.0`. **[Decision M1]** acceptable vs
the README's literal `python=3.11.0`: 3.12 is supported by the metadata; pin to it for
reproducibility on this box. If verify (step 5) is not green on 3.12, fall back to a 3.11 conda env
(install Miniforge in WSL) — see Risk R1.

**AppWorld version to PIN: `appworld==0.1.3.post1`** (latest *released* on PyPI, uploaded
2026-02-17; `requires-python <4.0,>=3.11`). **Do NOT track GitHub `main`** — `main`'s
`pyproject.toml` is the unreleased `0.2.0.dev0` (build backend `uv_build`, reshuffled deps, an
`mcp` extra). A frozen benchmark pins a released, stable version; `0.2.0.dev0` is a moving target
and would make the scorecard identity non-reproducible. **[Decision M2]** if a specific feature is
needed only in `0.2.0.dev0`, pin to an exact git SHA on `main` instead (record the 40-char SHA),
never the floating branch.

```bash
# Use a dedicated venv OUTSIDE the repo (keeps AppWorld deps off the localbench CLI venv and the
# repo tree). ~/appworld-harness is in WSL $HOME, not under /mnt/c/.../local-bench.
python3.12 -m venv ~/appworld-harness/venv
source ~/appworld-harness/venv/bin/activate
python -m pip install --upgrade pip
pip install "appworld==0.1.3.post1"

# Record the EXACT resolved dependency set for reproducibility (commit this lock OUTSIDE the data
# tree — e.g. paste into the scorecard provenance, not into APPWORLD_ROOT):
pip freeze > ~/appworld-harness/appworld-0.1.3.post1.lock.txt

# Unpack the encrypted app/code bundles into site-packages:
appworld install
```

The localbench harness package must be importable in this same venv. Two clean options
**[Decision M3]**:
- **(recommended) editable install of the CLI into the AppWorld venv**:
  `pip install -e /mnt/c/Users/Michael/local-bench/cli` — but this drags the CLI's own deps
  (transformers, httpx, …) into the AppWorld venv; verify no version conflict with AppWorld's pins
  (httpx/anyio overlap — check after install). OR
- **(lighter) `PYTHONPATH`**: run the agentic entrypoint with
  `PYTHONPATH=/mnt/c/Users/Michael/local-bench/cli/src` so `import localbench.scoring.agentic_exec`
  resolves without installing the whole CLI. Preferred if the CLI's transformers pin fights
  AppWorld's. (The harness module itself imports only stdlib + `localbench._types`; it does not need
  transformers.)

### 2.1 Download data + set APPWORLD_ROOT (outside repo AND outside model/tool reach)

**`APPWORLD_ROOT` = `~/appworld-data` in the WSL user home** (i.e.
`/home/<wsluser>/appworld-data`). This satisfies every trap:
- **Outside the repo:** WSL `$HOME` is not under `/mnt/c/Users/Michael/local-bench`.
- **Outside any path the model/tool layer can read:** the model only ever sees our JSON tool
  protocol + canonicalized observations; the harness exposes ONLY `api_docs.search`,
  `api_docs.get`, whitelisted `<app>.<api>`, `final_answer`. The filesystem path of the data tree
  is never surfaced to the model, and forbidden-tool/host-fs access is a hard fail in the harness.
  Keeping ground-truth/eval files on disk at a path the prompt never references is the guard.
- Do NOT put it under `/mnt/c/...` (slow DrvFs + needlessly Windows-visible).

```bash
export APPWORLD_ROOT=~/appworld-data
export PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8     # determinism trio (spec mandate)
appworld download data --root "$APPWORLD_ROOT"
# Populates $APPWORLD_ROOT/data/ : api docs, datasets, base DBs, task files.
```

### 2.2 Hash the data tree + record dataset IDs (provenance)

```bash
# Deterministic content hash of the whole data tree (sorted; excludes nothing under data/):
( cd "$APPWORLD_ROOT" && find data -type f -print0 | sort -z | xargs -0 sha256sum \
    | sha256sum | awk '{print $1}' ) | tee ~/appworld-harness/appworld-data-tree.sha256

# Record the dataset/task IDs actually present (these become the manifest's selection universe):
source ~/appworld-harness/venv/bin/activate
python - <<'PY'
from appworld import load_task_ids
for split in ("train","dev","test_normal","test_challenge"):
    ids = load_task_ids(split)
    print(split, len(ids))
    # write the full ID lists OUTSIDE the repo for the deterministic selection step (§7)
    open(f"/home/{__import__('os').environ['USER']}/appworld-harness/ids_{split}.txt","w")\
        .write("\n".join(ids))
PY
```

Keep `appworld-data-tree.sha256`, the `.lock.txt`, the AppWorld version, and the bundle hash
together as the **AppWorld provenance block** — these feed the scorecard identity (§6.4). Never
commit the data tree itself, decrypted bundles, task text, or ID-to-groundtruth mappings.

---

## 3. Verification gate (BEFORE any scored task; BEFORE the model ever runs)

Run AppWorld's own validators **in the exact harness venv + env** (a stub passing is NOT evidence):

```bash
source ~/appworld-harness/venv/bin/activate
export APPWORLD_ROOT=~/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8

appworld verify tests   --root "$APPWORLD_ROOT"   # subset of unit tests, ~2–3 min
appworld verify tasks   --root "$APPWORLD_ROOT"   # end-to-end train+dev task validation, ~2–3 min
```

**Green looks like:** both commands exit 0 with their test/task suites reporting all-pass (no
failed unit tests; train+dev tasks validate end-to-end). This proves real DB state reset/save/eval
works on this box.

**On failure:**
- Dependency/build error on 3.12 → create a **3.11** env (Miniforge in WSL:
  `conda create -n appworld python=3.11.0 -y`), reinstall, re-verify (Risk R1). Re-pin §2 to 3.11.
- `appworld install` (bundle decrypt) error → re-run; if it persists, the released-bundle decrypt
  may need a newer point release — reconsider M2 (exact-SHA pin) only if a fix is unreleased.
- Task validation fails for specific tasks → record which; do NOT hand-patch AppWorld. Exclude only
  via documented task-ID selection later, never by editing the env.
- **Do not proceed to feasibility/smoke/scored until BOTH verifies are green.** This is a hard gate.

---

## 4. Wire the real adapter (replace the stub at the SEAM) — code change, still no GPU

This is the one code step; keep it minimal and behind the existing seam so the unit tests stay
valid. Implement a `RealAppWorld` (same four-method surface as `StubAppWorld`) and swap it in via a
builder; the adapter is unchanged.

- `load_task(task_id)`: construct `AppWorld(task_id=task_id, experiment_name=<fixed>)`; read
  `world.task.instruction`; pull `family`/`band`/`allowed_tools` from **our frozen manifest** for
  that task_id (AppWorld does not supply family/band — those are local-bench labels).
- `call_api(tool, arguments)`: split `tool` into `<app>.<api>`; build the single statement
  `print(apis.<app>.<api>(**<arguments>))`; `out = world.execute(code)`; parse `out` back to a
  JSON value; canonicalize via the existing `canonical_observation`. Enforce ONE call per turn (no
  multi-statement code) — that is the protocol invariant. Raise the harness's `TOOL_ERROR` shape on
  AppWorld exceptions so the existing failure policy applies.
- `final_answer(task_id, answer)`: `world.execute("apis.supervisor.complete_task(answer=…)")` then
  `eval = world.evaluate().to_dict()`; map AppWorld's pass/collateral structure onto `EvalResult`
  (`passed`, `collateral_damage`, `checks`). **[UNVERIFIED]** the exact key names in
  `evaluate().to_dict()` (e.g. which keys mark collateral/unexpected DB changes) — confirm against a
  real dev task and map explicitly; do not guess.
- **Fresh world per task** (spec): construct a new `AppWorld(...)` per task and `world.close()` /
  context-manager exit after eval; never reuse a world across tasks; one task at a time, no
  parallel tasks per process.
- Expose the on-demand doc tools (`api_docs.search`, `api_docs.get`) by routing to AppWorld's
  `apis.api_docs.*` (so the model isn't handed all 457 APIs). NEVER expose `python.exec`, shell,
  fs, network, SQL, env reset, or any `evaluation`/`ground_truth`/`setup` API — the adapter
  whitelist already blocks non-listed tools; keep the AppWorld supervisor/eval APIs off the
  whitelist (the harness itself calls `complete_task` on `final_answer`).

Re-run the existing hermetic unit tests (still against the stub) to confirm no regression, then add
a SMALL real-AppWorld smoke test guarded to run only in WSL with AppWorld present.

---

## 5. JSON-feasibility proof (the highest-risk gate) — BEFORE freezing the 96-task manifest

**Why:** AppWorld is natively code-as-action; a task that a Python agent solves with one loop
issuing 40 API calls may be **infeasible** under our one-JSON-call-per-turn protocol with
`max_tool_calls=11` / `max_turns=12`. We must prove feasibility on REAL tasks with the
**non-LLM scripted runner** (`runner.py::ScriptedAgentRunner`) — no model, no GPU.

**Procedure (CPU only, in WSL):**
1. Pick **2–3 real dev tasks per family** (4 families) from `dev` IDs only — selected by ID, NOT by
   reading task text/difficulty/eval (§7 method). These are DEV tasks → allowed for protocol
   calibration (test set stays untouched).
2. For each, hand-author a **deterministic gold `ScriptedPlan`** (the real-AppWorld analogue of
   `default_scripted_plans()` — the `# SEAM: real AppWorld scripted gold paths wire in here`
   marker): the minimal sequence of single `<app>.<api>` calls + `final_answer` that satisfies the
   task. Run via `ScriptedAgentRunner` → it must reach the AppWorld verifier and PASS.
3. Read off **`api_call_count_distribution(logs)`** and per-task `steps_taken` (already instrumented
   in `ScriptedTaskLog`). This is the measured min-tool-calls envelope.

**Decision rule on the result:**
- **All gold paths fit ≤11 tool-calls / ≤12 turns** with margin (target ≤ ~9 to leave the model
  slack for one recovery) → budgets are FEASIBLE; proceed to freeze.
- **Some/most gold paths exceed the cap** → DO NOT silently fail those tasks (that fabricates model
  failures — explicit trap). Choose, in this preference order, and record the choice:
  1. **Pick fitting tasks** — select the 96 from the subset whose gold path fits the cap (cleanest;
     keeps the protocol + budgets identon).
  2. **Raise the cap** — if a whole family inherently needs >11, set `max_tool_calls`/`max_turns`
     from the measured p90 + margin. **This changes the scorecard identity** → it is a NEW scorecard
     id (`…v0` config hash changes via `hashing.py::_config_payload`); record it as such.
  3. **Add a bounded batch action** — a single JSON tool that performs a bounded fan-out (e.g.
     N lookups) in one turn. This is a **protocol change → explicitly a new scorecard id**
     (build spec §"bounded-batch action"); only if 1–2 are insufficient.
- Report the measured numbers (call counts, turns, pass/fail) as a first-class artifact (build spec
  treats this as the #1 deliverable). **The manifest is NOT frozen until this proof passes.**

Also opportunistically gather (still scripted, CPU): observation sizes vs
`max_observation_chars_per_tool=12000` and api-doc sizes vs `max_api_doc_chars_per_call=8000` — if
real AppWorld observations routinely truncate, flag for the smoke step.

---

## 6. Freeze the adapter + manifest (only after §3 green AND §5 proven)

Freeze, in order:
1. **Adapter freeze** (build spec / pilot trap): schema, tool namespace, api-doc exposure, retry
   (`parse_retries=1`), timeouts (`max_wall_time_per_task_seconds=240`), max turns/tool-calls,
   final-answer handling, failure categories (`types.py::FailureReason`), observation
   canonicalization (`observations.py`), transcript hashing (`hashing.py`). No adapter change after
   any scored task is run.
2. **Manifest freeze**: the 96-task subset (4 families × 3 bands × 8, policy family inverted per
   spec) selected deterministically (§7). Freeze BEFORE the model ladder (anti-p-hack).
3. **Identity constants** (`hashing.py`): set `APPWORLD_VERSION="0.1.3.post1"` (the real pin),
   `ADAPTER_VERSION` / `VERIFIER_VERSION` to real (non-"stub") values, and fold the
   **data-tree sha256 + bundle hash** into the scorecard payload so the identity reflects the real
   substrate. Re-run `test_agentic_hash_stability` after, expecting an intentional hash change
   (update the expected hash deliberately — this is the wire-in, not a regression).

---

## 7. Deterministic test-subset selection (task IDs ONLY — never inspect content)

Select the scored 96 (and the 36-lite / 12-smoke tiers) **from task IDs alone**, seeded and
split-balanced, **without** reading task text, ground truth, difficulty, eval reports, or prior
failures (explicit trap in all three authorities):

```python
import hashlib
def pick(ids: list[str], k: int, seed: str) -> list[str]:
    # rank by a stable hash of (seed, id); take the first k. No task content is read.
    return sorted(ids, key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())[:k]
```

- Draw from `test_normal` / `test_challenge` ID lists captured in §2.2 (5 normal + 3 challenge per
  non-policy cell; INVERT to 3 normal + 5 challenge for the `policy_collateral_sensitive` family,
  per spec). Family/band membership comes from our manifest labels, assigned at selection time from
  IDs — not by reading the task.
- The seed is fixed + recorded in the manifest. Selection is pure-function reproducible.
- 12-smoke and 36-lite are deterministic sub-slices of the same procedure (smaller k, same seed) so
  tiers nest.
- **Never** publish test transcripts, decrypted bundles, api-doc dumps, eval traces, or ground
  truth. Publish only: task IDs, family/band labels, budgets, hashes, ASR + diagnostic definitions.

---

## 8. After this plan (handoff to the GPU-gated steps — NOT done here)

Once §1–§7 are complete (install + verify green + adapter wired + feasibility proven + manifest
frozen), the remaining steps are GPU-gated and need an explicit go-ahead (per the standing
GPU-ask-first rule), in this order from `v1-expanded-scope-plan.md` §"GPU queue":
- **12-task smoke** (1 weak + 1 strong local) — earliest detector of JSON-format / per-turn-token /
  tool-call-budget / state-reset / adapter failure; also gathers build-time validations #2 (per-turn
  token budget vs reasoning models) and #3 (format-failure floor).
- If smoke passes → **36-lite** (determinism + failure-mode distribution, not ranking).
- → **96-task candidate** across all v1 systems → freeze `board_v1.json` from the scorer → register
  the `Axis(...)` in `scoring/axes.py` with a frozen `scorer_version` (the registry comment's
  condition) → promotion-gate evaluation (weight 0 until ALL gates pass).

---

## Open risks + decisions for the maintainer

**Decisions to confirm (referenced inline):**
- **M1** — pin Python **3.12.3** (WSL) vs install 3.11 via Miniforge. *Recommendation: try 3.12.3
  first; fall back to 3.11 only if `appworld verify` is not green.*
- **M2** — pin **`appworld==0.1.3.post1`** (released) vs an exact git SHA on `main` (`0.2.0.dev0`).
  *Recommendation: the released `0.1.3.post1`; only SHA-pin `main` if a needed fix is unreleased.*
- **M3** — make the harness importable in the AppWorld venv via **editable CLI install** vs
  **`PYTHONPATH=…/cli/src`**. *Recommendation: PYTHONPATH (lighter; avoids transformers/httpx pin
  clashes — the harness module needs no heavy deps).*
- **M4** — run **llama-server inside WSL** (co-located, `localhost:8080`) vs on Windows (reach via
  host IP/mirrored networking). *Recommendation: in WSL — one network namespace with the in-WSL
  harness; matches the box's existing WSL llama.cpp usage.*

**Risks:**
- **R1 — AppWorld may not install/verify cleanly on Python 3.12.** Its README proves only 3.11.0
  and its deps are heavily pinned. *Mitigation:* 3.11 Miniforge fallback (M1). Detected by §3.
- **R2 — `evaluate().to_dict()` key shape is [UNVERIFIED].** The exact keys marking pass vs
  unexpected/collateral DB changes aren't determinable from docs. *Mitigation:* map them explicitly
  against a real dev task during §4 before any scored run; do not guess in code.
- **R3 — in-process IPython state/`world.execute` may be fragile** under per-task reset at scale
  (leaked variables, time-freezing via freezegun, DB snapshot cost). *Mitigation:* the documented
  **server mode** (`appworld serve environment/apis` + `AppWorld(remote_*_url=…)`) is the escape
  hatch — but it adds ports + a process boundary and changes the scorecard identity; only adopt if
  in-process proves unstable in §3/§5.
- **R4 — feasibility: real AppWorld tasks may exceed 11 tool-calls under one-call-per-turn** (the
  single most likely thing to invalidate v0). *Mitigation:* §5 measures it BEFORE freeze; documented
  fallbacks (pick-fitting / raise-cap / batch-action = new scorecard id).
- **R5 — WSL↔Windows file & line-ending hygiene.** Editing the harness from Windows tools while
  running in WSL: keep `APPWORLD_ROOT` off `/mnt/c` (done), and run the harness with the WSL venv,
  not the Windows venv. *Mitigation:* §0.2 boundary; never cross the interpreter.
- **R6 — confidentiality / protected-material.** AppWorld has a public/protected split +
  encrypted-redistribution rules. *Mitigation:* never publish decrypted bundles, task text,
  transcripts, eval traces, or ground truth; keep the data tree out of git; the data path is never
  exposed to the model.
