# Benchmark queue

The canonical, growing list. Rules: every run goes through the **public CLI** (standing
owner policy 2026-07-15 — each run doubles as product QA); GPU runs start only on
explicit owner go-ahead; one suite at a time on the box.

| # | Model | Status | Why / notes |
|---|-------|--------|-------------|
| — | **PROGRAM PIVOT (owner, 2026-07-21): depth on Qwen3.6-27B — popular quants + fine-tunes of the one base — instead of breadth across models.** Research: `scratchpad/qwen36-27b-family-research-2026-07-21.md`. Base ranked row = Q4_K_M (`qwen3-6-27b-q4km-s2v5`). MLX repos excluded (Apple-only). | | |
| 0 | Qwen/Qwen3.5-9B (unsloth GGUF Q4_K_M) | **RUNNING** (2026-07-21) | Family anchor for Qwythos; 0.4.3 stranger-pathway shakedown (7 findings → 0.4.4 fixes staged). |
| 1 | unsloth/Qwen3.6-27B-GGUF **UD-Q2_K_XL** | next — pathway proving run on 0.4.4 | Replaces Ornith as the proving run: real ladder rung, in-family, ~11GB so cheapest 27B run. |
| 2 | unsloth/Qwen3.6-27B-GGUF Q6_K | queued (Tier 1 ladder) | Size/quality curve above the Q4_K_M base row. |
| 3 | unsloth/Qwen3.6-27B-GGUF Q8_0 | queued (Tier 1 ladder) | ~29GB, fits 5090; near-lossless reference point. |
| 4 | unsloth/Qwen3.6-27B-GGUF Q3_K_M | queued (Tier 1 ladder) | Lower rung between UD-Q2 and Q4. |
| 5 | Qwen/Qwen3.6-27B-FP8 (official) | queued (Tier 2, vLLM lane) | 5.6M dls — single most-used artifact of the family. |
| 6 | unsloth/Qwen3.6-27B-NVFP4 | queued (Tier 2, vLLM lane) | Owner-listed; Blackwell-native. |
| 7 | nvidia/Qwen3.6-27B-NVFP4 | queued (Tier 2, vLLM lane) | Vendor head-to-head vs unsloth NVFP4. |
| 8 | cyankiwi/Qwen3.6-27B-AWQ-INT4 | queued (Tier 2, vLLM lane) | Top AWQ (1.6M dls). |
| 9 | HauhauCS Qwen3.6-27B-Uncensored-Aggressive (GGUF Q4) | queued (Tier 3 fine-tunes) | Most popular fine-tune line (~480K dls across formats). |
| 10 | bottlecapai/ThinkingCap-Qwen3.6-27B (GGUF Q4) | queued (Tier 3) | Reasoning-tune, 341K dls. |
| 11 | prism-ml Bonsai-27B 1-bit (Q1_0, 3.8GB) | queued (Tier 3, carried) | Floor of the family size/quality curve. |
| 12 | DavidAU Heretic-Uncensored-NEO-CODE (GGUF Q4) | queued (Tier 3) | 131K dls. |
| 13 | huihui-ai abliterated (MTP-GGUF) | queued (Tier 3, **MTP flag**) | Verify llama.cpp MTP support first (also gates unsloth MTP-GGUF, 2.9M dls). |
| 14 | AEON-7 Ultimate-Uncensored NVFP4 | queued (Tier 3, vLLM lane) | 133K dls across formats. |
| 15 | bytkim MTP-pi-tune (GGUF) | queued (Tier 3, **MTP flag**) | |
| — | Tier 4 / long tail | backlog | SEA-LION v4.5-27B-IT, allenai/tmax-27b, TeichAI Fable-5-Experimental, GPTQ-Pro-4bit, int4-AutoRound. |
| — | Out of this program (kept on master list) | backlog | gemma-4 NVFP4 set + Qwen3.6-35B-A3B-NVFP4 (owner-listed 2026-07-18); bridge re-runs; MiniCPM5-1B; Agents-A1; **Ornith-1.0-9B (demoted by the pivot)**. |
| — | 12B ladder | **ON HOLD** (owner) | Do not schedule without explicit owner release. |

Rules unchanged: public CLI only, one suite at a time, GPU runs on owner go-ahead (program
approved 2026-07-21). Est. ~15-20h per 27B run — Tier 1+2 is roughly a week of GPU time.

Add new entries at the bottom with date + one-line rationale; promote by editing rank.
Source scans: `scratchpad/benchmark-priority-scan-2026-07-15.md`, `scratchpad/qwen36-27b-family-research-2026-07-21.md`.
