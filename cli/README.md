# local-bench-ai

CLI benchmark runner for [local-bench.ai](https://local-bench.ai) — a community quality
leaderboard for local AI setups. It benchmarks GGUF models served by llama.cpp (or any
OpenAI-compatible endpoint), scores them on the six-axis Local Intelligence Index
(Agentic, Knowledge, Instruction-Following, Tool calling, execution-verified Coding, Math),
and packs signed, reproducible result bundles you can submit for maintainer review.

## Quickstart

```bash
pip install "local-bench-ai[hf]"   # Python 3.11+

# 1. Fetch the ranked suite from the site (hash-verified)
localbench fetch-suite --site https://local-bench.ai \
  --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms

# 2. Cache the tokenizer/chat template for offline identity
localbench cache-tokenizer <hf-model-id>

# 3. Strongest provenance: the CLI launches the pinned llama.cpp server itself
localbench bench \
  --runtime llama.cpp --server-bin <path-to-llama-server> \
  --model-file <model.gguf> --model-id <model-slug> \
  --hf-model-id <hf-model-id> \
  --suite full-exec-6axis-v1 --bench all \
  --lane bounded-final-v2 --profile auto --tier standard \
  --ctx 32768 --seed 1234 --out runs/my-bench

# 4. Submit for maintainer review (nothing auto-publishes)
localbench submit run --run runs/my-bench
```

The site's [submit page](https://local-bench.ai/submit) generates these commands for your
exact model and runtime, including the full identity flag set for bring-your-own-server
runs. Publishable bounded-final-v2 runs require a 32k server context.

## What makes rows trustworthy

- Suites are hash-pinned releases; sampler settings are pinned (greedy, seeded).
- Coding is BigCodeBench-Hard, re-executed by the maintainer's sandbox verifier before it
  can rank; community agentic results are labeled self-reported.
- Every number on the board links to a receipt with the full run manifest.
- Nothing ranks without maintainer review.

Methodology: <https://local-bench.ai/methodology>
