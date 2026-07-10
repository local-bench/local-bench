# Spec: agentic lane B1' — WSL2 sandbox proxy under the one Windows campaign (2026-07-03)

Implements the Linux/agentic lane per the oracle verdict
(`oracle-verdict-wsl2-topology-2026-07-02.md`: **A1+B1**) with the B1' refinement: the
protocol-C loop runs ON WINDOWS against the same 127.0.0.1 llama-server as the other four
axes; ONLY the sandbox crosses into WSL2, over stdio. No NAT bridge, no bind widening, no
second runtime. Branch: `agentic-lane-b1` (worktree; the main checkout is running the
4-axis canary and must not be touched).

## Verified context (do not re-derive)

- `run_localbench` triggers the agentic axis when `appworld_c` is in the resolved bench
  list (`orchestrate.py:247`); `core-text-v1/suite.json` already declares it. With
  factories injected it merges `benches["appworld_c"]` + items + provenance into the SAME
  scorecard (`orchestrate.py:496-511`) and degrades to axis-not-measured when absent.
- `_run_agentic_axis(config, warnings, sandbox_factory=, model_factory=, task_ids=,
  results_dir=)` (`orchestrate.py:1048`): injected factories are first-class; the native
  (non-injected) path requires appworld+bwrap in-process and is Linux-only.
- Loop surface (`protocol_c_loop.py:74-83`): `SandboxLike.run_block(code) -> obs
  (.stdout: str, .error: str|None)`; `.finalize(answer) -> verdict(.success,
  .collateral_damage, .failures — see AppWorldSandbox for the exact shape)`. The
  benchmark watchdog additionally calls `force_kill()` on timeout
  (`benchmark.py:_run_task_with_watchdog`).
- Model client: `funnel.chat_client_factory(base_url, model, api_key, timeout_s,
  chat_template_kwargs)` returns stateless `ChatCompletionsClient`s; per-request
  `chat_template_kwargs={"enable_thinking": True}` engages native thinking. On Windows
  this hits the SAME server instance as the text axes. The committed capped-thinking argv
  (`--reasoning on --reasoning-budget 8192 --reasoning-format deepseek`) parses thinking
  into `reasoning_content` server-side, so `message.content` is clean.
- The proven WSL sandbox (acceptance gates green 2026-07-02: 55/55 canaries blocked, 2/2
  scripted solves): `AppWorldSandbox(task_id)` context manager spawns trusted env-host +
  bwrap runner over a private AF_UNIX socket. Its internals are FROZEN — do not modify
  anything under `scoring/agentic_exec/{sandbox,env_host,runner_bootstrap,
  sandbox_protocol}.py` beyond what a new caller needs.
- WSL env: venv `<wsl-venv>`, data `APPWORLD_ROOT=<appworld-root>` (native ext4),
  pins `PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8`,
  `PATH="$HOME/.local/bin:$PATH"` (bwrap 0.9.0). Repo reachable at
  `/mnt/c/path/to/local-bench-wt-agentic` (this worktree) — the worker must run
  from the SAME tree as the Windows side so code identity matches.
- SCORED subset = 96 tasks (`task_pool.build_subset(Stage.SCORED, ...)`); task_ids come
  from the appworld package, so subset construction happens WSL-side (or is passed in).

## Work item 1 — WSL worker entrypoint

New module `cli/src/localbench/scoring/agentic_exec/wsl_worker.py` (+ a `python -m`
entry): a per-task worker speaking newline-delimited JSON over stdin/stdout.

- Protocol (one JSON object per line, mirroring the size-cap discipline of
  `sandbox_protocol.py` — reuse its framing constants/helpers where they aren't
  socket-specific; hard cap per line, reject oversized):
  - `{"op": "hello"}` -> `{"kind": "ok", "identity": {...}}` where identity carries:
    wsl kernel (`uname -r`), distro/os-release, python version, venv path, worker git
    commit + dirty flag (of the tree it runs from), bwrap path/version, appworld_root +
    a check that it is NOT under /mnt (fail closed if it is), appworld package version.
  - `{"op": "open_task", "task_id": ...}` -> enters `AppWorldSandbox(task_id)`;
    `{"kind": "ok"}` or `{"kind": "error", "detail": ...}`.
  - `{"op": "run_block", "code": ...}` -> `{"kind": "ok", "stdout": ..., "error": ...}`.
  - `{"op": "finalize", "answer": <json>}` -> `{"kind": "ok", "verdict": {success,
    collateral_damage, num_passes, num_failures}}`.
  - `{"op": "close"}` -> exits the sandbox context, replies ok, worker exits 0.
  - Any malformed/unknown op -> `{"kind": "protocol_error", ...}` (do not crash).
  - `{"op": "list_tasks", "stage": "scored"}` -> `{"kind": "ok", "task_ids": [...]}` —
    lets the Windows side obtain the SCORED subset without importing appworld.
- One task per worker process (fresh env_host + bwrap per task is the LOCKED rule;
  worker exits after `close` or on stdin EOF). Worker must install a SIGTERM/stdin-EOF
  handler that tears down the sandbox context (env-host + bwrap children) before exit.
- Env pins are asserted inside the worker (set them if absent; record them in identity).

## Work item 2 — Windows sandbox proxy + factories

New module `cli/src/localbench/scoring/agentic_exec/wsl_bridge.py`:

- `WslSandboxProxy` implementing the loop surface (`run_block`, `finalize`,
  `force_kill`) + context-manager enter/exit. Enter spawns
  `wsl.exe bash -lc '<venv-python> -m localbench.scoring.agentic_exec.wsl_worker'`
  with cwd-independent absolute paths, sends `hello` + `open_task`, and fails closed on
  any error/timeout. Exit sends `close`, waits bounded, then kills the process tree.
  `force_kill()` = kill the wsl.exe child immediately (taskkill /T /F or equivalent) —
  and the WSL-side EOF/SIGTERM handler reaps env-host/bwrap. All op-level timeouts
  bounded and configurable (open_task generous — world build takes time; run_block /
  finalize per LoopConfig norms).
- Proxy failures raise the exception types the benchmark maps to INFRA_SANDBOX (match
  what `appworld_sandbox_factory` produces today — inspect `benchmark.py`
  `_harness_error_result` and the failure-class mapping and conform).
- `wsl_sandbox_factory(repo_root_wsl_path, venv_python, appworld_root) ->
  sandbox_factory` compatible with `_run_agentic_axis`.
- `wsl_list_scored_task_ids(...)` helper using a short-lived worker (`list_tasks`).
- Stdout/stderr hygiene: worker stderr is captured to a per-task log file under the run
  dir (diagnostics), NEVER parsed as protocol.

## Work item 3 — serve-path wiring + preflight

- In the serve orchestrator path (`serving/` + `_bench`), when the resolved bench set
  includes `appworld_c` and runtime is llama.cpp: build the factories from work item 2
  and pass them (+ task_ids from `list_tasks`, honoring `--max-items` for shakeouts)
  into the orchestrate call. Bench CLI knobs require explicit managed-harness paths:
  `--wsl-venv-python <wsl-python>` and `--appworld-root <appworld-root>`.
- PREFLIGHT (before the llama-server launches): spawn a worker, `hello`, assert identity
  sanity (ext4 appworld root, bwrap present, git commit matches the Windows-side HEAD,
  clean/dirty recorded), `list_tasks` non-empty. Any failure -> clear RuntimeError, no
  server launch, no partial run.
- Record the worker identity + topology block into the agentic provenance the run
  already carries (`agentic_provenance`, orchestrate.py:494-511): additive JSON only —
  `topology` (scorecard_assembly "single-campaign-no-merge", model_call_location
  "windows_campaign_process"), `wsl_identity` (from hello), `agentic_sandbox_identity`
  (bwrap version/path, appworld_root + fs), `single_campaign_integrity`
  (merge_step_used false). Keep names/values additive and stable.

## Work item 4 — chat-client reasoning compatibility (verify, small fix if needed)

`ChatCompletionsClient` (`chat_client.py`) was validated against LM Studio. Against
llama-server b9852 with `--reasoning-format deepseek`, responses carry
`reasoning_content` next to `content`. Verify the client: (a) reads `content` as the
turn text and IGNORES `reasoning_content`; (b) maps `finish_reason` length/stop
faithfully; (c) forwards `chat_template_kwargs` per request. Add a unit test with a
deepseek-shaped chat response fixture (content + reasoning_content) and, if the client
mishandles it, fix minimally. Do NOT add forcing/two-pass machinery to the agent loop —
the locked agentic contract is the chat endpoint with native thinking.

## Work item 5 — tests (CPU-only; WSL-marked where needed)

- Protocol unit tests (Windows-runnable, no WSL): frame encode/decode, oversized frame
  rejection, malformed-op handling, proxy timeout -> INFRA_SANDBOX-mapped error, proxy
  force_kill kills the child (use a fake worker subprocess script, not real WSL).
- WSL integration tests (skip-if-no-WSL, same pattern as
  `test_appworld_sandbox_acceptance.py`): hello identity sanity; open/run/finalize round
  trip on one real dev task through the proxy from WINDOWS; **the two acceptance gates
  re-run THROUGH the B1' proxy path** (canaries via run_block from the Windows side —
  this is the oracle's `AppWorld_Sandbox_Gates_Under_B1`); parent-death cleanup: kill
  the proxy's wsl child mid-task, assert no orphan env_host/bwrap processes remain in
  WSL (`pgrep`).
- Orchestrate-level test: injected wsl-bridge factories (faked at the SandboxLike level)
  produce `benches["appworld_c"]` + agentic provenance in the record — extend the
  existing injected-agentic test pattern rather than inventing a new harness.

## Hard constraints

- Work ONLY in this worktree (`<home>/local-bench-wt-agentic`, branch
  `agentic-lane-b1`). NEVER touch `<home>/local-bench` (a 13h canary is
  stamping tree state there).
- `cli/` only. No changes to frozen sandbox internals, scorecard identity,
  reasoning registry, axes weights, or any released SCORECARD.json.
  `cli/runs/board/board_v1.json` untouched.
- No GPU runs, no deploys, no pushes, no commits (Claude reviews then commits).
- Full pytest green (Windows baseline 1019 passed / 13 skipped / 1 xfailed; new WSL
  tests must SKIP cleanly on hosts without the env). Run the WSL-marked tests via the
  documented wsl command against THIS worktree path and report results separately.

## Out of scope (round 2, after shakeout)

- core-text-v1 site release manifest + catalog entry (needed only for the RANKED
  publishable run).
- boundary_health telemetry, remaining oracle test battery items, trust-tier label
  plumbing (`orchestrated-pinned-artifacts-v1+agentic-wsl2-bwrap-v1`).
- Any funnel/rerun policy changes.
