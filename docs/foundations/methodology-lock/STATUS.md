# suite-v1.1 methodology-lock — LOOP STATUS

GOAL: Lock suite-v1.1 methodology. Paper decisions DONE + SIGNED OFF (2026-06-18). Now executing
the approved staged validation campaign (DECISION.md Section D) to finalize the lock with measured data.

SIGN-OFF (Michael, 2026-06-18): KV cache = hold f16. Campaign = approved. RULER + mixed-difficulty
math = candidates, Stage 2 decides. Difficulty-stratification = retired. One signed weight source.

HARD CONSTRAINTS:
- One model/server/run at a time. NEVER parallel GPU runs.
- Before each GPU stage: measure tokens/item on ~20 items, report wall-clock estimate to Michael BEFORE the full run.
- KV cache f16 (not quantized). Branch suite/v1-quant-wedge; commit locally; DO NOT push.

CAMPAIGN STAGES:
- Stage 0 [in progress] NO GPU: reconcile 3 weight copies -> 1 signed manifest; diagnose math floor
  (dataset vs scorer) on existing data; scorer false-rate spot-check per axis; confirm Qwen3.6-8B
  GGUF availability (Q6_K + Q4_K_M) for Stage 1.
- Stage 1 [pending] Wedge gate, 8B FIRST: Qwen3.6-8B Q6 vs Q4, ~1000 stratified paired items,
  reasoning-on, f16 KV. Stratified paired bootstrap + McNemar. GO if Q4 drop >=4pp; NO-GO if <3pp
  (then wedge -> secondary feature, pivot to distance-to-frontier). 20-item throughput probe first.
- Stage 2 [pending] Axis discrimination/calibration -> final keep/weight (spread-proportional).
- Stage 3 [pending] Budget sweep 4/8/12/16k on ~300 mixed items -> confirm/correct 8192.

RESUME: read DECISION.md + this file. Continue from the first incomplete Stage-0 item. Do NOT launch
any GPU run without the throughput probe + estimate. Do NOT relaunch old calibration scripts.
