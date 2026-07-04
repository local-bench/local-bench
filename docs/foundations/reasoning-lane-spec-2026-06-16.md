# Reasoning-for-all lane + cap calibration — execution spec (2026-06-16)

*The last fit-for-purpose piece before a trustworthy suite-v1 re-run. Scorers ✓ and knowledge-keys ✓ are done;
this defines the LANE the re-run uses. Ready to execute on Michael's GPU/spend go.*

## 1. Why a new lane (the problem this fixes)
The existing data is cross-lane and unfair: **frontier anchors ran with native reasoning; locals ran
answer-only** (`--reasoning-effort none`). Worse, the locals *still* reasoned into the token cap and got
truncated — which is exactly what produced the math false positives we just fixed (truncated non-answers
credited by the last-number fallback). Michael's decision: **reasoning-for-all** — every model reasons, scored
in one lane, so the comparison is apples-to-apples.

## 2. The lane (definition)
- The code's lane literals are **`answer-only` / `capped-thinking` / `api-uncapped`** (orchestrate.py
  `LaneChoice`). The reasoning-for-all lane = **`capped-thinking`**: thinking ENABLED, under a calibrated
  per-axis token cap set ABOVE natural completion (a runaway bound, NOT a brevity/fairness control).
- **Run BOTH locals AND a fresh anchor pass in `capped-thinking` with the SAME caps.** Composite is computed
  **within a lane only** (lanes never merge), so locals and anchors MUST share the lane for the comparison to be
  valid. The old anchor data (`api-uncapped`) and the old local data (`answer-only`) stay as secondary lanes,
  never merged into this one.
- **Tokens-to-answer is a first-class output** (already captured as `usage.completion_tokens`): report accuracy
  AND compute-burned side by side (AA-style), so reasoning length informs rather than constrains. The site
  surfaces both; never fold tokens into the accuracy score.
- The old answer-only numbers become a secondary "fast-mode" lane (kept, not deleted, never merged).

## 3. Cap calibration (do this FIRST — short, cheap)
The cap per axis is a runaway ceiling set *above* the think-on natural-completion distribution. Calibrate it,
don't guess it.

**Procedure (per local model, ~20-30 sampled items/axis):**
1. Serve the model reasoning-ON (see §4), provisional cap = the suite.json per-bench `max_tokens` (below).
2. Run the sample; record the **completion-token distribution per axis** (median, p95, p99) and the
   **non-termination rate** (items that hit the cap with no final answer).
3. Set each axis cap to **≈ p95–p99 of think-on completions, rounded up**, bounding degenerate loops. If
   non-termination stays high even at the provisional cap (P0 saw 25–36% on hard 9B math at 14k — genuine
   non-termination, not loops), keep the cap where compute cost levels off and accept those as scored-wrong
   (the scorer now handles truncation correctly).

**Current provisional caps (suite/v1/suite.json — starting points):** math (amo/olymmath) 16384 · knowledge
(mmlu_pro) 12288 · ifbench/bfcl/lcb 8192 · ruler_32k 4096. Math is the reasoning-heaviest; ruler the lightest.
Calibration confirms or nudges these for the reasoning lane.

## 3b. MEASURED — Qwen-Q4 calibration sample (2026-06-16, capped-thinking, n=6/axis)
Pipeline validated END-TO-END on suite-v1 (serving + reasoning + MMLU-Pro + fixed scorers), 0 errors.
Composite 62.5%; per-axis: knowledge(mmlu_pro) 66.7%, instruction(ifbench) 100%, agentic(bfcl) 66.7%,
coding(lcb) 83.3%, math 0%.

| axis | cap | ct_median | ct_p95 | trunc(len) | verdict |
|---|---|---|---|---|---|
| mmlu_pro | 12288 | 2568 | 12288 | 2/6 | minor truncation — consider 16384 for the full run |
| ifbench | 8192 | 4497 | 6464 | 0/6 | well-calibrated (generous) |
| bfcl | 8192 | 231 | 245 | 0/6 | hugely generous (tool calls are short) |
| lcb | 8192 | 2876 | 8192 | 1/6 | minor truncation — consider 12288 |
| olymmath_hard/amo | 16384 | ~16250 | ~16290 | 6/6 | **genuine non-termination** — Qwen-Q4 reasons to the ceiling, never converges; cap is a correct runaway bound. **Validates the math scorer fix: all 12 truncated items correctly scored 0, no FPs.** |

**TIME REALITY (load-bearing for scope):** 36 reasoning items = 2555s (~43 min) at concurrency 2, dominated by
the math axis (~16k tok/item). Extrapolated to the full standard suite (~1262 items): **~15 hrs/model** → the
full 6-quant ladder ≈ **~4 days of 5090 time**. Levers: reduce item counts (ranked-lite), raise concurrency
(2→4 with box-freeze caution), or fewer quants. The math axis dominates wall-clock for little signal (always 0).

## 4. Serving (local, 5090, WSL2 — no spend, GPU time only)
Native llama.cpp built for sm_120 (Blackwell). Reasoning-ON = **omit** `--reasoning-effort none`:
```
~/bin/micromamba run -n cuda ~/llama.cpp/build/bin/llama-server \
  -m ~/models/<gguf> -ngl 99 -c <ctx> --parallel 2 --jinja --host 127.0.0.1 --port 8080
```
- `-c <ctx>`: must exceed the longest prompt + cap. RULER 32k needs `-c ~40000`; other axes ~16k. Serve RULER in
  a separate pass with a large `-c` (KV-cache memory on a 32GB card is the constraint — verify Q4 27B + 40k KV
  fits, else reduce parallelism / run RULER at a lower ctx tier and label it).
- Drive via `localbench run --provider local --endpoint http://127.0.0.1:8080/v1 --suite-dir suite/v1
  --lane capped-thinking` (NOTE: `--suite-dir suite/v1` is REQUIRED — `discover_suite_dir()` still defaults to
  v0; and do NOT pass `--reasoning-effort none`, which suppresses Qwen3 thinking — `capped-thinking` leaves it on).
- `pkill -x llama-server` between models (never `-f`). Mining is retired — the 5090 is free.

## 5. Anchors (API — this is the $$ part, gated)
The v1 anchor runs are stale for knowledge (they used SuperGPQA; the axis is now MMLU-Pro) and incomplete
(missing lcb/ruler on some). A clean reasoning-lane comparison needs the **anchors re-run on suite-v1 incl.
MMLU-Pro, in the SAME `capped-thinking` lane with the same per-axis caps** — i.e. the discrimination probe.
(The high caps rarely bite frontier, which reasons more efficiently than the locals the caps are sized for.)
Configs (max thinking): GPT-5.5 `openai-reasoning` xhigh; Gemini `gemini-3.1-pro-preview` high (its max —
rejects xhigh); Opus `claude-opus-4-8` xhigh. **Cost-probe first**
(~30 items/model), show Michael the measured per-item cost, then full run only on his OK. Rough order: prior
3-axis Quick anchors were ~$9 total; a fuller 7-axis reasoning run is more — estimate at probe time.

## 6. Recommended staged execution (GPU-time-aware)
Full ladder = 6 local runs (Qwen3.6-27B Q2/Q3/Q4/Q6/Q8 + Gemma-12B) × ~1322 standard items × reasoning ≈ many
hours each → 1–2 days of 5090 time. So stage it:
1. **Calibrate** caps on one representative local (Qwen Q4) — short.
2. **Pilot**: full suite-v1 reasoning run on Qwen Q4 only → sanity-check the per-axis spread + completion rates +
   that the new MMLU-Pro axis behaves. Cheap signal before the big commitment.
3. **Anchor refresh** (gated $$): cost-probe → Michael OK → run the 3 anchors on suite-v1 reasoning lane.
4. **Full local ladder**: the remaining quants + Gemma, overnight/unattended, watchdog the server.
5. **Rebuild site data** from the reasoning-lane runs; the quant-wedge + distance-to-frontier now use one fair lane.

## 7. What's gated on Michael
- **GPU time** for the local runs (free $ but 1–2 days of 5090). Step 1–2 (calibrate + Qwen-Q4 pilot) is a few
  hours — reasonable to start on his go.
- **API spend** for the anchor refresh (step 3) — cost-probe first, explicit OK before the full spend.
Everything up to step 2 is no-spend. I can start calibration + the pilot immediately when he says go.

## 8. Data products
Per-axis accuracy + chance-corrected scores + bootstrap CIs, **per-model tokens-to-answer**, paired quant-deltas
(Q? vs Q8 on the fixed items ± paired CI), all in the `reasoning` lane. Feeds the home leaderboard (one fair
lane), the model scatter (quality vs VRAM), and the quant-degradation wedge.
