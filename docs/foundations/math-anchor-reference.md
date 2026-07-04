# Math Anchor — Reference Ceiling (REPORTED scores)

**Purpose.** These tables collect **published, author-reported** frontier-model scores on two
Olympiad-level math benchmarks (AMO-Bench and OlymMATH EN-HARD), for use as a **labeled
"reference ceiling"** on the leaderboard. **Every number below was measured by the benchmark
authors on their own harness — NOT by local-bench.** They are anchors / context only. Do not
present them as comparable to our own measured runs: sampling settings, attempt counts, token
budgets, and (for AMO-Bench) model versions differ from ours and from each other. Treat them as
"what the source reported, when, under which harness."

Compiled 2026-06-14. Each row cites a source URL. Where a figure could not be verified it is
flagged rather than guessed.

---

## 1. AMO-Bench

- **Benchmark.** 50 original, expert-crafted, IMO-or-harder problems (designed to be contamination-free). HF dataset `meituan-longcat/AMO-Bench`.
- **Metric.** **AVG@32** — accuracy averaged over 32 independent samples per problem, across all 50 problems. (Confirmed in paper §evaluation and the leaderboard axis label "AVG@32 (%)".)
- **Authors' harness (from paper, arXiv:2510.26768v1).** Temperature **1.0** for reasoning models / **0.7** for non-reasoning models; top_k=50, top_p=0.95; max output tokens = "highest allowable limit for each model" (i.e. each model's own max, not a fixed budget). NOT our harness.
- **Two sources, two dates:**
  - **Paper (2025-10-31):** original 22–26 model table; SOTA was GPT-5-Thinking (High) at 52.4%.
  - **Live leaderboard (snapshot 2026-02-05):** superset with newer frontier models (Gemini 3 Pro, GPT-5.1, Claude Opus 4.5, Qwen3-Max-Thinking, etc.). Numbers below are read from the official leaderboard bar chart `leaderboard_20260205.png` on amo-bench.github.io.
- **Caveat on reading the chart:** values are transcribed from the published bar-chart image (labels printed above each bar), cross-checked against the project changelog and paper table where models overlap. Bar-chart transcription is high-confidence for the printed numbers but treat the last decimal as image-read, not copy-pasted from a CSV.

### AMO-Bench — leaderboard snapshot 2026-02-05 (AVG@32)

| model | score | metric | source URL | date | harness notes |
|---|---|---|---|---|---|
| Qwen3-Max-Thinking | 65.1% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | authors' harness; reasoning model (temp 1.0); SOTA on snapshot |
| Gemini-3-Pro | 63.1% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 (added 2025-11-24) | first model to break 60% |
| GLM-4.7 | 62.4% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | open-source record on snapshot |
| Kimi-K2.5 | 61.8% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | open weights |
| DeepSeek-V3.2-Speciale | 60.3% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | open weights |
| Doubao-Seed-1.8 | 60.0% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | proprietary |
| GPT5.1-Thinking | 56.4% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | proprietary, reasoning |
| Kimi-K2-Thinking | 56.0% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 (added 2025-11-19) | changelog quoted 56.0%; chart bar reads ~56 (see note) |
| Claude-Opus-4.5 | 54.8% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | proprietary, reasoning |
| LongCat-Flash-Thinking-2601 | 54.6% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | Meituan's own model (benchmark authors) — note potential first-party bias |
| GLM-4.6 | 54.1% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | open weights |
| GPT-5-Thinking (High) | 52.4% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) | original paper SOTA; also on snapshot chart at 52.4 |
| DeepSeek-V3.2-Thinking | 51.9% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | open weights |
| Grok-4 | 48.6% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | proprietary |
| Qwen3-235B-A22B-Thinking-2507 | 47.8% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | open weights |
| DeepSeek-V3.1-Thinking | 47.6% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | open weights |
| Grok-4.1-Fast | 47.3% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | proprietary |
| LongCat-Flash-Thinking | 43.6% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | Meituan first-party model |
| o4-mini (High) | 40.2% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | proprietary, reasoning |
| Gemini-2.5-Pro | 38.7% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | proprietary, reasoning |
| Qwen3-Next-80B-Thinking | 34.8% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | open weights |
| o3-mini (High) | 32.4% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | proprietary, reasoning (paper table had 32.3; snapshot reads 32.4 — see note) |
| Qwen3-Max-Instruct | 28.8% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning (temp 0.7) |
| Claude-Sonnet-4.5 | 27.7% | AVG@32 | https://amo-bench.github.io/ | 2026-02-05 | proprietary (paper table had Claude-Sonnet-4.5 at 17.6 — see version note) |
| Qwen3-Next-80B-Instruct | 18.2% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning |
| Gemini-2.5-Flash | 18.1% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning |
| LongCat-Flash | 14.6% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | Meituan first-party, non-reasoning |
| DeepSeek-V3.1 | 9.8% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning |
| Kimi-K2 | 7.5% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning |
| DeepSeek-V3-0324 | 5.2% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning |
| GPT-4.1 | 4.1% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning |
| GPT-4o-20241120 | 1.5% | AVG@32 | https://arxiv.org/abs/2510.26768 | 2025-10-31 (paper) + snapshot | non-reasoning |

**Discrepancy flags (AMO-Bench):**
- **Claude-Sonnet-4.5:** paper table (2025-10-31, read from arXiv HTML) lists **17.6%**; the 2026-02-05 leaderboard chart shows **27.7%**. Likely a re-run / harness update / model-version change between dates. Use the leaderboard value (27.7%) as current, but flag the divergence — do not treat as settled.
- **o3-mini (High):** paper HTML read **32.3%**; snapshot chart reads **32.4%** (rounding / re-run; immaterial).
- **Kimi-K2-Thinking:** changelog (2025-11-19) states **56.0%**; this followed a 2025-11-05 correction to Problem 35, so small shifts vs any pre-correction number are expected. Chart bar consistent with ~56.
- **Claude-Opus-4 vs Opus-4.5:** the *paper* table includes "Claude-Opus-4" at ~10.6% (non-reasoning config); the *snapshot* lists "Claude-Opus-4.5" at 54.8%. Different models — don't conflate. (Opus-4.5 is the current anchor.)
- **First-party caveat:** AMO-Bench is published by Meituan-LongCat, whose own LongCat-Flash models appear high on the board. Standard caution for author-run scores of the authors' own models.

**Primary sources (AMO-Bench):**
- Paper: AMO-Bench, arXiv:2510.26768v1 — https://arxiv.org/abs/2510.26768 (HTML: https://arxiv.org/html/2510.26768v1 ; PDF: https://arxiv.org/pdf/2510.26768)
- Live leaderboard + changelog: https://amo-bench.github.io/ (chart image: https://amo-bench.github.io/static/images/leaderboard_20260205.png)
- Repo: https://github.com/meituan-longcat/AMO-Bench
- HF dataset: https://huggingface.co/datasets/meituan-longcat/AMO-Bench

---

## 2. OlymMATH — EN-HARD (English, Hard subset)

- **Benchmark.** OlymMATH, 200 Olympiad-level problems in parallel EN/ZH; split into EASY (AIME-level) and HARD. The **HARD subset = 100 problems**. HF dataset `RUC-AIBOX/OlymMATH`.
- **Subset requested:** **English × HARD** only (the table below is the `OlymMATH-EN-HARD` column from the paper).
- **Metric.** Reported as **P@1 (pass@1)**, but computed as the **average accuracy over k samples** (an avg@k estimate of single-attempt accuracy), NOT a single greedy decode. The paper also reports C@k (consensus@k / majority vote over 64) which is NOT used below.
- **k (number of samples averaged):** **64 samples** for most (locally-run) models; **8 samples** for the heavier API/large models — explicitly including **DeepSeek-R1, o3-mini (high), Gemini 2.5 Pro Exp**, plus OpenMath-Nemotron-32B, Qwen3-235B-A22B, GLM-Z1-Air. So the three frontier rows below are **avg@8**.
- **Authors' harness.** temperature **0.6**, top_p **0.95**, min_p 0, max_token **32768** for locally-evaluated models; API models used their max. NOT our harness.
- **Source = the original paper only.** arXiv:2503.21380**v2** (March 2025). There is **no ongoing public leaderboard** for OlymMATH; the repo points users to run their own eval (LLMBox/OpenCompass/LightEval) and ships an `OlymMATH-eval` dataset of 582,400 generations from 28 models, but publishes no maintained scoreboard. Frontier coverage is therefore **frozen at the early-2025 generation** — no GPT-5/5.1, no Claude 4.x, no Gemini 3.x, no DeepSeek-V3.x.

### OlymMATH-EN-HARD (paper Table, P@1 = avg over k samples)

Frontier / strong models first; full table (incl. small open models) below for context.

| model | score | metric | source URL | date | harness notes |
|---|---|---|---|---|---|
| Gemini 2.5 Pro Exp 03-25 | 58.4% | P@1 (avg@8) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | API model, 8 samples; highest reported on EN-HARD |
| OpenAI o3-mini (high) | 31.2% | P@1 (avg@8) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | API model, 8 samples |
| Qwen3-235B-A22B (Think) | 36.5% | P@1 (avg@8) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | large open model, 8 samples |
| DeepSeek-R1 | 19.5% | P@1 (avg@8) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | API/large, 8 samples |
| Qwen3-30B-A3B (Think) | 26.3% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Skywork-OR1-Preview (32B) | 25.2% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| QwQ (32B) | 23.1% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Light-R1-DS (32B) | 22.3% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| GLM-Z1-Air (32B) | 20.1% | P@1 (avg@8) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | 8 samples |
| OpenMath-Nemotron (32B) | 16.6% | P@1 (avg@8) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | 8 samples |
| OpenMath-Nemotron (14B) | 18.8% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| OpenThinker2 (32B) | 16.9% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| DS-R1-Distill (32B) | 16.9% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| OpenMath-Nemotron (7B) | 17.4% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Light-R1-DS (14B) | 16.1% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| AceMath-RL (7B) | 14.2% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Qwen3 (4B, Think) | 13.9% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| DS-R1-Distill (14B) | 13.3% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| OpenThinker2 (7B) | 12.4% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Light-R1-DS (7B) | 12.2% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Skywork-OR1-Math (7B) | 12.2% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| DS-R1-Distill (7B) | 11.1% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| OpenMath-Nemotron (1.5B) | 10.4% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Skywork-OR1-Preview (7B) | 10.0% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| DeepScaleR-Preview (1.5B) | 4.1% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| STILL-3-Preview (1.5B) | 3.8% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |
| Qwen3 (0.6B, Think) | 3.0% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples; table floor |
| DS-R1-Distill (1.5B) | 1.5% | P@1 (avg@64) | https://arxiv.org/html/2503.21380v2 | 2025-03 (v2) | local, 64 samples |

**Notes / flags (OlymMATH EN-HARD):**
- The standout **Gemini 2.5 Pro Exp 03-25 = 58.4%** is far above the next model (o3-mini high 31.2%, R1 19.5%) — the authors highlight this gap. It is an avg@8 number on the experimental March-2025 Gemini 2.5 Pro; treat as that snapshot, not current Gemini.
- "P@1" here is an **averaged** estimate (avg@k), not greedy single-shot — so it is methodologically closer to our avg@k than to a strict 1-attempt run, but k and temperature differ from ours.
- No GPT-5/Claude-4/Gemini-3 generation exists for this benchmark in any authoritative source as of 2026-06-14. If a newer third-party EN-HARD number is wanted, it would have to be community-run (not author-reported) and should be labeled as such.

**Primary sources (OlymMATH):**
- Paper: "Challenging the Boundaries of Reasoning: An Olympiad-Level Math Benchmark for LLMs", arXiv:2503.21380v2 — https://arxiv.org/abs/2503.21380 (HTML: https://arxiv.org/html/2503.21380v2)
- Repo: https://github.com/RUCAIBox/OlymMATH
- HF dataset: https://huggingface.co/datasets/RUC-AIBOX/OlymMATH ; eval-generations dataset `OlymMATH-eval`; demo Space: https://huggingface.co/spaces/RUC-AIBOX/OlymMATH-demo

---

## Reference-ceiling summary (for leaderboard labeling)

- **AMO-Bench (AVG@32, 50 problems).** Reported frontier ceiling ≈ **63–65%** (Qwen3-Max-Thinking 65.1, Gemini-3-Pro 63.1, GLM-4.7 62.4) on the live leaderboard (2026-02-05); the *paper* (2025-10-31) topped out at GPT-5-Thinking 52.4%. Strong-but-older anchors (Gemini-2.5-Pro 38.7, o4-mini 40.2, DeepSeek-R1-0528 ~34) sit far below. **Authoritative + current:** maintained leaderboard at amo-bench.github.io with a dated changelog; high reliability, but author is Meituan (first-party models present) and the newest values are transcribed from the leaderboard bar-chart image.
- **OlymMATH EN-HARD (P@1=avg@k, 100 problems).** Reported ceiling = **Gemini 2.5 Pro Exp 58.4%**, then a steep drop (o3-mini high 31.2%, Qwen3-235B 36.5%, DeepSeek-R1 19.5%). **Source is the original arXiv paper only (v2, Mar 2025) — no maintained leaderboard**, so coverage is frozen at the early-2025 frontier (no GPT-5/Claude-4/Gemini-3). Reliable as a static reference, but stale relative to current models; the 58.4 vs ~30 gap means the ceiling here is effectively "one model far ahead, the rest ≤~37%".
- **Cross-benchmark caveat for the leaderboard:** these are two different harnesses (AMO-Bench avg@32 @ temp 1.0/0.7; OlymMATH avg@8–64 @ temp 0.6) on two different problem sets — the ceilings are not comparable to each other, and neither is directly comparable to our own measured runs. Label both as **REPORTED (authors' harness), reference only.**
