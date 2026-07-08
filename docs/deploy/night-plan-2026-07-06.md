# Night plan 2026-07-06 → 07 (Fable, full authority, owner asleep)

Owner directive: "keep going with remaining tasks… we lose access to Fable in <24h… make it
count. Opus can't get us to the finish line, so if you can't finish, leave a rock-solid plan
Opus can follow. Full authority. Orchestrate, code, delegate (GPT-5.5 high via codex), oracle if
you wish."

## The goal (crisp)
local-bench is a PUBLIC, REPRODUCIBLE community benchmark. "Done" = a stranger can
`pip install local-bench-ai`, fetch the current suite, run the current ranked lane
(bounded-final-v2 / full-exec-6axis-v1), and submit — AND the security model holds when they do.

## Three breaks that block "done" (all verified real 2026-07-06 evening)
- **R1 — PyPI stale.** PyPI `local-bench-ai` latest = 0.2.1, which PREDATES the suite-v2 pivot
  (bounded-final-v2 lane, exec-coding-141, AST gate + sentinel). A fresh `pip install` gives a CLI
  that cannot run the board's lane. Fix: publish 0.2.2 with the final harness. (Local pyproject is
  0.2.1 too — must bump.)
- **R2 — server release registry stale vs code.** Our own Gemma v2 auto-submit was REJECTED:
  `suite-v1-full-exec-6axis-v1 / 10369dd3… not registered`. Server registered a different sha than
  the current code computes. A legit community submit would bounce the same way. Fix: re-register
  release pairs server-side at the FINAL sha + deploy (the "v2 go-live" step that was never done).
- **R3 — coding axis forgeable (P1, task #42).** Re-confirmed by re-running the exploit tonight:
  `FORGERY SUCCEEDED: True`. A submitter's generated code forges a passing `<SENTINEL>` and
  `raise SystemExit(0)` before the trusted epilogue runs. Community coding scores are untrustworthy
  until fixed. Fix: invert control (trusted driver = __main__, untrusted imported as non-main under
  try/except BaseException) + tighten AST gate. MUST be result-preserving (canonical 148/148
  identical) so our own rows re-score, not re-run.

## Critical-path ORDER (why this order)
#42 bumps HARNESS_REV → coding scorecard_id → suite manifest sha. So the sha chain must settle
BEFORE we publish 0.2.2 and re-register the server, or we'd immediately need 0.2.3. Therefore:

1. **#42 coding-forgery fix** (cli/coding_exec). Codex builds to exact spec; I adversarially review
   + re-run exploit (must FAIL now) + canonical 148/148 verdict-preservation + tests green. Commit.
2. **Sha single-source-of-truth (#38) + re-sync all reference sites** to the post-#42 values.
   (A harness change moved these before — 34b5b38 caught a 5-way desync that would've rejected every
   v2 bundle. Do it deliberately + parity-test all sites.) Commit.
3. **#43 ZT-1 auto-publish hardening** (dormant behind auto_publish OFF; Fable-judgment so do it now).
   Codex builds; I review. Commit.
4. **Bump 0.2.2 + onramp.ts → v2 recipe + publish to PyPI.** Fresh-venv verify install→--version.
5. **Re-derive Gemma's live board row under the final harness** (coding verifier re-exec = the #42
   acceptance gate on Gemma's real data; verdicts identical; new scorecard_id) → rescore → board
   rebuild. Keeps the LIVE board's provenance honest (matches shipped harness). CPU/Docker in WSL —
   concurrent-safe with the GPU requeue (no GPU contention).
6. **Coordinated v2 go-live:** re-register server release pairs at final sha + deploy site + live
   verify + **fresh-machine dress rehearsal** (pip install 0.2.2 → fetch-suite → --max-items 1 smoke
   → submit --dry-run) PROVING a stranger can reproduce. Public-mode smoke.
7. **Requeue landing runbook** (mechanical, for Opus/me-later — requeue finishes ~07-08, past the
   Fable window). Verifier pass (already-refreshed lb-verify at final harness) → rescore → board
   rebuild (adds Qwopus + Qwen-base rows) → redeploy. This is the fine-tune-vs-base showcase.
8. Morning summary + memory update.

## Guardrails (unchanged, honor)
- GPU: do NOT touch — the requeue owns it. All my work is CPU/web/Docker.
- board pins: `git hash-object cli/runs/board/board_v1.json` must stay 3d058e60…; board_v2 re-pinned
  by the board pipeline. Verify at every commit.
- Secrets are FILE PATHS only, never echoed: admin `~/.localbench/local-bench-admin-secret.txt`,
  bypass `…local-bench-private-bypass-token.txt`, attester `…attester_ed25519.pem`, ops
  `~/.localbench/ops_log_ed25519.pem`, PyPI `…pypi-token.txt`.
- Codex = implementer (GPT-5.5 high), one repo-mutating codex at a time; I design/review/test/commit.
- Oracle: try opportunistically on #42 (security-critical); do NOT block on it (login may be stale).
  Substitute: a second codex-rescue instance as adversarial red-teamer of the built fix.
- Do NOT accept/publish any community coding submission (incl. QA fixture ticket_2d2f80a8) — that
  guard STAYS until #42 is verified closed; even after, keep auto_publish OFF + allowlist unset
  until #43 lands.

## Progress log
- 2026-07-06 ~20:20 AEST: reconstructed state, verified R1/R2/R3, wrote this plan. Starting #42 spec.
