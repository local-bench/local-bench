# Session checkpoint — 2026-06-20 (local-bench)

Durable resume point (committed to the repo so it survives session loss). Branch
`suite/v1-quant-wedge`, commits LOCAL — **do not push**. Standing rule: never launch GPU work
on the local RTX 5090 without Michael's explicit go (build/spec/test freely).

## What this session did (all committed, local)
Worked the GPT-5.5 Pro oracle's foundations red-team to done, then unblocked + started the
discrimination campaign. New commits on `suite/v1-quant-wedge` (newest first):
- `24e77fa` docs(campaign): pre-register Core Text keep/kill rule before the GPU run
- `31c9862` feat(forge): forced answer-pass truncation = scored failure, not a headline exclusion
- `9397a84` feat(forge): enforce capped-thinking budget for local vLLM via s1-style forcing
- (earlier this session, foundations) `52669fe`, `d4e994e`, `578e340`, `b071db0`, `ac24ada`,
  `2afae13`, `ede9d0a`, `f878aa3`, `1684616` — see METHODOLOGY-v1.2 §12.
Test state: **624 green** (`cd cli && .venv\Scripts\python.exe -m pytest tests -q`), ruff clean.

## The big unblock: capped-thinking budget forcing (DONE + LIVE-VERIFIED)
Small Qwen3 models on vLLM thought past the 16384 cap without closing `</think>` → empty
content+reasoning → ~65% no-answer → the lane-conformance gate (correctly) killed the run as
`diagnostic-only`. The locked "capped-thinking, budget 8192" was never enforced for local vLLM.
- Fix = s1-style two-pass budget forcing on the raw `/v1/completions` endpoint
  (`cli/src/localbench/budget_forcing.py`): think to 8192 (stop on `</think>`), force-close,
  generate the answer; scrub any re-reasoning in the answer pass. Routed in `_requests.py` only
  for local + capped-thinking + a `think_budget` item; every other lane/provider unchanged.
- Live result on Qwen3.5-4B: composite **25.7% → 94.4%**; leaked-reasoning + no-final-answer
  both **0%** at 30 items.
- Conformance refinement (oracle option A): under budget-forcing, answer-pass truncation
  (`finish_reason=length`) is a SCORED model failure (degenerate loop / non-termination — every
  case inspected, zero legit long-answer cutoffs) surfaced as a visible `answer_cap_hit_rate`
  diagnostic, NOT a headline exclusion. Leaked / no-answer / single-pass truncation stay hard
  gates. An orchestrate audit warns if any cap-hit item scored CORRECT (oracle's risk mitigation).

## The campaign (STARTED then PAUSED — GPU returned to Michael)
Goal: does the headline (Knowledge=MMLU-Pro + Instruction=IFBench, capped-thinking) SEPARATE
local sizes? Pre-registered GO/KILL rule (oracle-endorsed) committed at
`docs/foundations/methodology-lock/CORE-TEXT-CAMPAIGN-PREREG-2026-06-20.md`.
- Panel: Qwen3.5 same-family ladder **0.8B, 2B, 4B, 9B** (all HF-cached in WSL).
- Oracle design check: run FULL sets (MMLU-Pro 400 + IFBench 294) × 4, NOT a first-N slice
  (too noisy/order-biased for a keep/kill). Uniform forcing; raw accuracy primary; cap-hit
  annotated not down-weighted. After a GO, validate with 1–2 off-family anchors.
- **Reality: this is an 8–12h OVERNIGHT job.** Small models over-think to the full 8192 budget
  on most items, so each item burns near-max tokens; 0.8B alone didn't finish in ~65 min.
  Paused + torn down cleanly when Michael needed the GPU (no completed file = nothing lost
  but GPU time).
- Oracle fallback if a full overnight run is impractical: ~200 items/bench (≈half the time) is a
  "minimum semi-trustworthy" directional read (continue/full-run decision, not final keep/kill).

### HOW TO RESUME THE CAMPAIGN (when GPU is free for a long stretch, with Michael's go)
Per model, smallest first (serve in WSL, client on Windows against localhost:8000):
1. Serve (long-lived BACKGROUND task — do NOT fire-and-forget):
   `wsl bash -lc "exec ~/serve_localbench.sh '<HF-id>' '<served-name>'"`
   HF ids: `Qwen/Qwen3.5-0.8B|2B|4B|9B` → served names `qwen3.5-0.8b|2b|4b|9b`.
2. Poll ready: until-loop on `wsl bash -lc "curl -s localhost:8000/v1/models" | grep <served-name>`.
3. Client (Windows):
   `cli\.venv\Scripts\python.exe -m localbench run --endpoint http://localhost:8000/v1
   --model <served-name> --bench mmlu_pro,ifbench --tier standard --lane capped-thinking
   --provider local --concurrency 8 --suite-dir C:\Users\Michael\local-bench\suite\v1
   --out runs\campaign-<served-name>.json`
4. Kill server (`wsl bash -lc "pkill -9 -f 'vllm[ ]serve'"` — the `[ ]` avoids self-match) → next.
Then analyze: `cd cli && .venv\Scripts\python.exe -m localbench.probe --runs runs\campaign-*.json
--labels runs\campaign-labels.json --suite-dir ..\suite\v1 --out runs\campaign-discrimination.json`
plus the paired-bootstrap GO/KILL eval at `%TEMP%\analyze_campaign.py`.
Orchestration gotchas (cost 2 failed smoke tests): WSL `nohup &` inside a one-shot `wsl -lc`
gets reaped; PowerShell `Start-Process wsl -ArgumentList` mangles the spaced bash `-c` arg;
`pkill -f 'vllm serve'` self-kills (use `vllm[ ]serve`). The `campaign-run.ps1` is retired.

## Website (Next.js dark site, `web/`) — FIXED, LIVE at http://localhost:3000
Local dev only (no deploy yet; Vercel/Supabase deferred). Next 16 + Turbopack, Tailwind v3,
`output: "export"`. Reads static data from `web/public/data/*.json` built by `web/build_data.py`.
Run: `cd web && npm run dev` → http://localhost:3000 (dev task this session: `bztmvsjzm`).
All routes verified 200: `/`, `/methodology/`, `/trust/`, `/compare/` (+ `/model/[slug]`, `/run/[runId]`, `/submit/`).
- **Why Michael couldn't access it (2026-06-20):** a stale dev server from **June 14** held :3000 and
  returned 500; a fresh `npm run dev` ALSO 500'd with Tailwind v3 `resolveChangedFiles` ENOENT on
  `app/page.tsx` (which exists fine — Node stats it). Root cause = a **527 MB stale `.next` cache**
  vs source files edited today 07:49 (site-overhaul task #32). 
- **FIX (if it 500s with that Tailwind ENOENT again):** stop dev server, `rm -rf web/.next
  web/node_modules/.cache`, free :3000, `npm run dev`. Clean recompile resolves it.

## Trackers (volatile — in %TEMP%, may be lost; this doc is the durable copy)
- `%TEMP%\campaign-local-bench.md` — campaign detail + orchestration learnings.
- `%TEMP%\refactor-local-bench.md` — the overnight foundations-hardening loop + handoff.
- `%TEMP%\analyze_campaign.py` — pre-registered paired-bootstrap GO/KILL analysis.

## Open decisions for Michael
1. Public headline NAME — implemented as "Local Intelligence Index (v1 · Core Text)"; confirm or change.
2. When to run the overnight campaign (full sets vs ~200/bench fallback).
3. Deferred-with-specs: S2 (canonical KLD calib pack) + S3 (stratified frozen slices, RISKY —
   touches deterministic item-slicing). See METHODOLOGY-v1.2 §12.

## Campaign launch — ops notes (2026-06-20, this session; decision #2 actioned, full sets)
**CAMPAIGN COMPLETE 2026-06-21 → STRONG GO on BOTH axes → LAUNCHABLE Local Intelligence Index.**
Full result + paired-bootstrap CIs: `docs/foundations/methodology-lock/CORE-TEXT-CAMPAIGN-RESULT-2026-06-21.md`.
Index (composite = chance-corrected mean): 0.8B 17.8 → 2B 37.8 → 4B 59.9 → 9B 69.1. Knowledge spread
9B−0.8B +54.5pp [+49.5,+59.5]; Instruction +41.5pp [+34.7,+48.0] (both CIs clear of zero). Ladder driven
smallest-first, each serve→run→kill→next; run JSONs in `cli/runs/campaign-qwen3.5-<size>.json` (durable).
OPEN before publishing absolutes: IFBench cap-hit high even at 9B (21%) → raise answer-token budget +
re-score; truncation audit (16–33 items/model scored correct); probe label-schema fix; off-family anchors.
- **2B was NOT actually cached** (28K stub) despite the "all cached" note → pulled with
  `hf download Qwen/Qwen3.5-2B`. NOTE `huggingface-cli` is now a DEAD no-op (deprecated) — use `hf`.
- **Serve MUST force offline:** `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ~/serve_localbench.sh <id> <name>`.
  First 0.8B serve crashed because vLLM did an ONLINE metadata fetch for the omni image-processor and
  HF dropped the connection (`Server disconnected`). All 4 panel models are Qwen3.5 OMNI
  (`Qwen3_5ForConditionalGeneration`, fully cached incl. `preprocessor_config.json`) → offline-safe and
  removes the network dependency for the unattended run.
- **WSL-via-Bash-tool quoting gotcha:** `$var` / `$(...)` inside `wsl bash -lc '...'` get expanded to
  EMPTY by a wrapper BEFORE WSL sees them (literal `~` and plain strings pass fine). Escape every `$`
  as `\$`, or use literal paths / git-bash-level loops. Cost several turns of false-empty readings.
- **Smoke (0.8B, 4 items/bench):** pipeline OK (ifbench answered, 0 errors, budget-forcing engaging
  ~15k tok/item). 0.8B ~0% (expected, bottom rung). WATCH: mmlu_pro had no-extractable-answer on the
  smoke → confirm 0.8B mmlu_pro CONFORMANCE at full N (could flag diagnostic-only on the Knowledge axis
  for the bottom rung; pre-reg GO#5 already accounts for a melting-down small model).
- **Front-end agent** ran (audit+fix): 3 copy commits `8bdf4f1`/`686b927`/`3ebc14a` on this branch,
  site healthy/all-routes-200. KEY: site is an INTENTIONAL scoreless catalog (`data_sources.json=[]`)
  awaiting THIS campaign's capped-thinking data; biggest real gap = NO KLD/drift column (UI still frames
  quant as an accuracy tradeoff, contra METHODOLOGY §6).
