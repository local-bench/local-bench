# Overnight runbook — 2026-08-01 → 02 (deeper-budgets chain to 0.4.14)

Owner asleep; Claude runs the chain under standing authority (deploy-on-clean-gate;
announce/yanks stay Michael's). This file is the authoritative sequence + rules for
tonight. Each phase has an entry gate; a failed gate HALTS the chain at that phase —
no skipping forward, no silent retries of scored or validation runs.

## State at handoff (~20:00)

- Branch `codex/local-bench-online-backend`, HEAD `8876ddc` (-lv 4 capacity-evidence fix)
  on `bfba881` (v9 ceremony), `f4c4014` (QA round), `5734fd6`/`ccff53d` (T10/T9).
- Contract v9 ACTIVE (payload `26d1072b…`), 20/20 contract tests green, full CLI suite
  green at `bfba881` (2232/0 authorized-red).
- Anchor validation PASS on the 5090: capacity probe true, 65536/f16/f16, epoch-bound,
  audit promised 49152 / observed 26,695, 26,868 MiB, 65.65 tok/s.
- Gemma validation caught a REAL defect (declared 32k tuple, executed legacy budgets;
  probe correctly failed closed). Codex fix in flight: task `b1rjnsuft` (started 19:25),
  scope = gemma-32k budget flow + mandatory per-profile budget-FLOW tests; legacy
  gemma-8192 lane frozen; instructed to STOP if any contract-covered module needs edits.
- Fusion 8k row LIVE + ranked (43.52; supersedes ticket_4dec3df9 over the invalid row;
  landing duties complete). GPU idle. NVFP4/vLLM lane stays parked. Vast box off-limits.
- Monitors armed: Codex completion notification (task exit) + commit ticker with 45-min
  stall alert (`bkm0vkwf4` / `bh1qehxxw`).

## R3 verdict (pinned tonight, measured — supersedes "provisional" wording)

From the fusion bundle's scored runs (2×96 tasks, 1863 turns each, deterministic):
per-turn output tokens p50=74 / p90=247 / p95=373 / p99=886 / max=3072; finish_reason
length = 5/1863 = **0.27%**. The cap that actually bound 0.4.13 execution was the
**appliance LoopConfig default 3072** — the host-side 1024 constant never flowed into
the worker (a default shadow, same defect class T4 eliminates; discovered tonight from
`scored.run*.json` loop_config). Projected clip rate at the new contract-owned 1024 cap:
14/1863 = **0.75%** — under the 2% R3 trigger, and p99 (886) sits below the cap.
**R3 = keep 1024.** Watched metric from row 1: T4's per-turn p95/p99/max diagnostics.
Copy corrections owed (post-Codex, web/): methodology line 342 cites "0.32%" (actual
0.27% at executed 3072) and says per-turn "remains 1024" (false continuity — executed
legacy was 3072); same line says "R2 PRO 6000" (owner: 5090-only).

## Phase 1 — Codex lands (gate: task b1rjnsuft exit + commits present)

1. Read the FULL diff. Scope check: gemma budget-flow seams + tests only. If any
   contract-covered module was edited: do NOT proceed to validation — assess whether the
   edit is legitimate; if yes, run the v10 ceremony (same tool/invocation as v9:
   `cli/tools/finalize_agentic_execution_contract.py`, evidence at
   `C:\Users\Michael\lb-runtime-build\c0v5\native-conformance\`, key
   `~\.localbench\agentic-contract-2026-07.pem`, `--allow-dirty`) BEFORE any validation
   run counts; if the edit looks wrong, revert and re-dispatch with a tighter brief.
2. Verify the mandatory tests exist: per-profile budget-FLOW tests for all 5 ranked
   profiles asserting request trace + item promise (`max_tokens`) + audit totals;
   gemma-32k must assert trace [32768, 16384] and promised total 49152.
3. Zero-red gates at new HEAD: full CLI suite + contract tests (CPU-only; GPU is idle
   so no sequencing conflict).

## Phase 2 — gemma validation rerun (gate: Phase 1 green)

```
localbench bench --runtime llama.cpp \
  --model-file "C:\Users\Michael\lb-rung0\models\gemma-4-31B-it-Q4_K_M.gguf" \
  --model-id gemma-4-31b-it-q4-k-m --hf-model-id google/gemma-4-31b-it --seed 1234 \
  --lane bounded-final-v1 --profile gemma4_channel_32768_v1 --ctx 65536 \
  --server-bin "C:\Users\Michael\llamacpp\b10076\llama-server.exe" \
  --tier standard --bench mmlu_pro --max-items 3 --no-submit --yes \
  --out "C:\Users\Michael\lb-rung0\runs\validation-0414-gemma-fix1"
```

Acceptance = parity with the anchor evidence chain: `runtime-capacity-probe.json`
written with passed:true; audit max_promised_total 49152; per-item budget trace
[32768, 16384]; epoch binding verified; VRAM within the 5090 envelope.
(CORRECTED: `manifest.execution_profile.runtime_probe_passed` is the RENDERER-equivalence
probe field — false on BOTH validation runs because the --hf-model-id path skips it; it
is NOT an acceptance criterion. Codex round-1 caught my error here.) On FAIL: halt GPU chain, write the evidence note,
re-dispatch Codex with the trace — do NOT start R2.

## Phase 3 — R2 turn-cap calibration (gate: Phase 2 PASS; overnight GPU block)

Pre-registered rule (plan §R2): fixed AppWorld DEV subset at max_turns ∈ {32, 40, 48}
on the 5090, non-publishable; adopt the smallest value where the dev trajectory
distribution stops being materially cap-dominated (cap_exceeded_dev ≤ 10%); default 40
if flat. Set agentic per-task bound ≥ dev p99 cumulative (provisional 65536).
Mechanics: resolve the max_turns override via the validation/dev entrypoint of the
0.4.14 tree (contract-owned LoopConfig — look at T4's test helpers for the dev-override
seam); NEVER by editing the ranked lane. Launch DETACHED (scheduled task) with ntfy on
completion + stall watchdog. **Nothing else heavy runs during this block** — no suites,
no web builds (process-exhaustion rule: suites sequential, never concurrent with
GPU/WSL). If ambiguous/flat evidence → adopt 40 and write the flag into the morning
report rather than silently choosing.

## Phase 4 — post-R2 batch (gate: R2 complete, cap frozen, GPU free)

1. Freeze final turn cap + task bound; if either differs from the frozen tuple
   (40/65536), that is a tuple change → re-mint + ceremony + fixture updates BEFORE
   release (decision recorded, not silent).
2. Fusion publication merge (fixes the owner-raised scatter gap): bake the
   qwopus-fusion model entry + registry + per-artifact metadata (file sha `eeb9b184…`,
   file GB, vram_gb_8k via the SAME estimator basis as the existing ladder) so
   `model-scatter.tsx:112` stops dropping the live row. Plus owed publication merges /
   registry entries from the Qwopus chain.
3. Web copy corrections (from R3 section above) + T8 methodology accuracy pass; vitest
   green.
4. Hermetic wheel blackbox per RELEASE-RUNBOOK (contract assertion against the BUILT
   wheel), widen S10 window, then PyPI publish 0.4.14 (token env-only from
   `Desktop\API keys.txt`, never echoed) and site deploy `git push deploy HEAD:main`
   on the clean tech gate.

## Phase 5 — queue start (gate: 0.4.14 live on PyPI + fresh-venv smoke install)

Row 1 of `C:\Users\Michael\lb-rung0\rerun-queue-32k.md` (qwen3-6-27b-q5-k-m) via the
PUBLISHED CLI only; per-run capacity preflight; detached + ntfy; sequential. Standing
row rules: R1 saturation audit publishes after row 2; row 3 (gemma leader) landing+verify
triggers task #8 (flip `BOARD_DEFAULT_OPERATING_POINT_VIEW`); row 10 artifact-identity
check → owner decides skip.

## Escalation / abort rules

- Validation acceptance miss → halt at that phase + evidence note. BSOD/driver event →
  halt ALL GPU work, preserve evidence, owner decides in the morning (no auto-restart).
- Codex silent > ~90 min (two stall alerts) → inspect its session log, then kill
  (PID-scoped only) and re-dispatch; never two Codex instances on one tree.
- Contract-covered edit discovered late → invalidate any validation run made under the
  stale contract and redo after ceremony.
- Michael-only (untouched tonight): announce batch 0.4.5→0.4.14, PyPI yanks
  0.4.9/0.4.10, MSI Afterburner Profile1 slot deletion.

## Morning deliverables

Dense checkpoint covering: Codex fix verdict + diff summary; gemma rerun evidence
chain; R2 curve + adopted cap; release state (published/held + why); queue position;
the two tonight-catches (gemma budget-flow defect, appliance 3072 default shadow) and
what now guards each.

---

## Addendum — R2 execution record (2026-08-02, post-oracle)

Topology pivot chain: the pre-registered WSL-funnel→Windows-server topology is dead on
this box (ProtonVPN kill-switch WFP filters drop WSL→host traffic; VPN config is
owner-only) → all-WSL lane chosen after oracle consult `r2-path-forward` (GPT-5.6 Sol
Pro, 2026-08-02) plus the post-consult discovery that WSL carries a complete system
CUDA 13.3.1 toolkit at /usr/local/cuda. Server = llama.cpp b10076 (305ba51) built in
WSL with that toolkit — same CUDA 13.3 family as the Windows campaign runtime; the
residual parity gap (OS/compiler) is the consult's lowest-ranked validity threat. The
oracle's A-path (owner Proton toggle) was not required: its own decision rule — "run R2
iff A passes preflight or B succeeds in one clean build attempt" — was satisfied by B.

Oracle gates implemented (topology-independent, ranked above parity by the consult):
1. Per-task watchdog = 3000s (operating point), not the 1800s LoopConfig default that
   censors the t48 tail. Funnel gained diagnostic `--per-task-timeout-s` (commit
   de70bcc); driver GATE0 asserts the effective value from the printed loop line.
2. Decision denominator frozen PRE-LAUNCH: runs 1+2 pooled per arm (72 task-runs);
   ASR-drift-triggered 3rd runs are diagnostic-only. Decision rule: smallest cap with
   cap_exceeded ≤ 10% (7/72 passes, 8/72 fails); flat / knife-edge / non-monotonic →
   40. No post-hoc tie-breakers.
3. GATE0 asserts manifest hash a77c910a8b24… / size 36 / seed 20260624 before any GPU
   use; mismatch stops the driver.
4. Smoke gate requires funnel exit 0 + serve-log growth + ≥1 persisted report, after a
   direct chat probe returning HTTP 200 with a choices object (log growth alone is not
   success). An EXIT/INT/TERM trap kills the server — no stale-server contamination.

Post-R2, before the Phase 5 queue: one production-direction Windows→WSL smoke to
reconfirm the scored lane (consult aftercare). VPN and Windows production lane
untouched throughout.

**R2 VERDICT (2026-08-02 12:10, run complete, overall_ok=true):** pooled cap_exceeded —
t32 14/72 (19.44%), t40 10/72 (13.89%), t48 8/72 (11.11%); none ≤ 7/72, t48 misses by one
event. ASR identical (0.1389) at all three caps across six bit-identical reruns; extra
turns relabel cap_exceeded→failure, never produce successes. Per the pre-registered rule
and the pre-stated none-pass treatment: **turn cap = 40**, per-task bound 65536 — the
provisional contract v9 values, so **no re-mint and no ceremony**. Transport 4,201/0
failures; 0 harness errors; per-turn format failures ≤1.67% (< the 2% R3 trigger — the
1024 per-turn cap stands). Proceed to Phase 4.
