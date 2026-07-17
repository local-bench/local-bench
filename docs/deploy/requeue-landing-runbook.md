# Requeue landing runbook — Qwopus + Qwen-base v2 rows (mechanical, for whoever lands them)

The GPU requeue (`C:\Users\Michael\lb-user-runs\runner-v2-requeue.ps1`, pid in
`runner-v2-requeue.pid`) benchmarks **Qwopus3.6-27B-v2-MTP** (a fine-tune of Qwen3.6-27B) then
**Qwen3.6-27B base** on the SAME v2 config Gemma used. It finishes ~2026-07-08 (past the Fable
window), so this is the deterministic hand-off. These two rows are the **fine-tune-vs-base
showcase** — the core purpose ([[feedback-local-bench-finetunes-first-class]]): Qwopus gets its
own model row with a base_model lineage chip; Qwen3.6-27B base is the comparator.

This is IDENTICAL to the Gemma v2 re-derivation done on the night of 2026-07-06 (see
`night-plan-2026-07-06.md` and the Gemma steps below). If Gemma landed cleanly, repeat it twice.

## Pre-req reality (why auto-submit "failed" and that's fine)
The runner auto-runs `localbench submit run` at the end of each phase. That submit **fails**
with `suite release pair is not registered: suite-v1-full-exec-6axis-v1 / <sha>` — BY DESIGN:
our runs use `--suite-dir suite/v1` (the source dir), whose manifest sha differs from the
registered release bundle. **Our own rows do not go through the submit gate — they are
re-scored and board-built by the maintainer** (steps below). The failed submit is cosmetic; the
run artifacts are complete. (A third-party user, by contrast, `fetch-suite`s the registered
bundle and DOES match — that path is proven by the go-live dress rehearsal.)

## 0. Wait for completion
- `Get-Content C:\Users\Michael\lb-user-runs\state-v2-requeue.json` → `{"phase":"all","status":"complete"}`
  (or per-phase `"qwopus"/"submitted"` then `"qwen-base"/"submitted"`).
- Run dirs: `C:\Users\Michael\lb-user-runs\runs\qwopus-v2-full\` and `...\qwen3-6-27b-v2-full\`.
- Each has a `localbench-run.json` with the static/agentic verdicts and **148 PENDING coding
  items** (verdict null — coding verdicts are filled by the verifier pass, never at gen time).
- GPU is free after this — you may stop the llama-server and the runner.

## 1. Coding verifier pass (WSL rootless Docker, per model) — fills coding verdicts under the FINAL harness
The harness is the post-#42 invert-control grader (commit 41dbe8d;
`SENTINEL_SCHEME_REV=bigcodebench-invert-control-sentinel-v2`,
`AST_GATE_REV=bigcodebench-ast-gate-v2`). Refresh lb-verify first so it has that code, then run.
**Launch WSL commands from PowerShell** (MSYS mangles `/mnt/c` paths — see night-plan). Image is
pinned; 60s/task; DOCKER_HOST is the rootless socket:

```powershell
# once, refresh the verifier to the committed harness:
wsl -d Ubuntu -u michael -- sh -lc "~/lb-verify/bin/pip install -q -e /mnt/c/Users/Michael/local-bench/cli"

# per model (run for qwopus-v2-full, then qwen3-6-27b-v2-full):
$img='bigcodebench/bigcodebench-evaluate@sha256:a3cd34ec3840a49d6b7afb240f4bdd47c350bc5991043fd0a91773830f7cd405'
wsl -d Ubuntu -u michael -- sh -lc "export DOCKER_HOST=unix:///run/user/1000/docker.sock; cd /mnt/c/Users/Michael/local-bench; ~/lb-verify/bin/localbench code --pending-run 'C:\Users\Michael\lb-user-runs\runs\qwopus-v2-full\localbench-run.json' --suite-dir suite/v1 --image $img --per-task-timeout 60 --receipt-signing-key ~/.localbench/maintainer-verifier.pem --out 'C:\Users\Michael\lb-user-runs\runs\qwopus-v2-full\coding-verified.json'"
```
Sanity: coding shows ~141 scoreable, a REAL pass rate (not 0%, not 100%). The 7 unscoreable ids
(bcbh-006/007/014/035/074/096/104) are auto-excluded. AST-rejected gens show as conformance
failures, not zeros.

**Community-submission verification (2026-07-17):** when the receipt is destined for
`submit admin-verify`/`verify-submission --coding-verified`, point `--pending-run` at the
**exact submitted bundle file** (the bytes whose sha256 the server pinned), NOT the local run
output. Admission binds `receipt.source_run_sha256` to the submitted-bundle bytes
(admission_coding.py `_admission_source_hashes`); a receipt produced against the local run file
fails with "coding verifier receipt is not bound to the submitted run". Also pass WSL paths
(`/mnt/c/...`) for both `--pending-run` and `--out` — Windows `C:\` paths raise
FileNotFoundError inside the verifier.

## 2. Re-score under the current scorer (no model re-run)
The run's inline scores were computed at gen time; re-derive the stamped scorecard identity +
budget audit from the current canonical functions (generations are hash-pinned, untouched).
Adapt `scratchpad/rescore_gemma.py` (from session 6fd61c59) — point SRC at each model's
`coding-verified.json`, OUT at `localbench-run.rescored.json`. It re-derives
`scorecard_identity(profile_id, lane_spec_id=lane)` + `_budget_audit(items)` and writes a
`rescore_provenance` block. Confirm the new `scorecard_id` matches the post-#42 profileless/
profile ids in `cli/tests/test_bounded_final_profiles.py` (the v2 pins updated in commit 41dbe8d).

### Automated maintainer path

Steps 2 and 3 are now one guarded command. It defaults to `<run-dir>/coding-verified.json`;
use `--coding-verified` only when the verifier output has a different name.

**Trust boundary:** `land-run` is maintainer-only automation over records produced by the
maintainer's own harness. Its campaign and agentic gates check structure, completeness, and
drift; they do **not** cryptographically authenticate that evidence and are not an anti-spoof
boundary. The maintainer must establish the authenticity of the input run directory. The coding
receipt and exact-GGUF checks do not extend that guarantee to non-coding evidence.

The public queue is intentionally an intake boundary, not a semantic validator. Worker admission
accepts only a size-capped blob whose R2 bytes match its declared content address and whose ticket
has a valid Ed25519 proof of possession; it does not decode, parse, canonicalize, or trust bundle
claims. Semantic truth - schema, suite coverage, model identity, result integrity, and any evidence
needed for acceptance - is established here on maintainer hardware in the `land-run` / verification
flow, consistent with the U1 trust boundary. Invalid pending blobs must be rejected through the
authenticated verification endpoint below.

```powershell
# Preflight all scorer, exact-GGUF, coding, agentic, curation, board, and web-data gates.
# This writes nothing.
uv run --project cli localbench land-run --run C:\path\to\finished-run --gguf C:\path\to\exact-model.gguf --verifier-public-key <64-hex-maintainer-key> --dry-run

# Apply the same checked plan. Deployment is deliberately not part of this command.
uv run --project cli localbench land-run --run C:\path\to\finished-run --gguf C:\path\to\exact-model.gguf --verifier-public-key <64-hex-maintainer-key>
```

The command writes the rescored canonical record under `runs/bench/landed/`, appends its
maintainer-controlled entry to `web/data_sources.json`, invokes the existing board builder,
rebuilds `web/public/data`, and re-pins `web/components/launch-freeze.ts`. It refuses before
writing if the candidate board changes any existing ranked model object, if the signed verifier
receipt is not bound to the current harness/suite and original run, if the actual GGUF bytes do not
match the claimed SHA-256, or if the two-run agentic campaign fails an
infrastructure gate. Its final checklist always leaves deploy + live smoke marked **MANUAL**.

### Pending-cohort rejection / purge path

Community admission deliberately does not recompute attacker-authored results. Per-key/global
caps and the 14-day pending GC limit occupation, but a bad bundle can still occupy one of the five
visible FIFO slots until it is rejected. The public queue never displays its declared slug. To
release a slot, use the existing authenticated admin verification endpoint and mark the row
`rejected` (the rejected raw object is removed by the existing 14-day rejected-object GC):

```powershell
$site = 'https://local-bench.ai'
$submissionId = '<ticket_id>'
$rawBundleSha256 = '<raw_bundle_sha256 from GET /api/admin/submissions?status=pending_verification>'
$headers = @{ 'x-localbench-admin-secret' = $env:LOCALBENCH_ADMIN_SECRET }
$body = @{
  accepted = $false
  blocking_reasons = @('attacker-authored or invalid pending bundle')
  projection_path = 'rejected/no-public-projection.json'
  projection_sha256 = ('0' * 64)
  raw_bundle_sha256 = $rawBundleSha256
  reason = 'maintainer queue purge'
  schema_version = 'localbench.submission_status_update.v1'
  status = 'rejected'
  validated_at = (Get-Date).ToUniversalTime().ToString('o')
  validator_commit = $null
  validator_version = 'maintainer-manual-reject.v1'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$site/api/admin/submissions/$submissionId/verification?override=true" -Headers $headers -ContentType 'application/json' -Body $body
```

Use `override=true` only to evict a known bad row out of FIFO order; omit it when rejecting the
oldest visible row. The admin secret is mandatory. Rejection immediately removes the row from the
pending cohort; it does not publish any submitted content.

## 3. Board rebuild (adds both rows; Gemma already present)
The board is a maintainer-built static artifact — community submits never produce ranked rows.
```
# from repo root, cli venv:
uv run --project cli localbench board          # -> cli/runs/board/board_v2.json + release manifest
cd web && python build_data.py                 # -> web/public/data/*.json (reads board_v2)
```
Curation: **Qwopus = its own model row** (`qwopus3-6-27b-v2-mtp`, catalog entry exists, commit
c136ce4), fine-tune of Qwen3.6-27B, base_model lineage chip. **Qwen3.6-27B base = its own row**
= the vs-base comparator. Do NOT merge Qwopus into Qwen. If a model lacks a catalog entry, add it
to `web/model_catalog.json` (see the Qwopus entry as a template) before build_data.
Re-pin LAUNCH_FREEZE as the board pipeline requires (`sha256sum cli/runs/board/board_v1.json`
must stay `3d058e6074bd781cc488c03255904b5f9599e37e`).

## 4. Deploy + smoke
```
cd web
scripts/publish-board.ps1      # chains tests -> data -> build -> deploy -> live-verify
# or manually: build-site.ps1 ; deploy-site.ps1 ; launch-smoke.ps1 -ExpectedMode Public
```
Live-verify: local-bench.ai/leaderboard shows Qwopus + Qwen-base rows with all 6 axes; the
Qwopus row shows its base_model lineage chip and a vs-base delta against Qwen3.6-27B.

## 4b. FOLD IN: Gemma board re-derivation (deferred from the 2026-07-06 night deploy)
The night-of-2026-07-06 deploy shipped code + the 6-axis bundle + suite-catalog (fetch-suite
works, submit registers c4098df8) but did NOT rebuild the board, to avoid a rushed LAUNCH_FREEZE
re-pin. Gemma's board run is ALREADY re-scored on disk under the post-#42 harness:
`runs/bench/ranked-6axis-bounded-final-2026-07-06/gemma-4-12b-it-qat-ud-q4kxl-bounded-final-v2.json`
now carries scorecard_id `39edac77…` (was `e4903c5d…`); its coding was re-verified under the new
harness = 40/141, 0 mismatches (result-preserving, number unchanged at Index 35.20). The board
rebuild in step 3 picks this up automatically (data_sources.json references that file). If the
file is missing/reverted, re-run `scratchpad/rescore_gemma_v42.py` (session badb6de7) first.
So the requeue board rebuild re-derives ALL THREE rows (Gemma + Qwopus + Qwen-base) uniformly
under the post-#42 harness — which is exactly why folding Gemma here (one rebuild) beat rebuilding
twice. Update `web/components/launch-freeze.ts` `boardSha256` to the freshly built board sha
(`sha256sum cli/runs/board/board_v2.json` after the build) as part of step 3. `boardSha256`
is always the board writer's 64-hex SHA-256, never a Git blob object ID.

## 5. Notes / gotchas
- One Docker verifier pass at a time (single WSL rootless daemon). ~10-15 min/model.
- The server advertises and enforces a 67,108,864-byte (64 MiB) raw-bundle cap; oversized uploads
  get `413 {"code":"bundle_too_large",...}`. Measured real bundles are 20,219,268 bytes for the
  5-axis anchor, 27,858,532 bytes for 6-axis Q4, and 44,417,038 bytes for rung-1 Q2. The cap covers
  the largest measured bundle with the policy's ~44% headroom target. Finalize streams R2 chunks
  directly into `crypto.DigestStream`, so admission peak memory is O(chunk), independent of the cap.
- If a coding re-verify shows a pass count wildly different from a sane range, STOP — a harness/
  image drift is more likely than a real model regression; check the image sha + lb-verify revs.
- The requeue rows use the CURRENT scorer, so no sha churn — they slot into the existing v2 board.
- Publication of these rows is the same board-build path as Gemma (maintainer-built), not the
  community accept flow — no ticket/accept needed.
