# Resume-gate fix: exclude ephemeral port from resume identity (2026-07-03)

## Problem (root cause proven)

The canary crash-resume was refused: `unsafe resume refused: server_fingerprint changed`
(exit 70). Root cause, verified by reproducing the recorded hash bit-for-bit:

- `runner.py` allocates an **ephemeral port** per launch (`allocate_port()` binds port 0)
  and fingerprints `redacted_argv(argv)`, which contains `--port <ephemeral>`.
- Reproduction: recomputing `server_fingerprint` with the recorded
  `server_command_redacted` (port 55419) and today's on-disk components yields the exact
  recorded value `28f8fa1466435ae657b1d58546e7f6d3549a43b35e6db28c6596a91a39b81ec2`;
  changing only the port token changes the hash. Model file sha256, exe sha256, chat
  template digest, env allowlist, ctx, kv quant, slots, flash are all byte-identical.
- Therefore cross-process resume is structurally impossible: a fresh launch always gets a
  new port, so both resume gates always refuse:
  1. `serving/assembly.py::precheck_resume_fingerprint` (line ~225) — fired first.
  2. `orchestrate.py::_validate_resume_campaign` (line ~847) — would fire next.

The fingerprint itself is otherwise correct provenance (each launch/segment SHOULD record
its exact argv incl. port). The defect is using the **exact per-launch fingerprint** as
the **resume identity**.

## Fix design

Introduce a `resume_identity`: the same canonical hash but computed over argv with
per-launch ephemera normalized. Keep the exact `server_fingerprint` untouched everywhere
it is recorded today (forensic/segment provenance).

### R1 — `serving/fingerprint.py`
- Add `normalize_ephemeral_argv(argv: list[str]) -> list[str]`: returns a copy where the
  token immediately following `--port` is replaced with the literal `"<EPHEMERAL>"`.
  No other tokens change (`--api-key` values are already constant `***REDACTED***` in the
  argv this feeds on — the runner always fingerprints redacted argv).
- Add `resume_identity(**same keyword args as server_fingerprint) -> str` implemented as
  `server_fingerprint(argv=normalize_ephemeral_argv(argv), ...)` — same canonical JSON
  hashing, no new schema.

### R2 — `serving/runner.py`
- Compute both `fingerprint` (unchanged) and `identity = resume_identity(...)` with the
  same components.
- Pass `identity` (plus whatever recorded-side inputs the precheck needs, see R3) to the
  precheck instead of the exact fingerprint.
- Thread `identity` into evidence so it is recorded and reaches orchestrate (R4/R5).

### R3 — `serving/assembly.py::precheck_resume_fingerprint` (rename to
`precheck_resume_identity`; update the single import in runner.py)
- New comparison, fail-closed:
  - Load `campaign.json` → `serve_fingerprint` section (missing section → refuse).
  - If `resume_identity` key present (new records): refuse unless it equals the current
    identity.
  - Else (legacy records, e.g. the live canary run): reconstruct the recorded identity as
    `server_fingerprint(argv=normalize_ephemeral_argv(recorded["server_command_redacted"]),
    executable_sha256=recorded["server_binary_hash"],
    model_file_sha256=recorded["model_artifact_hash"],
    ctx=recorded["context_length"], chat_template_digest=<current artifact digest or "">,
    env_allowlist/kv_cache_quant/parallel_slots/flash_attention=<the same values the
    current launch is using>)` and compare to the current identity.
    - Any missing/None recorded field among server_command_redacted, server_binary_hash,
      model_artifact_hash, context_length → refuse (fail closed).
    - Code comment required: using the *current* chat_template_digest for the recorded
      side is sound only because model_file_sha256 equality is enforced by the same
      comparison (identical GGUF bytes ⇒ identical embedded template); same reasoning for
      the constant env/kv/slots/flash inputs (if a future code change alters those
      constants, the identities diverge and the resume refuses — intended).
- Refusal message: keep the `unsafe resume refused: ...` prefix; name the mismatch
  (`resume identity changed` / `campaign.json serve_fingerprint is missing <field>`).
- Preserve the observed CLI failure behavior (process exits with code 70 today via the
  RuntimeError path). If you can raise the more precise `UnsafeResumeError` without an
  import cycle, do so; do NOT undertake the broader exit-code-collapse refactor (known
  backlog item, out of scope).

### R4 — record `resume_identity` (additive only)
- `ServingEvidence` (serving/provenance.py): new field `resume_identity: str`.
- `serving/assembly.py::serving_evidence(...)`: accept + populate it.
- `serving/bench.py::_serve_fingerprint(...)`: add `"resume_identity": evidence.resume_identity`
  to the dict (this is what lands in campaign.json's serve_fingerprint section and the
  manifest's serving context).
- `serving/bench.py::build_orchestrate_config(...)`: pass it through.
- `orchestrate.py::OrchestrateConfig`: new optional field `resume_identity: str | None = None`.
- `campaign_records.py`: if the serve section is written from explicit keys rather than
  the dict, add the key there too. No existing keys removed or renamed anywhere.

### R5 — `orchestrate.py::_validate_resume_campaign`
- Replace the exact `server_fingerprint` optional-compare (lines ~861-871) with an
  optional-compare of `config.resume_identity` vs recorded
  `serve_fingerprint.resume_identity`, using the existing `_append_optional_mismatch`
  semantics. Legacy records lack the key → this check is skipped here; that is acceptable
  ONLY because the runner-level precheck (R3) fail-closed-gates every serve-mode resume,
  and non-serve resumes have no serve_fingerprint section at all. Put that rationale in a
  comment + test.
- Segment recording (`run_record["segments"][...]["server_fingerprint"] = config.server_fingerprint`)
  stays EXACTLY as is — per-segment exact fingerprints are honest provenance.

### R6 — tests (all CPU-only; use fake runners/fixtures, no real server launches)
1. `normalize_ephemeral_argv`: masks only the port token; argv without `--port` unchanged;
   idempotent.
2. `resume_identity`: equal across two argvs differing only in port; differs when model
   hash / exe hash / chat template digest / ctx / a non-port argv flag differs.
3. Precheck new-record path: passes on port-only change; refuses on binary-hash change.
4. Precheck legacy path: fixture `serve_fingerprint` shaped like the real canary record
   (server_command_redacted with `--port 55419`, server_binary_hash, model_artifact_hash,
   context_length, NO resume_identity key) — passes with same components + different
   current port; refuses when any reconstruction field is missing (fail closed); refuses
   on model_artifact_hash mismatch.
5. `_validate_resume_campaign`: refuses when both sides present and different; skips when
   recorded key absent; all pre-existing hard-invariant checks unchanged.
6. Existing serving provenance tests updated where they assert the old precheck name /
   exact-fingerprint compare; the resumed-segment carry test
   (`test_run_localbench_resume_segment_carries_server_fingerprint`) must keep passing
   unchanged in meaning.
7. Full suite green: baseline on this branch/worktree is expected ~1019 passed / 13
   skipped / 1 xfailed — run it BEFORE changes to confirm the env, and after.

### R7 — acceptance probe (no GPU, no server launch)
- Script-level check (throwaway, do not commit results): construct the current-launch
  resume identity for the live canary run dir
  `C:\Users\Michael\local-bench\runs\bench\canary-4axis-capped-2026-07-02` (READ ONLY —
  never write there) using the real model/exe files, and assert the legacy-backfill
  reconstruction from its campaign.json matches. This proves the blocked canary resume
  will pass the new gate. Print both hashes in your final report.

## Hard constraints
- Work ONLY in this worktree (`C:\Users\Michael\local-bench-wt-resumefix`). NEVER touch
  `C:\Users\Michael\local-bench` (main checkout) or `C:\Users\Michael\local-bench-wt-agentic`.
- The live run dir `runs/bench/canary-4axis-capped-2026-07-02` (main checkout) is
  evidence: read-only.
- No GPU work, no llama-server model loads, no benchmarks.
- `cli/runs/board/board_v1.json` (copied fixture) must remain byte-identical
  (`git hash-object` = `3d058e6074bd781cc488c03255904b5f9599e37e`).
- Additive schema only; no reformatting of untouched code; frozen `sandbox.py` untouched.
- Do NOT commit — leave the tree dirty for review (Claude reviews + commits).
