# AppWorld-C process-isolation sandbox + eval seam — BUILD RESULTS

Date: 2026-06-23. Status: **BOTH ACCEPTANCE GATES PASS.** Implements the SANDBOX + eval-seam
sections of `appworld-sandbox-build-spec.md` / `agentic-axis-design-LOCKED-2026-06-23.md`.

GPU-free, endpoint-free (no model, no `llama-server`, port 8000 untouched). Additive only:
new modules under `cli/src/localbench/scoring/agentic_exec/` + tools + tests; no edits to `web/`,
`axes.py`, the scorer, scorecard, `top_k`, the headline lanes, `cli/runs/`, or the existing stub
adapter; the agentic axis stays unregistered (weight-0 candidate). No `git commit`/`push`.

---

## HEADLINE — the hard gate (both hold; re-run yourself with the commands below)

| Gate | Requirement | Result |
|---|---|---|
| **1. Canary suite THROUGH the sandbox** | `SUCCEEDED: 0` (all 55 BLOCKED), parsed count | **SUCCEEDED 0 / BLOCKED 55 / ERROR 0** ✅ |
| **2. Scripted NON-LLM 2-task solve** | ≥2 real dev tasks reach `success: True` | **2/2 success: True** (`fac291d_1`, `50e1ac9_1`) ✅ |

### Canary before → after (the 31 → 0 flip)

| run | SUCCEEDED | of which | BLOCKED | ERROR |
|---|---|---|---|---|
| **baseline** (raw `world.execute()`) | **31** | CRITICAL 14, HIGH 12, MED 5 | 24 | 0 |
| **through `AppWorldSandbox`** | **0** | — | **55** | **0** |

Every canary in the attack-surface doc — including all 14 CRITICAL (answer/solution/DB reads
A1/A4–A9, raw-`requester`/TestClient/admin-bypass H1–H4/O2/O3, world-class visibility W3) and the
17 HIGH/MED (env/cwd/proc leaks P1–P5, cross-task logs L1–L3, `__import__`/`importlib` gadgets,
`os.scandir`/`pathlib.glob`/`os.stat`, object-graph O1/O5, `breakpoint`) — is now **BLOCKED**.
The L1–L3 cross-task targets were **seeded on disk first** (a real sibling-task `api_calls.jsonl` /
`environment_io.md` / mutated `dbs/`), so those are blocked against a *real* tree, not a missing one.

### Scripted-solve verdicts (computed from the live APIs through the proxy — gold files unreadable)

```json
[
  {"task_id": "fac291d_1", "success": true,  "collateral_damage": false, "num_passes": 2, "num_failures": 0,
   "answer_preview": "81"},
  {"task_id": "50e1ac9_1", "success": true,  "collateral_damage": false, "num_passes": 2, "num_failures": 0,
   "answer_preview": "Mysteries of the Silent Sea, Crimson Veil, Haunted Memories, Fire and Ice"}
]
```

Both answers match the gold (`81`; the four R&B titles) yet were derived by the scripted agent
*through the API proxy* — auth (`show_account_passwords`→`spotify.login`), full pagination across
song/album/playlist libraries, per-song `show_song` genre/play-count lookups, sort + top-k — with
genre/`top_k` parsed from the **instruction** (`show_active_task`), never from the on-disk gold
(which the jail cannot read). State persists across blocks; finalize is harness-owned.

---

## ARCHITECTURE AS BUILT (process + filesystem isolation — the only boundary that holds)

Two processes per task over a private `AF_UNIX` socket:

```
  with AppWorldSandbox(task_id) as sb:        # orchestrator (trusted side, in the appworld venv)
      obs = sb.run_block(code)                # -> BlockObservation(stdout, error)
      verdict = sb.finalize(answer)           # -> Verdict(success, collateral_damage, passes, failures)
```

- **TRUSTED env host** (`agentic_exec/env_host.py`) — the ONLY process that imports/initialises
  AppWorld (so its global `builtins.SystemExit` rebind never pollutes the harness/scorer). Owns the
  real `world` + data + live `requester`/`TestClient` + DBs + evaluator. Serves a **4-opcode** RPC
  over the unix socket and nothing else: `call_api(app, api, kwargs)`, `api_docs(...)`,
  `finalize(answer)`, `ping`. No `world`/`requester` ever crosses the wire; no raw code-exec, no
  filesystem op, no eval/state passthrough. Every inbound field is validated (app/api/kwarg names
  must be identifiers; kwargs are re-serialised via `json.dumps`, so the untrusted side cannot inject
  code). Prints `READY` once the world is built and the socket is listening.
- **UNTRUSTED code runner** (`agentic_exec/runner_bootstrap.py`) — runs the model's Python blocks
  inside **bubblewrap**. NO AppWorld import, no data tree, no `APPWORLD_ROOT`. Its only window onto
  AppWorld is the bind-mounted socket at `/rpc/rpc.sock`. Model code runs via `exec` in a namespace
  whose only AppWorld surface is `ApisProxy` — a **plain `__slots__` object** that marshals
  `apis.<app>.<api>(**kwargs)` to the host and returns plain data. It carries **no `_requester`, no
  `.client`, no `.close`/`.close_all`, no `complete_task`**, and its API leaves have no closure/globals
  leading back to a Requester (they are freshly built in this process). Secondary in-process belt: a
  safe-builtins allow-list (no `open`/`eval`/`exec`/`compile`/`input`/`breakpoint`/`globals`/…) and a
  **guarded `__import__`** that permits ONLY pure-data modules (`re`/`json`/`math`/`collections`/…)
  and denies every escape module (`os`/`pathlib`/`io`/`sys`/`socket`/`subprocess`/`importlib`/`ctypes`/
  `pickle`/`inspect`/…), dotted forms, and relative imports.
- **Orchestrator** (`agentic_exec/sandbox.py`) — `AppWorldSandbox`: spawns the env host in the venv,
  waits for `READY`, spawns the bwrap runner, waits for its `ready`, then brokers `run_block` /
  `finalize` (JSON over the runner's stdio pipe; the runner RPCs API/finalize to the host over the
  socket). Per-event wall-clock timeouts; fresh per task; tears both children + the socket dir down on
  exit. Import-safe on non-Linux hosts (bwrap/appworld only touched in `__enter__`).

### Why an in-process allow-list alone cannot work (and is only the belt here)
The canary suite already proved aliased `open`, `os.environ` path rebuild, `apis._requester`,
`__closure__`/`__globals__`, and `().__class__.__base__.__subclasses__()` defeat any namespace strip.
In this build those still *run* inside the jail but reach **nothing**: there is no data tree to read,
no `requester` in the process, no `FileIO`/`BufferedReader` in the minimal `-I` interpreter's object
graph (verified: O1's 280 subclasses expose only import-system internals, no concrete file-IO type),
and the only injected handle reachable via a traceback frame (O5) is the inert `ApisProxy` whose
`_rpc` can send just the 4 validated opcodes. The wall is the **process + FS jail**.

---

## EVAL SEAM (the 3 adapter bugs, fixed in the trusted host — `env_host._handle_finalize`)
- No `world.verify(...)` (it does not exist) → `complete_task` then `world.evaluate().to_dict()`.
- `passed = to_dict()["success"]` (not a non-existent `.passed`).
- `collateral_damage = ("assert no model changes." in failed-requirement strings)` (not `.collateral_damage`).
- Observation parse contract: `json.loads` → `ast.literal_eval` → raw `str` (in `runner_bootstrap._parse_observation`).
- `complete_task` is harness-owned; the untrusted side has no path to call it (no `complete_task` on the proxy).

---

## bubblewrap CONFIG USED

bwrap was **not installed** and `sudo` requires a password (non-interactive apt unavailable), so the
binary was extracted from the official Ubuntu `.deb` into user space (no root needed). Unprivileged
user+net+pid+mount namespaces are available in this WSL kernel (`6.6.87.2-microsoft-standard-WSL2`),
which is all bwrap needs.

```bash
# one-time, no root: fetch + unpack bwrap into ~/.local/bin
cd /tmp && apt-get download bubblewrap && dpkg-deb -x bubblewrap_*_amd64.deb bw && \
  mkdir -p ~/.local/bin && cp bw/usr/bin/bwrap ~/.local/bin/bwrap && chmod +x ~/.local/bin/bwrap
~/.local/bin/bwrap --version          # bubblewrap 0.9.0
```

The runner is launched with (Ubuntu 24.04 usrmerge layout):

```
bwrap --unshare-all --die-with-parent --new-session --cap-drop ALL --hostname sandbox \
  --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --symlink usr/sbin /sbin --proc /proc --dev /dev --tmpfs /tmp --tmpfs /home \
  --size <256MiB> --tmpfs /lbscratch \
  --ro-bind <runsrc> /lbrun  --bind <rpc-sock-dir> /rpc \
  --chdir /lbscratch --clearenv \
  --setenv HOME /lbscratch --setenv PATH /usr/bin:/bin --setenv PYTHONHASHSEED 0 \
  --setenv PYTHONDONTWRITEBYTECODE 1 --setenv TZ UTC --setenv LC_ALL C.UTF-8 --setenv PYTHONPATH /lbrun \
  /usr/bin/python3 -I /lbrun/runner_bootstrap.py
```

`--unshare-all` includes the **network** namespace (verified: `AF_UNIX` to `/rpc/rpc.sock` works,
`AF_INET` to `8.8.8.8:53` is refused). Resource limits (`RLIMIT_CPU` 60s, `RLIMIT_AS` 2 GiB,
`RLIMIT_CORE` 0) + `prctl(PR_SET_NO_NEW_PRIVS)` are applied in a `preexec_fn` on the bwrap child.
Scrubbed env confirmed inside the jail: only `HOME/PATH/PYTHONHASHSEED/TZ/LC_ALL/PYTHONPATH/PWD`;
no `APPWORLD_ROOT`; `/home` empty; `/mnt/c` and the data tree absent.

**Determinism:** `PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8`; AppWorld fixed task time; fresh jail per
task; the sandboxed canary count is **0/55/0 across repeated runs**.

---

## EXACT WSL RE-RUN COMMANDS (independent verification)

Prereq once: extract bwrap to `~/.local/bin/bwrap` (block above). Then:

```bash
# GATE 1 — canary suite THROUGH the sandbox (expect SUCCEEDED=0 / BLOCKED=55 / ERROR=0).
# NOTE: invoke the venv python by ABSOLUTE PATH — `activate` does not shadow python3 on this box,
# and the host side must import appworld + seed the L1-L3 cross-task tree.
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && export PATH="$HOME/.local/bin:$PATH" \
  && ~/appworld-harness/venv/bin/python3 cli/tools/appworld_canary_suite_sandboxed.py --json'

# GATE 2 — scripted NON-LLM 2-task solve THROUGH the sandbox (expect 2/2 success: True).
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && export PATH="$HOME/.local/bin:$PATH" \
  && ~/appworld-harness/venv/bin/python3 cli/tools/appworld_scripted_solve_sandboxed.py --json'

# BOTH GATES as pytest (skips cleanly if appworld/bwrap/APPWORLD_ROOT are absent):
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && export PATH="$HOME/.local/bin:$PATH" \
  && ~/appworld-harness/venv/bin/python3 -m pytest cli/tests/test_appworld_sandbox_acceptance.py -v -s'

# Host-agnostic unit tests for the proxy/import-allow-list/wire-protocol (no bwrap needed):
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && ~/appworld-harness/venv/bin/python3 -m pytest cli/tests/test_appworld_sandbox_units.py -q'

# Baseline (raw world.execute, for the 31 number):
wsl bash -lc 'cd /mnt/c/Users/Michael/local-bench \
  && export APPWORLD_ROOT=/home/michael/appworld-data PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  && ~/appworld-harness/venv/bin/python3 cli/tools/appworld_canary_suite.py'
```

---

## FILES (all additive)

| File | Role |
|---|---|
| `cli/src/localbench/scoring/agentic_exec/sandbox_protocol.py` | wire framing + opcode set (imported by both sides; no AppWorld, no secrets) |
| `cli/src/localbench/scoring/agentic_exec/env_host.py` | TRUSTED env host: owns `world`, serves the 4-opcode RPC, eval-seam fix |
| `cli/src/localbench/scoring/agentic_exec/runner_bootstrap.py` | UNTRUSTED in-jail runner: `ApisProxy`, safe-builtins, guarded `__import__`, block exec |
| `cli/src/localbench/scoring/agentic_exec/sandbox.py` | `AppWorldSandbox` orchestrator (`run_block`/`finalize`); bwrap launch + brokering |
| `cli/tools/appworld_canary_suite_sandboxed.py` | runs the 55 canaries THROUGH the sandbox (gate 1) |
| `cli/tools/appworld_scripted_solve_sandboxed.py` | scripted NON-LLM 2-task solve THROUGH the sandbox (gate 2) |
| `cli/tests/test_appworld_sandbox_acceptance.py` | both gates as pytest (skips without WSL/bwrap/appworld) |
| `cli/tests/test_appworld_sandbox_units.py` | host-agnostic units: proxy no-leak shape, import allow-list, framing |

The existing stub-based agentic tests (35) and the rest of the agentic_exec package are untouched and
still pass — the eval-seam fix lives in the new real-world `env_host`, not in the stub adapter.

---

## SCOPE NOTE — what this build is NOT (separate follow-ups, per the spec)
Sandbox + eval seam + the two acceptance tests ONLY. The Protocol C agent loop (model-output →
code-block → sandbox → observation → iterate, turn cap 24, per-block rollback), the diagnostics
logging, and scorer wiring are deliberately out of scope; the `AppWorldSandbox` interface
(`run_block`/`finalize`) is kept clean so that loop can sit straight on top.

## Remaining-open canaries
**None.** All 55 are BLOCKED (0 SUCCEEDED, 0 ERROR) through the sandbox.
