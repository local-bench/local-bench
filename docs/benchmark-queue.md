# Benchmark queue

The canonical, growing list. Rules: every run goes through the **public CLI** (standing
owner policy 2026-07-15 — each run doubles as product QA); GPU runs start only on
explicit owner go-ahead; one suite at a time on the box.

| # | Model | Status | Why / notes |
|---|-------|--------|-------------|
| 1 | prism-ml/Ternary-Bonsai-27B (Q2_0) | **RUNNING** (static finishing 2026-07-18) | First exotic-runtime case (PrismML fork); vs-base delta against Qwen3.6-27B at ~1/7 size. Coding-zero anomaly under investigation before publication. |
| 2 | Bonsai-27B agentic phase | queued (today, after static) | First agentic run on the c0v4 appliance via released 0.4.2. |
| 3 | Qwen/Qwen3.5-9B | queued (owner-added 2026-07-18) | Family anchor: gives the Qwythos-9B lineage a real base row and vs-base delta; fills the sub-12B gap on the board. ~5–8h estimate. |
| 4 | deepreinforce-ai/Ornith-1.0-9B | queued | Scan candidate #2 (1.55M dl, MIT); sibling of legacy Ornith-35B rows. |
| 5 | prism-ml Bonsai-27B 1-bit (Q1_0, 3.8GB) | queued | Sibling of #1; same fork runtime, tests the floor of the size/quality curve. |
| 6 | NVFP4 quant-delta set (owner-listed 2026-07-18, five repos): [unsloth/gemma-4-31B-it-NVFP4](https://huggingface.co/unsloth/gemma-4-31B-it-NVFP4), [unsloth/gemma-4-26B-A4B-it-NVFP4](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-NVFP4), [unsloth/gemma-4-12b-it-NVFP4](https://huggingface.co/unsloth/gemma-4-12b-it-NVFP4), [unsloth/Qwen3.6-27B-NVFP4](https://huggingface.co/unsloth/Qwen3.6-27B-NVFP4), [unsloth/Qwen3.6-35B-A3B-NVFP4](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-NVFP4) | **gated** on vLLM appliance lane | Owner-confirmed set (adds 26B-A4B to the original four). NVFP4 runs vLLM/TensorRT, not llama.cpp — blocked until the vLLM lane ships in the public CLI appliance. Quant-delta vs base rows (Qwen3.6-27B ranked base already on board; Bonsai comparison bonus). Guides: [gemma-4](https://unsloth.ai/docs/models/gemma-4), [qwen3.6 NVFP4](https://unsloth.ai/docs/models/qwen3.6#nvfp4), [NVFP4 basics](https://unsloth.ai/docs/basics/nvfp4). Note: gemma-4-12b NVFP4 is owner-listed here explicitly; the broader 12B ladder hold below still stands. |
| 7 | Bridge re-runs (season-1 legacy trending rows) | backlog | Cheap wins; see scan §bridge. |
| 8 | openbmb/MiniCPM5-1B | backlog | Trivial GPU cost; may score near-floor. |
| 9 | InternScience/Agents-A1 (35B) | backlog | Agent-specialized; strong tool_use story; ~20GB Q4, long bench. |
| — | 12B ladder | **ON HOLD** (owner) | Do not schedule without explicit owner release. |

Add new entries at the bottom with date + one-line rationale; promote by editing rank.
Source scans: `scratchpad/benchmark-priority-scan-2026-07-15.md` (+ hf-scan JSONs).
