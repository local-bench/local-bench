# AppWorld install + verify results — `agentic_exec_appworld_lite_v0`

Date: 2026-06-23. Status: **INSTALL + VERIFY COMPLETE — BOTH GATES PASS.**
Scope of this note: install + environment verification ONLY (GPU-free; no model, no scored run,
no repo code changes, no adapter wiring). Executed verbatim per
`docs/foundations/appworld-install-plan.md` (steps 1–3 + provenance). The orchestrator does the
harness seam-wiring (steps 4–7) afterward.

## Environment used (decision M1: 3.12 — NO 3.11 fallback needed)

| Item | Value |
|---|---|
| Host | Windows 11; AppWorld lives **only in WSL** (Windows Python is 3.14, too new). |
| WSL distro | Ubuntu 24.04.3 LTS, x86_64, glibc Linux (AppWorld native target). |
| WSL user / home | redacted / `/home/<wsl-user>`. |
| Python | **3.12.3** (WSL system interpreter). Inside AppWorld's `>=3.11,<4.0`. Verify GREEN on 3.12 → **3.11 Miniforge fallback NOT triggered.** |
| Isolation | dedicated **venv** at `<wsl-venv>` (off `/mnt/c`, OUTSIDE the repo). pip upgraded 24.0 → 26.1.2 inside the venv. |
| Determinism env | `PYTHONHASHSEED=0  TZ=UTC  LC_ALL=C.UTF-8` (set for download, ID load, and both verify gates). |

## AppWorld version pinned (decision M2: released, NOT main/0.2.0.dev0)

- **`appworld==0.1.3.post1`** (latest *released* PyPI; lock line `appworld==0.1.3.post1`).
- `appworld install` succeeded — unpacked encrypted bundles:
  - apps → `…/site-packages/appworld/`
  - tests → `~/.appworld/tests` (present).
- Key resolved pins (the heavily-pinned stack the plan flagged — all installed clean, no conflicts):
  `pydantic==1.10.26`, `sqlmodel==0.0.10`, `SQLAlchemy==1.4.54`, `freezegun==1.5.1`,
  `Faker==24.14.1`, `pendulum==3.2.0`, `cryptography==39.0.2`, `fastapi==0.110.3`, `ipython==9.12.0`.
- Full lock: `<managed-runtime-dir>/appworld-0.1.3.post1.lock.txt` (80 packages).

## APPWORLD_ROOT + data provenance

| Item | Value |
|---|---|
| **APPWORLD_ROOT** | **`<appworld-root>`** (WSL `$HOME`; OFF `/mnt/c`; OUTSIDE the repo; path never exposed to the model/tool layer). |
| Data root | `<appworld-root>/data` (`api_docs/`, `base_dbs/`, `datasets/`, `tasks/` [734 dirs], LICENSE, README_BEFORE_SHARING.md, version.txt). |
| Data version (`version.txt`) | `0.1.0` |
| Size | **193M** (169,528,045 bytes), **14,696 files**. |
| **Data-tree sha256** (deterministic: `find data -type f -print0 \| sort -z \| xargs -0 sha256sum \| sha256sum`) | **`ff4f3dbc512bdb9c05538388ded339ceeca6f3eb50a450307ac841de07e71934`** |
| Encrypted bundle sha256 (apps.bundle) | `ba58bc5679c3573aa8f60ad6f5cda4377128a0ec569de5eef9543a77561796bb` |
| Encrypted bundle sha256 (tests.bundle) | `93d53dea06f9d7c42cc03b66f4b08e4644c26b5ed41cdeaec0560c792bc16d8f` |

### Dataset task IDs (loaded in-process via `load_task_ids` — a first-order integration signal)

| Split | Count |
|---|---|
| `train` | 90 |
| `dev` | 57 |
| `test_normal` | 168 |
| `test_challenge` | 417 |

(Matches AppWorld's documented split sizes.) Full ID lists written OUTSIDE the repo:
`<managed-runtime-dir>/ids_{train,dev,test_normal,test_challenge}.txt` (feed the deterministic
selection step §7; never committed, never inspected for content).

## Verification GATE (both run in the exact harness venv + determinism env)

### `appworld verify tests` — **PASS** (exit 0)
- Apps suite: **1553 passed** in 25.54s (pytest-8.4.2, 5 parallel xdist workers).
- Other modules: **138 collected, all passed** (`test_common`, `test_model_collection`,
  `test_sqlite_fts`, `test_load_task_ids`, `test_safety_guard`, `test_sqlmodel`, `test_appworld`).
- "All tests passed." Full log: `<managed-runtime-dir>/verify_tests.log`.

### `appworld verify tasks` — **PASS** (exit 0)
- **147/147 tasks** validated end-to-end (90 train + 57 dev) in ~75s — progress bar to 100%, no
  task failures, no tracebacks, clean exit 0.
- This proves real **DB state reset → task execution → `world.evaluate()`** works on this box for
  every train+dev task (the deepest first-order check; a stub passing was explicitly not evidence).
- Full log: `<managed-runtime-dir>/verify_tasks.log`.

**Result: BOTH GATES GREEN.** The hard gate in the plan ("do not proceed until BOTH verifies are
green") is satisfied.

## Boundaries honored
- GPU untouched (install + verify are CPU/network only; no model loaded; no `llama-server`).
- No repo code edited; `axes.py` / `hashing.py` / adapter UNCHANGED (this note is the only repo file written).
- No scored / model / agentic-smoke run. No ground-truth/eval material inspected beyond what
  `appworld verify` itself runs. Data tree, decrypted bundles, task text, and ID→ground-truth
  mappings remain local and uncommitted.

## Handoff to orchestrator (NOT done here — steps 4–7 of the install plan)
Wire `RealAppWorld` behind the existing seam; map `evaluate().to_dict()` keys (plan R2,
[UNVERIFIED]) against a real dev task; JSON-feasibility proof on scripted dev tasks (≤11
tool-calls / ≤12 turns); freeze adapter + 96-task manifest; set identity constants
(`APPWORLD_VERSION="0.1.3.post1"` + data-tree/bundle hashes). Then GPU-gated 12-smoke → 36-lite →
96-task (explicit GPU go-ahead required).
