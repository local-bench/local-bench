# Spec: model-identity digest plumbing + engine hardening (2026-07-02)

Implements P1 of `docs/deploy/plan-ranked-row-2026-07-02.md`. Four work items, all `cli/` only.
Findings verified against code during the 2026-07-02 comprehensive review.

## Work item 1 — GGUF identity digests → manifest.model (clears `model.identity_missing`)

The digests are already computed from GGUF embedded metadata at `serving/model_artifact.py:83-84`
(`tokenizer_digest` = hash of `tokenizer.*` keys minus chat template; `chat_template_digest` =
hash of `tokenizer.chat_template`) and stored on `ModelArtifact`. The plumbing stops in
`serving/bench.py:build_orchestrate_config` — they never reach `manifest.model`, so every serve
run emits `model.tokenizer_digest=null` + `model.chat_template_digest=null` (both required by
`manifest._MODEL_FIELDS` and `foundation._MODEL_REQUIRED`) → publish blocker.

Fix (minimal path):
1. Add `tokenizer_digest: str | None = None` and `chat_template_digest: str | None = None` (plus
   matching SOURCE-LABEL fields, e.g. `tokenizer_digest_source` / `chat_template_digest_source`
   with values `gguf.embedded` | `external.file` | `server.override`) to `OrchestrateConfig`
   (orchestrate.py ~L194) and `ManifestContext` (manifest.py ~L60).
2. `build_orchestrate_config` passes `evidence.artifact.tokenizer_digest` /
   `.chat_template_digest` with source label `gguf.embedded`.
3. Forward both through the `ManifestContext(...)` construction in orchestrate.py (~L519-573).
4. `manifest._model_identity` (manifest.py ~L193-203): prefer the explicit digest when provided;
   otherwise keep the existing `_optional_file_hash(tokenizer_file/chat_template_file)` fallback
   (label `external.file`). If a `--chat-template-file` override is in play for the serve lane,
   hash the OVERRIDE (label `server.override`) — the served template identity must match what was
   actually served. Do NOT reuse `gguf_metadata_sha256` as either digest (it stays an audit hash).
5. Emit the source labels in `manifest.model` alongside the digests (additive fields; do not
   rename or remove existing fields).

Result check: a serve-lane bundle must show non-null `model.tokenizer_digest` +
`model.chat_template_digest`, and `validate-submission-bundle` must no longer list
`model.identity_missing` for an orchestrated bundle (the smoke bundle
`runs/bench/smoke-leakfix-capped-16k-2026-07-02/localbench-run.json` is a handy fixture shape).

## Work item 2 — close the launch orphan window

`serving/process.py:41-55`: the llama-server is `Popen`-spawned (line ~41) but the Job Object is
only attached at `job.assign_process` (line ~55). If `AssignProcessToJobObject` raises `OSError`
(job_object.py:82-83) — or a `KeyboardInterrupt` lands between spawn and assign — the running
server is never terminated and `launched` is still None in the caller, so `runner.py`'s `finally`
skips teardown entirely: a GPU-holding orphan with the KILL_ON_JOB_CLOSE safety net never armed.

Fix: wrap everything after the `Popen` so ANY exception before the launch handle is returned
terminates the spawned process (`process.terminate()` + best-effort wait) and closes the job
handle and log handle before re-raising. Add a test with a fake/raising assign that asserts the
spawned process got terminated and handles closed.

## Work item 3 — `_bench` exit-code fidelity

`cli.py` `_bench` (~L709-714) catches `(RuntimeError, OSError)` → `EXIT_INTERNAL_RUNNER_BUG`,
which swallows `UnsafeResumeError` and `CheckpointCorruptionError` (both RuntimeError subclasses)
that `_run` maps to dedicated exit codes (`cli.py` ~L558-566). Catch the specific exceptions
first and return the same dedicated codes `_run` uses. Test both mappings.

## Work item 4 — capped-thinking ctx fail-fast guard

Observed live 2026-07-02: a capped-thinking bench with `--ctx 4096` (< the 8192 thinking budget)
burned every item on `exceed_context_size` after the model thought to the context wall. Add a
fail-fast validation at bench-config/launch-assembly time: for the capped-thinking lane, require
`ctx >= CAPPED_THINKING_REASONING_BUDGET + <the max per-bench decoding max_tokens of the resolved
suite, or a documented fixed headroom if the suite isn't resolved yet at that point> + prompt
headroom (use 2048 if no better bound is available)`. On violation raise a clear RuntimeError
telling the user the minimum ctx. Keep it lane-scoped (answer-only unaffected). Test the guard
(violation raises; compliant config passes).

## Hard constraints
- `cli/` only. `cli/runs/board/board_v1.json` untouched (git blob `3d058e60…`).
- No scorecard-identity / registry-digest / SCORECARD.json changes.
- Additive manifest fields only (no renames/removals — the result_bundle contract is live).
- Full pytest suite green (baseline 1005 passed / 13 skipped / 1 xfailed).
- No GPU runs, no push, no deploy, no commit.
