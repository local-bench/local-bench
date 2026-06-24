# Overnight orchestration charter (2026-06-23) — autonomous loop north-star

Durable equivalent of `/goal` (a UI command, not programmatically settable). A fresh context
after compaction should read THIS + the task ledger (#17-32) + docs/foundations/* to re-orient.

## GOAL
Drive local-bench to a complete, QA'd, launch-ready **v1** — ONE combined public launch
(run -> submit -> on-the-board; called "v1" publicly; v1/v2 are internal iterations).
Combined-launch is Michael's CONFIRMED call ("you only make a first impression once"). Ship
COMPLETE; timing can flex. Front-load risk-discovery so a late blocker can't blindside it.

## CRITICAL PATH (priority order; tracks 1 and 2 run in parallel)
1. **AGENTIC AXIS — reinstated priority, do NOT cut** (Michael overruled the de-scope: cutting
   the hard axis ruins the robustness that is the whole point). Sequence he directed:
   research a viable AppWorld protocol -> **oracle red-team** -> implement (fix the 3 adapter
   bugs + chosen protocol) -> **benchmark the already-run models (Qwen ladder + gemma)** so
   agentic becomes a REAL scored axis with its own board column. Lead hypothesis: bounded
   **code-as-action** (AppWorld's eval is deterministic => judge-free holds regardless of action
   mode; a task needing ~34 API calls needs only a handful of code BLOCKS). Research agent
   a5cd3c60 running; findings -> design -> oracle -> Codex implement -> GPU benchmark.
2. **gemma** corrected thinking-lane run (#17, GPU, event-gated): on completion, gate
   (conformance-pass, no leaked reasoning, suite hashes mmlu_pro 129b8d97…/ifbench 40dc0b3e…),
   regenerate the FINAL board (+gemma row), FREE the GPU (stop server bsmvzwzx4).
3. **Oracle punch-list + launch-debt**: determinism repeatability slice [GPU, after gemma];
   pseudonymous signed release manifest; contamination/trust policy; upload-bundle security;
   `localbench verify` offline; assemble + relay the v1 site packet to the SITE agent (point it
   at board_v1.json systems[] — it renders, never re-derives).
4. **FINAL GATE — thorough MULTI-AGENT QA** (Michael's explicit instruction, task #32): before
   declaring v1 complete, run a multi-agent QA pass (Workflow / parallel review agents) across
   all dimensions, adversarially verify findings, synthesize. Nothing is "done" until this passes.

## CONSTRAINTS (non-negotiable)
- Local commits only, **NEVER push**. Work only in `cli/` + `docs/foundations/` — the SITE agent
  owns `web/` (never edit it; it is active concurrently in the same tree, cleanly partitioned).
- GPU only for pre-authorized gemma + the agentic benchmark of already-run models; **max parallel
  benchmark concurrency 4**; no other GPU work without explicit authorization.
- Stay anonymous: repo private, owner pseudonymous, Cloudflare-only public infra.
- **Independently verify every sub-agent's output** before trusting it (re-run tests, inspect
  artifacts). Oracle is authorized for the agentic design red-team (Michael directed it).

## LOOP MECHANICS
Autonomous dynamic `/loop` via ScheduleWakeup (~1800s fallback heartbeat) + event-driven on
task/agent notifications. Each fire: check gemma health (GPU util + END-file
cli/runs/ladder-gemma4-31b-Q4_K_M.json + server tail) and in-flight agents; advance the critical
path; re-arm. Done = critical path complete AND the final multi-agent QA (#32) passes.
