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
| 6 | NVFP4 quant-delta rows (31b / 12b / 27b / 35b-a3b vs Unsloth NVFP4) | **gated** on vLLM appliance lane | Was already the post-UD-Q4 target; scan of 07-15 raised priority. Tool-calling claims directly testable on the tool_use axis. |
| 7 | Bridge re-runs (season-1 legacy trending rows) | backlog | Cheap wins; see scan §bridge. |
| 8 | openbmb/MiniCPM5-1B | backlog | Trivial GPU cost; may score near-floor. |
| 9 | InternScience/Agents-A1 (35B) | backlog | Agent-specialized; strong tool_use story; ~20GB Q4, long bench. |
| — | 12B ladder | **ON HOLD** (owner) | Do not schedule without explicit owner release. |

Add new entries at the bottom with date + one-line rationale; promote by editing rank.
Source scans: `scratchpad/benchmark-priority-scan-2026-07-15.md` (+ hf-scan JSONs).
