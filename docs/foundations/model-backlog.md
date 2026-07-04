# Model backlog — community local models to benchmark

Source: Michael's "Best Local LLMs for Consumer GPUs — llama.cpp Guide (June 2026)" (2026-06-15).
These are exactly the *community-run, consumer-GPU* setups local-bench exists to score, and our native
**llama.cpp sm_120** stack (WSL2) already runs any GGUF by one-liner with verified thinking-suppression +
the run/compare pipeline. Ties to task #35 (HF sweep). Not yet run — backlog.

## Candidates by VRAM tier
### 8–16 GB
- **Gemma 4-12B (Google)** — smartest in its size class; Unsloth **MTP** GGUF claims 162 vs 52 tok/s (~3×).
  `huggingface.co/unsloth/gemma-4-12b-…`
- **LFM2.5-8B-A1B (LiquidAI)** — hybrid MoE, only ~1B active → very fast for its size; 8–12 GB / MacBook.
  `huggingface.co/LiquidAI/LFM2.5-8B-A1B-…`

### 16–32 GB (our RTX 5090 tier)
- **Qwen3.6-27B (Qwen)** — *the model in our current wedge.* Guide: 1.00 tool-efficiency, 40 deterministic
  tasks + 32k/128k needle tests passed. Unsloth GGUF + an **MTP (faster)** version. Our BFCL agentic axis
  already corroborates the strong-agent claim (91–97%).
- **Qwopus3.6-27B-v2 (Jackrong)** — billed as the *best quant/finetune of Qwen3.6-27B*; topped 5 agent &
  coding benchmarks (1200 samples). A direct **community-build-vs-base** comparison candidate. (We already
  have Jackrong `qwopus3.5-27b-v3` + Qwen3.5-Opus distills on the box.) `huggingface.co/Jackrong/Qwopus…`
- **Gemma 4-31B QAT (Google/Unsloth)** — QAT + MTP draft head: 76–125 tok/s (~1.67×). Good multi-agent.
- **Nex-N2-Mini (Nex AGI)** — post-train of Qwen3.5-35B-A3B, MoE ~3B active; "adaptive thinking" saves ~20%
  tokens at ~no quality loss; overflows to system RAM on 16 GB. `huggingface.co/sjakek/Nex-N2-…`

## Cross-cutting axes these surface (high value, ordered)
1. **MTP / draft-head variants = the SPEED axis.** The guide cites 1.67–3× tok/s from MTP at ~same quality.
   Our quant wedge just showed that **cost (speed/VRAM), not accuracy, is the real local differentiator** —
   MTP is the same story for the serving method. The bench question: *does MTP preserve quality while
   boosting tok/s?* This is the single highest-value addition (it makes the leaderboard's cost axis sing).
2. **Community quant/finetune vs base** — Qwopus, Nex post-trains, Unsloth re-quants vs the stock model:
   "which community build should I actually run?" (Our wedge already showed lmstudio Q4 ≈ Q8; this extends
   it across *publishers/finetunes*, not just bit-width.)
3. **MoE with few active params** — LFM2.5 (~1B active), Nex-N2 (~3B active): quality-per-active-FLOP, and
   the speed win on consumer cards.
4. **Context tiers** — Qwen3.6-27B's 32k/128k needle claims map to the **RULER long-context axis** (Michael's
   earlier 8k/32k/128k interest, task #47).

## Stack readiness
- Serve any GGUF: `~/bin/micromamba run -n cuda ~/llama.cpp/build/bin/llama-server -m <gguf> -ngl 99
  -c 8192 --parallel 2 --cache-type-k q8_0 --cache-type-v q8_0 --jinja --host 127.0.0.1 --port 8080`.
- Thinking-suppression (per-request `enable_thinking=false`) verified on both lmstudio + bartowski templates.
- MTP note: llama.cpp serves MTP/speculative via the draft model flags — confirm the exact `--model-draft` /
  MTP-head invocation per model card before benchmarking the speed claim.
