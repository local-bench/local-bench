# Build spec: orchestrator-driven direct finalization (agentic verdict integrity)

Date 2026-07-03. Author: Claude (for Codex; Claude reviews+commits). Branch
`codex/local-bench-online-backend` (HEAD 6b0be11). board_v1 frozen `3d058e60…` — must not change.
Oracle-designed (GPT-5.5 Pro, 2026-07-03); full answer in the session scratchpad
`oracle-verdict-integrity-answer.txt`.

## Problem (verified in code)
The agentic verdict (50% of the ranked composite) is currently RELAYED through the UNTRUSTED
runner: `sandbox.finalize(answer)` sends `{"cmd":"finalize","answer":...}` to the runner over
stdin; the runner RPCs `OP_FINALIZE` to the trusted env-host, gets the real verdict, and relays
it back as a stdout `{"event":"final_result","verdict":{...}}` line the orchestrator trusts. The
in-process sandbox "belt" is bypassable by design, so escaped model code can (a) substitute the
answer sent to the env-host, or (b) `os.write(1, forged_final_result)` to forge `success`.

## What's already safe (do NOT regress)
- The task is PINNED at env-host spawn: `env_host.serve(task_id, socket_path, experiment_name)`
  builds `AppWorld(task_id=task_id, ...)`. The runner cannot choose/switch the task.
- `complete_task`, `evaluate`, `save_state`, `load_state`, `close`, `request` are already in
  `env_host._FORBIDDEN_API_NAMES` — the runner's socket RPC cannot call them.
- `_handle_finalize` is one-shot (`self._finalized` guard) and computes the verdict host-side on
  the pinned world.
The ONLY residual hole is that finalize is runner-TRIGGERED and runner-RELAYED.

## Design (oracle's preferred: runner never sees finalize)
Route finalization over the env-host's stdin/stdout — a trusted channel the runner cannot touch
(the runner only has the in-jail unix socket). The runner is removed from the verdict path.

### 1. `env_host.py` — accept finalize on a trusted control channel, not the runner socket
- In `serve(...)`, after `server.accept()` (the runner connection), ALSO read newline-delimited
  JSON CONTROL messages from `sys.stdin`. Multiplex stdin + the runner socket (a stdin reader
  thread feeding a queue is simplest; keep the socket serve loop as-is for app APIs).
- On a control message `{"op":"finalize","answer":<any>,"finalize_id":<str>}` from stdin: run the
  EXISTING `_RealEnvHost._handle_finalize` logic on the pinned world, then emit EXACTLY ONE line
  on stdout:
  `{"type":"authoritative_verdict","finalize_id":<echoed>,"task_id":<pinned>,"result":{...}}`
  (result = the current `_handle_finalize` KIND_OK `result` dict). Flush.
- REMOVE `OP_FINALIZE` from the socket-served `handle()` surface: if the runner sends `OP_FINALIZE`
  over the socket, return `KIND_PROTOCOL_ERROR "finalize is not available on the runner surface"`.
  (Keep OP_PING/OP_CALL_API/OP_API_DOCS on the socket.)
- Keep the one-shot `_finalized` guard: a second finalize control message returns a protocol error
  on stdout (never a second scoreable verdict).
- The `READY` handshake stays. Control messages are only read AFTER READY. Never parse arbitrary
  host logs as control/verdict lines — logs go to stderr (already drained separately); stdout
  carries only `READY` and the single `authoritative_verdict` line.

### 2. `sandbox.py` — orchestrator drives finalize directly; scores only the direct verdict
- Spawn the env-host with `stdin=subprocess.PIPE` (currently `subprocess.DEVNULL`) so the parent
  can write control messages.
- Rewrite `finalize(answer)`:
  1. Generate a `finalize_id` nonce (trusted, orchestrator-side; use a counter+run-scoped random
     seeded via the existing identity, NOT `os`-time — respect the no-`Date.now`/`random` rule if
     any; a monotonic counter combined with the task_attempt is sufficient for correctness).
  2. Write `{"op":"finalize","answer":answer,"finalize_id":...}` to the env-host STDIN. `answer`
     is the orchestrator's read-back answer (already what protocol_c_loop passes — B1' loop runs
     on Windows), NOT anything the runner supplies at finalize time.
  3. Read lines from the env-host STDOUT until the `authoritative_verdict` whose `finalize_id`
     matches. Accept ONLY that exact-match line. Ignore/ône-shot everything else.
  4. Return the verdict built from `result`. NEVER read the runner's `final_result` for scoring.
- Keep the one-shot `_finalized` guard on the parent side too.
- NO FALLBACK: if the env-host emits no matching verdict (timeout / malformed / mismatch), raise
  `SandboxError` and FAIL the task. Never silently fall back to the runner's relayed result or a
  "last seen" verdict (oracle Q4.12).

### 3. `runner_bootstrap.py` — runner no longer participates in finalize
- Remove (or hard no-op) the `finalize` command handler. If a `finalize` cmd still arrives, reply
  with an explicit non-scoreable ack; the runner has no path to complete_task/evaluate anyway.
- The runner's `final_result` event is retained ONLY as debug telemetry (write to the transcript),
  never consumed for scoring by the parent.

### 4. protocol_c_loop.py — unchanged call site, new semantics
- `verdict = _coerce_verdict(sandbox.finalize(answer))` stays. Confirm `answer` is the
  orchestrator's read-back answer bytes (via `__LB_ANSWER__`), and that those exact bytes are what
  reach the env-host (answer provenance). Record the answer bytes (or their hash) in the per-task
  agentic record.

### 5. Provenance / trust tier (additive)
- Record in the agentic provenance a `finalization` block:
  `{"path":"orchestrator-direct-envhost-stdin-v1","runner_in_verdict_path":false,
    "finalize_correlation":"finalize_id+pinned_task+one_shot","answer_hash":<sha256 of answer bytes>}`.
- Update the trust-tier string/note to reflect that the runner is excluded from the verdict path
  (e.g. append `+direct-finalize-v1`). Do NOT change board_v1 or the scorecard.

## Correlation scheme (oracle minimal-correct)
`finalize_id` (orchestrator nonce) + task pinned at env-host spawn + one-shot finalization +
orchestrator-supplied answer. Orchestrator accepts a verdict ONLY if `finalize_id` matches the
pending finalization and it has not already scored. Never "latest verdict wins."

## Out of scope (explicitly deferred — separate tasks)
- Reliability/provenance fixes (WslSandboxProxy.__enter__ leak, `_read_response` timeout kill,
  git-identity fail-closed, APPWORLD_ROOT realpath+ext4 assert) — separate small build.
- Pre-open-submissions items (trust TIERS for third-party operators, save/load/reset lockdown
  audit, api_docs leak audit, fresh-env-host-per-task, RPC deserialization hardening, FD-leak
  audit of the control channel) — these gate OPENING third-party submissions, not the first ranked
  (Gemma, held) row. Track separately.

## Tests / gates (MUST add)
- env_host: OP_FINALIZE over the socket is rejected (protocol error); a stdin finalize control
  message produces exactly one `authoritative_verdict` with the echoed finalize_id; a second
  finalize control message is refused (one-shot).
- sandbox: `finalize` writes the control message to env-host stdin and returns the env-host's
  direct verdict; a forged runner `final_result` on the runner channel is NOT used for scoring
  (inject a fake and assert it's ignored); a finalize_id mismatch raises and fails the task; no
  fallback to runner output on timeout.
- Keep the existing appworld acceptance gates green (they are WSL/skipif-gated on this host; ensure
  the pure-Python unit tests with a mock env-host/socket cover the new paths on Windows/CI).
- Full `uv run pytest` green. `git hash-object cli/runs/board/board_v1.json` ==
  `3d058e6074bd781cc488c03255904b5f9599e37e`. Do NOT touch axis weights. Do NOT commit — leave the
  tree dirty for Claude review.

## Review posture
This is security-critical. Claude will read the full diff, adversarially test the forgery paths,
and may run a second oracle pass on the implementation before commit.
